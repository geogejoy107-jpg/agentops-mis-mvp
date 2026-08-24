import type { PoolClient } from "pg";
import { NextRequest, NextResponse } from "next/server";

import { legacyPythonProxyAllowed } from "./config";
import { withPostgresTransaction } from "./db";
import { authenticateHumanMember } from "./humanSession";
import { ControlPlaneHttpError, errorPayload } from "./http";
import { appendAudit, stableHash } from "./ledger";
import { proxyControlPlaneRequest } from "./proxy";

const HUMAN_WORKER_READ_ROLES = new Set([
  "operator",
  "approver",
  "reviewer",
  "workspace-admin",
  "owner",
]);
const COMMERCIAL_EDITIONS = new Set([
  "pro_workspace",
  "team_governance",
  "enterprise_byoc",
]);
const KNOWN_INACTIVE_ENTITLEMENTS = new Set(["inactive", "suspended", "expired"]);
const ADAPTERS = ["mock", "codex", "hermes", "openclaw"] as const;
const WORKER_LIMIT = 50;
const EVENT_LIMIT = 25;
const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, X-AgentOps-Workspace-Id",
};

export type HumanWorkerReadKind = "status" | "fleet" | "adapter-readiness";

type EntitlementRow = {
  edition: string;
  status: string;
  effective_at: Date | string;
  expires_at: Date | string | null;
};

type WorkerRow = {
  agent_id: string;
  name: string;
  role: string;
  runtime_type: string;
  status: string;
  updated_at: string;
  token_status: string;
  heartbeat_timeout_sec: number;
  token_expires_at: string | null;
  last_used_at: string | null;
  last_heartbeat_at: string | null;
  scope_count: number;
  active_session_count: number;
  recent_event_status: string | null;
  recent_event_at: string | null;
};

type EventRow = {
  runtime_event_id: string;
  event_type: string;
  status: string;
  agent_id: string | null;
  runtime_connector_id: string | null;
  latency_ms: number | null;
  created_at: string;
};

type AdapterRow = {
  runtime_type: string;
  enrolled_workers: number;
  active_enrollments: number;
  active_sessions: number;
  fresh_workers: number;
  stale_workers: number;
  last_heartbeat_at: string | null;
  recent_successes: number;
  recent_failures: number;
};

function timestamp(value: Date | string | null) {
  if (value === null) return null;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
}

function boundedText(value: unknown, field: string, maximum: number, nullable = false) {
  if (value === null && nullable) return null;
  if (typeof value !== "string" || value.length > maximum) {
    throw new ControlPlaneHttpError(
      503,
      "human_worker_fleet_state_invalid",
      `The stored ${field} is outside the bounded worker fleet contract.`,
    );
  }
  return value;
}

function boundedCount(value: unknown, field: string) {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0 || parsed > 1_000_000) {
    throw new ControlPlaneHttpError(
      503,
      "human_worker_fleet_state_invalid",
      `The stored ${field} is outside the bounded worker fleet contract.`,
    );
  }
  return parsed;
}

function safeRef(prefix: string, value: string) {
  return `${prefix}_${stableHash({ value }).slice(0, 16)}`;
}

function requestedWorkspace(request: Request) {
  const search = new URL(request.url).searchParams;
  const keys = [...new Set(search.keys())];
  if (keys.some((key) => key !== "workspace_id")) {
    throw new ControlPlaneHttpError(
      400,
      "human_worker_fleet_query_unsupported",
      "Worker fleet reads only accept workspace_id.",
    );
  }
  const values = search.getAll("workspace_id");
  if (values.length > 1) {
    throw new ControlPlaneHttpError(
      400,
      "human_worker_fleet_query_ambiguous",
      "Worker fleet workspace binding must have one value.",
    );
  }
  return values[0] ?? "";
}

async function activeCommercialEntitlement(client: PoolClient, workspaceId: string) {
  await client.query(
    "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
    [`agentops:workspace-entitlement:${workspaceId}`],
  );
  const now = timestamp((await client.query<{ evaluated_at: Date | string }>(
    "SELECT clock_timestamp() AS evaluated_at",
  )).rows[0]?.evaluated_at ?? "");
  const entitlement = (await client.query<EntitlementRow>(
    `SELECT edition,status,effective_at,expires_at
    FROM workspace_entitlements WHERE workspace_id=$1`,
    [workspaceId],
  )).rows[0];
  if (!entitlement) {
    throw new ControlPlaneHttpError(403, "workspace_entitlement_missing", "This workspace has no commercial entitlement.");
  }
  const effectiveAt = timestamp(entitlement.effective_at);
  const expiresAt = timestamp(entitlement.expires_at);
  if (!now || !effectiveAt || (entitlement.expires_at !== null && !expiresAt)) {
    throw new ControlPlaneHttpError(503, "workspace_entitlement_invalid", "The workspace entitlement state is invalid.");
  }
  if (entitlement.status !== "active") {
    const known = KNOWN_INACTIVE_ENTITLEMENTS.has(entitlement.status);
    throw new ControlPlaneHttpError(
      known ? 403 : 503,
      known ? `workspace_entitlement_${entitlement.status}` : "workspace_entitlement_invalid",
      "The workspace entitlement is not active.",
    );
  }
  if (effectiveAt.getTime() > now.getTime()) {
    throw new ControlPlaneHttpError(403, "workspace_entitlement_not_effective", "The workspace entitlement is not effective yet.");
  }
  if (expiresAt && expiresAt.getTime() <= now.getTime()) {
    throw new ControlPlaneHttpError(403, "workspace_entitlement_expired", "The workspace entitlement has expired.");
  }
  if (!COMMERCIAL_EDITIONS.has(entitlement.edition)) {
    throw new ControlPlaneHttpError(403, "workspace_entitlement_edition_forbidden", "Worker fleet reads require a commercial workspace edition.");
  }
  return entitlement.edition;
}

async function readWorkers(client: PoolClient, workspaceId: string) {
  const result = await client.query<WorkerRow>(
    `WITH scoped_tokens AS (
      SELECT token_id,agent_id,status,heartbeat_timeout_sec,expires_at,
        last_used_at,last_heartbeat_at,
        CASE
          WHEN jsonb_typeof(scopes_json::jsonb)='array'
          THEN jsonb_array_length(scopes_json::jsonb)
          ELSE -1
        END AS scope_count
      FROM agent_gateway_tokens
      WHERE workspace_id=$1
      ORDER BY agent_id,
        CASE status WHEN 'active' THEN 0 WHEN 'expired' THEN 1 ELSE 2 END,
        COALESCE(last_heartbeat_at,last_used_at,created_at) DESC,
        token_id
    ), selected_tokens AS (
      SELECT DISTINCT ON (agent_id) * FROM scoped_tokens
    ), session_counts AS (
      SELECT agent_id,COUNT(*)::int AS active_session_count
      FROM agent_gateway_sessions
      WHERE workspace_id=$1 AND status='active' AND expires_at::timestamptz>clock_timestamp()
      GROUP BY agent_id
    ), recent_events AS (
      SELECT DISTINCT ON (agent_id) agent_id,status AS recent_event_status,
        created_at AS recent_event_at
      FROM runtime_events
      WHERE workspace_id=$1 AND agent_id IS NOT NULL
      ORDER BY agent_id,created_at DESC,runtime_event_id DESC
    )
    SELECT agent.agent_id,agent.name,agent.role,agent.runtime_type,agent.status,
      agent.updated_at,token.status AS token_status,token.heartbeat_timeout_sec,
      token.expires_at AS token_expires_at,token.last_used_at,
      token.last_heartbeat_at,token.scope_count,
      COALESCE(session.active_session_count,0)::int AS active_session_count,
      event.recent_event_status,event.recent_event_at
    FROM selected_tokens token
    JOIN agents agent ON agent.agent_id=token.agent_id
    LEFT JOIN session_counts session ON session.agent_id=agent.agent_id
    LEFT JOIN recent_events event ON event.agent_id=agent.agent_id
    ORDER BY agent.name,agent.agent_id
    LIMIT $2`,
    [workspaceId, WORKER_LIMIT],
  );
  return result.rows;
}

async function readEvents(client: PoolClient, workspaceId: string) {
  return (await client.query<EventRow>(
    `SELECT runtime_event_id,event_type,status,agent_id,runtime_connector_id,
      latency_ms,created_at
    FROM runtime_events
    WHERE workspace_id=$1 AND agent_id IS NOT NULL
    ORDER BY created_at DESC,runtime_event_id DESC LIMIT $2`,
    [workspaceId, EVENT_LIMIT],
  )).rows;
}

function heartbeatState(worker: WorkerRow, now: Date) {
  if (worker.token_status !== "active") return worker.token_status;
  if (worker.token_expires_at && timestamp(worker.token_expires_at)!.getTime() <= now.getTime()) return "expired";
  const heartbeat = timestamp(worker.last_heartbeat_at);
  if (!heartbeat) return "never_seen";
  const timeout = boundedCount(worker.heartbeat_timeout_sec, "heartbeat timeout");
  return now.getTime() - heartbeat.getTime() <= timeout * 1_000 ? "fresh" : "stale";
}

function publicWorker(worker: WorkerRow, now: Date) {
  const state = heartbeatState(worker, now);
  const sessions = boundedCount(worker.active_session_count, "active session count");
  return {
    agent_id: boundedText(worker.agent_id, "agent id", 128),
    name: boundedText(worker.name, "agent name", 200),
    role: boundedText(worker.role, "agent role", 128),
    runtime_type: boundedText(worker.runtime_type, "runtime type", 64),
    status: boundedText(worker.status, "agent status", 32),
    enrollment_status: boundedText(worker.token_status, "enrollment status", 32),
    heartbeat_state: state,
    heartbeat_timeout_sec: boundedCount(worker.heartbeat_timeout_sec, "heartbeat timeout"),
    last_heartbeat_at: boundedText(worker.last_heartbeat_at, "heartbeat timestamp", 64, true),
    last_used_at: boundedText(worker.last_used_at, "last-used timestamp", 64, true),
    expires_at: boundedText(worker.token_expires_at, "enrollment expiry", 64, true),
    active_session_count: sessions,
    scope_count: boundedCount(worker.scope_count, "scope count"),
    recent_event_status: boundedText(worker.recent_event_status, "event status", 64, true),
    recent_event_at: boundedText(worker.recent_event_at, "event timestamp", 64, true),
    process_state_verified: false,
    token_omitted: true,
    session_id_omitted: true,
  };
}

async function adapterRows(client: PoolClient, workspaceId: string) {
  return (await client.query<AdapterRow>(
    `WITH token_candidates AS (
      SELECT DISTINCT ON (token.agent_id) agent.runtime_type,token.agent_id,token.status,
        token.last_heartbeat_at,token.heartbeat_timeout_sec
      FROM agent_gateway_tokens token
      JOIN agents agent ON agent.agent_id=token.agent_id
      WHERE token.workspace_id=$1
        AND agent.runtime_type IN ('mock','codex','hermes','openclaw')
      ORDER BY token.agent_id,
        CASE token.status WHEN 'active' THEN 0 WHEN 'expired' THEN 1 ELSE 2 END,
        COALESCE(token.last_heartbeat_at,token.last_used_at,token.created_at) DESC,
        token.token_id
    ), scoped AS (
      SELECT * FROM token_candidates
    ), sessions AS (
      SELECT agent_id,COUNT(*)::int AS active_sessions
      FROM agent_gateway_sessions
      WHERE workspace_id=$1 AND status='active' AND expires_at::timestamptz>clock_timestamp()
      GROUP BY agent_id
    ), events AS (
      SELECT agent.runtime_type,
        COUNT(*) FILTER (WHERE event.status IN ('completed','success','ready'))::int AS successes,
        COUNT(*) FILTER (WHERE event.status IN ('failed','error','blocked'))::int AS failures
      FROM runtime_events event
      JOIN agents agent ON agent.agent_id=event.agent_id
      WHERE event.workspace_id=$1 AND event.created_at::timestamptz>clock_timestamp()-interval '24 hours'
      GROUP BY agent.runtime_type
    )
    SELECT scoped.runtime_type,COUNT(DISTINCT scoped.agent_id)::int AS enrolled_workers,
      COUNT(DISTINCT scoped.agent_id) FILTER (WHERE scoped.status='active')::int AS active_enrollments,
      COALESCE(SUM(session.active_sessions),0)::int AS active_sessions,
      COUNT(DISTINCT scoped.agent_id) FILTER (
        WHERE scoped.status='active' AND scoped.last_heartbeat_at IS NOT NULL
          AND scoped.last_heartbeat_at::timestamptz
            >=clock_timestamp()-(scoped.heartbeat_timeout_sec*interval '1 second')
      )::int AS fresh_workers,
      COUNT(DISTINCT scoped.agent_id) FILTER (
        WHERE scoped.status='active' AND scoped.last_heartbeat_at IS NOT NULL
          AND scoped.last_heartbeat_at::timestamptz
            <clock_timestamp()-(scoped.heartbeat_timeout_sec*interval '1 second')
      )::int AS stale_workers,
      MAX(scoped.last_heartbeat_at) AS last_heartbeat_at,
      COALESCE(MAX(events.successes),0)::int AS recent_successes,
      COALESCE(MAX(events.failures),0)::int AS recent_failures
    FROM scoped
    LEFT JOIN sessions session ON session.agent_id=scoped.agent_id
    LEFT JOIN events ON events.runtime_type=scoped.runtime_type
    GROUP BY scoped.runtime_type
    ORDER BY scoped.runtime_type`,
    [workspaceId],
  )).rows;
}

function adapterProjection(rows: AdapterRow[]) {
  const byName = new Map(rows.map((row) => [row.runtime_type, row]));
  const adapters = Object.fromEntries(ADAPTERS.map((adapter) => {
    const row = byName.get(adapter);
    const active = boundedCount(row?.active_enrollments ?? 0, `${adapter} active enrollments`);
    const sessions = boundedCount(row?.active_sessions ?? 0, `${adapter} active sessions`);
    const fresh = boundedCount(row?.fresh_workers ?? 0, `${adapter} fresh workers`);
    const stale = boundedCount(row?.stale_workers ?? 0, `${adapter} stale workers`);
    const failures = boundedCount(row?.recent_failures ?? 0, `${adapter} recent failures`);
    const readiness = failures > 0 || stale > 0
      ? "blocked"
      : active > 0 && sessions > 0 && fresh > 0
        ? "ready"
        : "unavailable";
    return [adapter, {
      adapter,
      ok: readiness === "ready",
      readiness,
      connector_id: null,
      trust_status: "workspace_evidence_only",
      observation_level: "postgres_ledger_summary",
      requires_confirm_run: adapter !== "mock",
      target_resource: null,
      checks: {
        enrolled_workers: boundedCount(row?.enrolled_workers ?? 0, `${adapter} enrolled workers`),
        active_enrollments: active,
        active_sessions: sessions,
        fresh_workers: fresh,
        stale_workers: stale,
        recent_successes: boundedCount(row?.recent_successes ?? 0, `${adapter} recent successes`),
        recent_failures: failures,
        last_heartbeat_at: boundedText(row?.last_heartbeat_at ?? null, `${adapter} heartbeat timestamp`, 64, true),
        process_state_verified: false,
        live_execution_performed: false,
      },
      recommended_action: readiness === "ready"
        ? `agentops workflow run-task --adapter ${adapter} --confirm-run`
        : "agentops enrollment create --agent-id <agent_id>",
      remediation: {
        status: readiness === "ready" ? "ready" : "action_required",
        primary_next_action: readiness === "ready" ? "agentops worker status" : "agentops doctor",
        missing: readiness === "ready" ? [] : ["fresh_active_workspace_worker_session"],
        commands: [],
        safety: {
          read_only: true,
          ledger_mutated: false,
          live_execution_performed: false,
          server_executes_shell: false,
          token_omitted: true,
        },
        token_omitted: true,
      },
      token_omitted: true,
    }];
  })) as unknown as Record<(typeof ADAPTERS)[number], Record<string, unknown>>;
  const ready = ADAPTERS.filter((name) => adapters[name].readiness === "ready");
  const blocked = ADAPTERS.filter((name) => adapters[name].readiness === "blocked");
  const unavailable = ADAPTERS.filter((name) => adapters[name].readiness === "unavailable");
  const recommended = (["openclaw", "hermes", "codex", "mock"] as const)
    .find((name) => adapters[name].readiness === "ready") ?? "mock";
  return {
    adapters,
    summary: {
      ready_adapters: ready,
      live_ready_adapters: ready.filter((name) => name !== "mock"),
      review_required_adapters: [],
      blocked_adapters: blocked,
      unavailable_adapters: unavailable,
      recommended_adapter: recommended,
    },
    status: blocked.length > 0 ? "degraded" : ready.length > 0 ? "ready" : "blocked",
  };
}

async function readProjection(client: PoolClient, workspaceId: string, kind: HumanWorkerReadKind) {
  const now = timestamp((await client.query<{ evaluated_at: Date | string }>(
    "SELECT clock_timestamp() AS evaluated_at",
  )).rows[0]?.evaluated_at ?? "");
  if (!now) throw new ControlPlaneHttpError(503, "human_worker_fleet_state_invalid", "Database time is invalid.");
  const rawWorkers = await readWorkers(client, workspaceId);
  const events = await readEvents(client, workspaceId);
  const adapterData = await adapterRows(client, workspaceId);
  const runCounts = await client.query<{ completed: number; recent: number }>(
    `SELECT COUNT(*) FILTER (WHERE status='completed')::int AS completed,
        COUNT(*)::int AS recent FROM (
          SELECT status FROM runs WHERE workspace_id=$1
          ORDER BY started_at DESC,run_id DESC LIMIT $2
        ) bounded`,
    [workspaceId, WORKER_LIMIT],
  );
  const taskCounts = await client.query<{ pending: number; stuck: number }>(
    `SELECT COUNT(*) FILTER (WHERE status IN ('backlog','planned'))::int AS pending,
        COUNT(*) FILTER (WHERE status='running' AND updated_at::timestamptz<clock_timestamp()-interval '15 minutes')::int AS stuck
      FROM tasks WHERE workspace_id=$1`,
    [workspaceId],
  );
  const workers = rawWorkers.map((row) => publicWorker(row, now));
  const adapter = adapterProjection(adapterData);
  const fresh = workers.filter((worker) => worker.heartbeat_state === "fresh");
  const stale = workers.filter((worker) => worker.heartbeat_state === "stale");
  const activeSessions = workers.reduce((sum, worker) => sum + worker.active_session_count, 0);
  const lanes = workers.map((worker) => ({
    lane_id: safeRef("fleet_lane", `${workspaceId}:${worker.agent_id}`),
    lane_type: "commercial_gateway_worker",
    adapter: worker.runtime_type,
    agent_id: worker.agent_id,
    agent_name: worker.name,
    workspace_id: workspaceId,
    runtime_type: worker.runtime_type,
    status: worker.status,
    health: worker.heartbeat_state === "fresh" && worker.active_session_count > 0 ? "pass" : "warn",
    heartbeat_state: worker.heartbeat_state,
    session_state: worker.active_session_count > 0 ? "active" : "missing",
    active_session_count: worker.active_session_count,
    last_seen_at: worker.last_heartbeat_at ?? worker.last_used_at,
    expires_at: worker.expires_at,
    scope_count: worker.scope_count,
    next_action: worker.heartbeat_state === "fresh" && worker.active_session_count > 0
      ? "agentops worker status"
      : "agentops doctor",
    process_state_verified: false,
    control_allowed: false,
    token_omitted: true,
    session_id_omitted: true,
  }));
  const publicEvents = events.map((event) => ({
    event_ref: safeRef("runtime_event", String(boundedText(event.runtime_event_id, "runtime event id", 128))),
    event_type: boundedText(event.event_type, "event type", 160),
    status: boundedText(event.status, "event status", 64),
    agent_id: boundedText(event.agent_id, "event agent id", 128, true),
    connector_ref: event.runtime_connector_id
      ? safeRef("connector", String(boundedText(event.runtime_connector_id, "connector id", 128)))
      : null,
    latency_ms: event.latency_ms === null ? null : boundedCount(event.latency_ms, "event latency"),
    created_at: boundedText(event.created_at, "event timestamp", 64),
    raw_payload_omitted: true,
  }));

  if (kind === "adapter-readiness") {
    return {
      provider: "agentops-worker",
      operation: "adapter_readiness",
      status: adapter.status,
      summary: adapter.summary,
      adapters: adapter.adapters,
      contract: "commercial readiness is derived from workspace-scoped PostgreSQL enrollment, session, heartbeat, and runtime evidence",
      live_execution_performed: false,
      python_proxy_performed: false,
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      token_omitted: true,
    };
  }

  if (kind === "fleet") {
    const warnings = lanes.filter((lane) => lane.health === "warn").length;
    return {
      provider: "agentops-worker",
      operation: "fleet_view",
      status: warnings > 0 ? "attention" : "ready",
      summary: {
        lane_count: lanes.length,
        lane_counts: { commercial_gateway_worker: lanes.length },
        health_counts: { pass: lanes.length - warnings, warn: warnings },
        local_daemon_count: 0,
        running_local_daemons: 0,
        active_service_workers: fresh.length,
        stale_service_workers: stale.length,
        execution_capacity_workers: fresh.filter((worker) => worker.active_session_count > 0).length,
        host_managed_workers: 0,
        api_managed_daemons: 0,
        remote_worker_count: workers.length,
        fresh_remote_enrollments: fresh.length,
        stale_remote_enrollments: stale.length,
        never_seen_remote_enrollments: workers.filter((worker) => worker.heartbeat_state === "never_seen").length,
        active_remote_sessions: activeSessions,
        stuck_worker_tasks: boundedCount(taskCounts.rows[0]?.stuck ?? 0, "stuck task count"),
        stuck_workflow_jobs: 0,
        recommended_adapter: adapter.summary.recommended_adapter,
      },
      lanes,
      next_actions: warnings > 0 ? ["agentops doctor", "agentops worker status"] : ["agentops worker status"],
      contract: "read-only commercial workspace fleet view; host process state is intentionally not inferred",
      safety: {
        read_only: true,
        live_execution_performed: false,
        token_omitted: true,
        session_id_omitted: true,
        raw_prompt_omitted: true,
      },
      python_proxy_performed: false,
      token_omitted: true,
      live_execution_performed: false,
    };
  }

  const completed = boundedCount(runCounts.rows[0]?.completed ?? 0, "completed run count");
  const pending = boundedCount(taskCounts.rows[0]?.pending ?? 0, "pending task count");
  const stuck = boundedCount(taskCounts.rows[0]?.stuck ?? 0, "stuck task count");
  return {
    provider: "agentops-worker",
    operation: "worker_status",
    status: stale.length > 0 ? "attention" : fresh.length > 0 ? "running" : "ready",
    worker_count: workers.length,
    running_workers: 0,
    active_service_workers: fresh.length,
    stale_service_workers: stale.length,
    execution_capacity_workers: fresh.filter((worker) => worker.active_session_count > 0).length,
    recent_completed_runs: completed,
    pending_worker_tasks: pending,
    stuck_worker_tasks: stuck,
    stuck_workflow_jobs: 0,
    remote_worker_count: workers.length,
    total_remote_enrollments: workers.length,
    active_remote_enrollments: workers.filter((worker) => worker.enrollment_status === "active").length,
    fresh_remote_enrollments: fresh.length,
    stale_remote_enrollments: stale.length,
    never_seen_remote_enrollments: workers.filter((worker) => worker.heartbeat_state === "never_seen").length,
    active_remote_sessions: activeSessions,
    remote_worker_health: {
      status: stale.length > 0 ? "attention" : "ready",
      fresh_enrollments: fresh.length,
      stale_enrollments: stale.length,
      token_omitted: true,
    },
    service_workers: workers,
    adapter_readiness: adapter.summary,
    fleet_health: {
      overall: stale.length > 0 || stuck > 0 ? "attention" : "ready",
      contract: "workspace-scoped PostgreSQL evidence",
      gates: [
        { id: "fresh_workers", status: fresh.length > 0 ? "pass" : "warn", summary: `${fresh.length} fresh worker(s)` },
        { id: "stuck_tasks", status: stuck > 0 ? "warn" : "pass", summary: `${stuck} stuck task(s)` },
      ],
      recommended_actions: stale.length > 0 || stuck > 0 ? ["agentops doctor"] : ["agentops worker status"],
      token_omitted: true,
    },
    daemons: [],
    workers,
    recent_runs: [],
    recent_tasks: [],
    stuck_tasks: [],
    stuck_workflow_job_refs: [],
    recent_events: publicEvents,
    bounds: { workers: WORKER_LIMIT, recent_events: EVENT_LIMIT },
    python_proxy_performed: false,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    token_omitted: true,
  };
}

export async function getHumanWorkerFleetRead(request: NextRequest, kind: HumanWorkerReadKind) {
  if (legacyPythonProxyAllowed()) {
    return proxyControlPlaneRequest(request, `/workers/${kind}`);
  }
  try {
    const workspace = requestedWorkspace(request);
    const body = await withPostgresTransaction(async (client) => {
      const identity = await authenticateHumanMember(client, request.headers, workspace);
      const role = identity.membershipRole.trim().toLowerCase();
      if (!HUMAN_WORKER_READ_ROLES.has(role)) {
        throw new ControlPlaneHttpError(
          403,
          "human_worker_fleet_role_forbidden",
          "Worker fleet reads require operator, reviewer, approver, workspace-admin, or owner authority.",
        );
      }
      const edition = await activeCommercialEntitlement(client, identity.workspaceId);
      const projection = await readProjection(client, identity.workspaceId, kind);
      await appendAudit(client, {
        workspaceId: identity.workspaceId,
        actorType: "user",
        actorId: identity.userId,
        action: `human.worker_${kind.replaceAll("-", "_")}_read`,
        entityType: "workers",
        entityId: kind,
        metadata: {
          membership_role: role,
          route: `GET /api/mis/workers/${kind}`,
          response_bounded: true,
          raw_payload_omitted: true,
          session_credential_omitted: true,
          token_omitted: true,
        },
        requestHash: stableHash({
          workspace_id: identity.workspaceId,
          user_id: identity.userId,
          operation: `human.worker_${kind.replaceAll("-", "_")}_read`,
        }),
      });
      return {
        ok: true,
        control_plane: "typescript_postgres",
        workspace_id: identity.workspaceId,
        entitlement_edition: edition,
        ...projection,
        audit_recorded: true,
        credentials_omitted: true,
      };
    });
    return NextResponse.json(body, { status: 200, headers: PRIVATE_HEADERS });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, { status: failure.status, headers: PRIVATE_HEADERS });
  }
}
