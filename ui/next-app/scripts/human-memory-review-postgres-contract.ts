import assert from "node:assert/strict";
import { createHmac, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

import { NextRequest } from "next/server";
import { Client } from "pg";

import { POST as reviewMemory } from "../app/api/mis/memories/[memoryId]/[decision]/route";
import { closeControlPlanePoolForTests } from "../src/server/controlPlane/db";
import { createPostgresRoleBoundaryFixture } from "./postgres-role-boundary-test-helper";

const BASE_DSN = String(process.env.AGENTOPS_POSTGRES_DSN || "").trim();
const ORIGIN = "https://mis.example.test";
const HOST = "mis.example.test";
const WORKSPACE = "ws_memory_review";
const FOREIGN_WORKSPACE = "ws_memory_review_foreign";
const REVIEWER_TOKEN = randomBytes(32).toString("base64url");
const OWNER_TOKEN = randomBytes(32).toString("base64url");
const OPERATOR_TOKEN = randomBytes(32).toString("base64url");
const HMAC_KEY = randomBytes(48).toString("base64url");
const SECRET_CANARY = "memory-review-sensitive-canary-must-not-leak";
let activeStage = "startup";
let observedStatus: number | null = null;
let observedError = "";

type Deployment = "production" | "shared" | "free_local";
type Decision = "approve" | "reject";
type RouteResult = Readonly<{
  response: Response;
  body: Record<string, unknown>;
}>;

function hmac(label: string, value: string) {
  return createHmac("sha256", HMAC_KEY)
    .update(`${label}:${value}`, "utf8")
    .digest("hex");
}

function headers(
  token: string,
  input: Readonly<{
    workspaceId?: string;
    csrf?: string;
    idempotencyKey?: string;
    origin?: string;
    machineCredential?: boolean;
  }> = {},
) {
  const result = new Headers({
    cookie: `agentops_human_session=${token}`,
    host: HOST,
    origin: input.origin === undefined ? ORIGIN : input.origin,
    "x-agentops-workspace-id": input.workspaceId || WORKSPACE,
    "x-agentops-csrf": input.csrf === undefined ? hmac("csrf", token) : input.csrf,
    "idempotency-key": input.idempotencyKey || "memory-review-contract-key-0001",
    "content-type": "application/json",
  });
  if (input.machineCredential) {
    result.set("authorization", "Bearer machine-credential-forbidden");
  }
  return result;
}

function request(
  token: string,
  memoryId: string,
  decision: string,
  input: Readonly<{
    deployment?: Deployment;
    controlPlaneMode?: "postgres" | "proxy";
    workspaceId?: string;
    headerWorkspaceId?: string;
    query?: string;
    body?: Record<string, unknown> | string;
    csrf?: string;
    idempotencyKey?: string;
    origin?: string;
    machineCredential?: boolean;
  }> = {},
) {
  process.env.AGENTOPS_DEPLOYMENT_MODE = input.deployment || "production";
  process.env.AGENTOPS_CONTROL_PLANE_MODE = input.controlPlaneMode
    || (input.deployment === "free_local" ? "proxy" : "postgres");
  const body = typeof input.body === "string"
    ? input.body
    : JSON.stringify(input.body ?? {
      workspace_id: input.workspaceId || WORKSPACE,
    });
  return new NextRequest(
    `${ORIGIN}/api/mis/memories/${encodeURIComponent(memoryId)}/${encodeURIComponent(decision)}${input.query || ""}`,
    {
      method: "POST",
      headers: headers(token, {
        workspaceId: input.headerWorkspaceId || input.workspaceId,
        csrf: input.csrf,
        idempotencyKey: input.idempotencyKey,
        origin: input.origin,
        machineCredential: input.machineCredential,
      }),
      body,
    },
  );
}

async function call(
  token: string,
  memoryId: string,
  decision: string,
  input?: Parameters<typeof request>[3],
): Promise<RouteResult> {
  const response = await reviewMemory(
    request(token, memoryId, decision, input),
    { params: Promise.resolve({ memoryId, decision }) },
  );
  const body = await response.json() as Record<string, unknown>;
  observedStatus = response.status;
  observedError = String(body.error || "");
  return { response, body };
}

function denied(result: RouteResult, status: number, error: string) {
  assert.equal(result.response.status, status);
  assert.equal(result.body.ok, false);
  assert.equal(result.body.error, error);
  assert.equal(result.body.token_omitted, true);
  assert.equal(Object.hasOwn(result.body, "memory"), false);
  assert.equal(result.response.headers.get("cache-control"), "no-store");
}

async function seed(client: Client) {
  const now = new Date().toISOString();
  const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  await client.query(
    `INSERT INTO users(user_id,name,email,role,created_at) VALUES
      ('usr_memory_reviewer','Memory reviewer','reviewer@example.invalid','reviewer',$1),
      ('usr_memory_owner','Memory owner','owner@example.invalid','owner',$1),
      ('usr_memory_operator','Memory operator','operator@example.invalid','operator',$1)`,
    [now],
  );
  await client.query(
    `INSERT INTO workspace_memberships(
      workspace_id,user_id,role,status,created_at,updated_at
    ) VALUES
      ($1,'usr_memory_reviewer','reviewer','active',$2,$2),
      ($1,'usr_memory_owner','owner','active',$2,$2),
      ($1,'usr_memory_operator','operator','active',$2,$2)`,
    [WORKSPACE, now],
  );
  await client.query(
    `INSERT INTO human_sessions(
      session_id,user_id,session_hash,status,created_at,expires_at,last_seen_at,revoked_at
    ) VALUES
      ('hsess_memory_reviewer','usr_memory_reviewer',$1,'active',$4,$5,$4,NULL),
      ('hsess_memory_owner','usr_memory_owner',$2,'active',$4,$5,$4,NULL),
      ('hsess_memory_operator','usr_memory_operator',$3,'active',$4,$5,$4,NULL)`,
    [
      hmac("session", REVIEWER_TOKEN),
      hmac("session", OWNER_TOKEN),
      hmac("session", OPERATOR_TOKEN),
      now,
      future,
    ],
  );
  await client.query(
    `INSERT INTO workspace_entitlements(
      workspace_id,edition,status,capabilities_json,max_agents,
      max_active_enrollments,max_active_sessions_per_agent,max_monthly_runs,
      max_monthly_cost_usd,max_concurrent_runs,effective_at,expires_at
    ) VALUES
      ($1,'team_governance','active','{}',20,20,20,100,1000,10,
        clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 year'),
      ($2,'enterprise_byoc','active','{}',20,20,20,100,1000,10,
        clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 year')`,
    [WORKSPACE, FOREIGN_WORKSPACE],
  );
  const memoryIds = [
    "mem_review_approve",
    "mem_review_reject",
    "mem_review_race",
    "mem_review_entitlement",
    "mem_review_foreign",
  ];
  for (const memoryId of memoryIds) {
    const workspaceId = memoryId.endsWith("foreign")
      ? FOREIGN_WORKSPACE
      : WORKSPACE;
    await client.query(
      `INSERT INTO memories(
        memory_id,workspace_id,scope,memory_type,canonical_text,source_type,
        source_ref,project_id,task_id,run_id,agent_id,confidence,review_status,
        owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,
        created_at,updated_at
      ) VALUES(
        $1,$2,'project','project_context',$3,'manual',$3,NULL,NULL,NULL,NULL,
        0.9,'candidate',NULL,NULL,NULL,$4,$5,$5
      )`,
      [memoryId, workspaceId, SECRET_CANARY, JSON.stringify([SECRET_CANARY]), now],
    );
  }
}

async function startProxyProbe() {
  let calls = 0;
  const paths: string[] = [];
  const server = createServer((incoming, response) => {
    calls += 1;
    paths.push(String(incoming.url || ""));
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({
      ok: true,
      free_local_python_proxy: true,
      path: incoming.url,
    }));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  return {
    base: `http://127.0.0.1:${address.port}/api`,
    calls: () => calls,
    paths: () => paths,
    close: () => new Promise<void>((resolve, reject) =>
      server.close((error) => error ? reject(error) : resolve())),
  };
}

async function staticBoundary() {
  const source = (await Promise.all([
    "../src/server/controlPlane/memoryReviews.ts",
    "../app/api/mis/memories/[memoryId]/[decision]/route.ts",
  ].map((path) => readFile(new URL(path, import.meta.url), "utf8")))).join("\n");
  assert.match(source, /legacyPythonProxyAllowed/);
  assert.match(source, /python_proxy_performed: false/);
  assert.match(source, /workspace_entitlements/);
  assert.match(source, /authenticateHumanReviewer/);
  assert.match(source, /validateMemoryReviewQuery/);
  assert.match(source, /validateMemoryReviewBody/);
  assert.match(source, /pg_advisory_xact_lock/);
  assert.match(source, /FOR UPDATE/);
  assert.match(source, /review_status='candidate'/);
  assert.match(source, /appendAudit/);
  assert.match(source, /appendRuntimeEvent/);
  assert.doesNotMatch(source, /server\.py|sqlite|child_process|\bfetch\s*\(/i);
}

async function run() {
  assert.ok(BASE_DSN, "AGENTOPS_POSTGRES_DSN is required");
  activeStage = "static_boundary";
  await staticBoundary();
  const environmentNames = [
    "AGENTOPS_ALLOWED_ORIGINS",
    "AGENTOPS_API_BASE",
    "AGENTOPS_CONTROL_PLANE_MODE",
    "AGENTOPS_DEPLOYMENT_MODE",
    "AGENTOPS_HUMAN_SESSION_HMAC_KEY",
    "AGENTOPS_POSTGRES_DSN",
    "AGENTOPS_POSTGRES_SCHEMA",
    "AGENTOPS_POSTGRES_RUNTIME_API_SCHEMA",
    "AGENTOPS_POSTGRES_RUNTIME_ROLE",
  ];
  const originalEnvironment = Object.fromEntries(
    environmentNames.map((name) => [name, process.env[name]]),
  );
  const fixture = await createPostgresRoleBoundaryFixture(BASE_DSN, "memory_review");
  const proxy = await startProxyProbe();
  let restoreRuntime: () => void = () => undefined;
  try {
    activeStage = "postgres_16";
    const version = await fixture.owner.query<{ server_version_num: string }>(
      "SHOW server_version_num",
    );
    assert.equal(Math.floor(Number(version.rows[0].server_version_num) / 10_000), 16);
    assert.equal(fixture.migration.schema_contract, "agentops_commercial_postgres_v11");
    activeStage = "seed";
    await seed(fixture.owner);
    restoreRuntime = fixture.activateRuntimeEnvironment();
    process.env.AGENTOPS_ALLOWED_ORIGINS = ORIGIN;
    process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = HMAC_KEY;
    process.env.AGENTOPS_API_BASE = proxy.base;

    activeStage = "production_direct";
    const approved = await call(REVIEWER_TOKEN, "mem_review_approve", "approve", {
      deployment: "production",
      idempotencyKey: "memory-review-production-0001",
    });
    assert.equal(approved.response.status, 200);
    assert.equal(approved.body.control_plane, "typescript_postgres");
    assert.equal(approved.body.review_status, "approved");
    assert.equal(approved.body.outcome, "updated");
    assert.equal(approved.body.entitlement_edition, "team_governance");
    assert.equal(approved.body.audit_recorded, true);
    assert.equal(approved.body.runtime_event_recorded, true);
    assert.equal(approved.body.python_proxy_performed, false);
    assert.equal(approved.response.headers.get("cache-control"), "no-store");
    assert.equal(
      approved.response.headers.get("vary"),
      "Cookie, Origin, X-AgentOps-Workspace-Id, X-AgentOps-CSRF, Idempotency-Key",
    );
    assert.equal(JSON.stringify(approved.body).includes(SECRET_CANARY), false);
    const publicMemory = approved.body.memory as Record<string, unknown>;
    assert.equal(Object.hasOwn(publicMemory, "owner_user_id"), false);
    assert.equal(publicMemory.owner_user_id_omitted, true);
    assert.equal(publicMemory.raw_content_omitted, true);

    activeStage = "commercial_proxy_fail_closed";
    const commercialProxy = await call(
      REVIEWER_TOKEN,
      "mem_review_reject",
      "reject",
      {
        deployment: "production",
        controlPlaneMode: "proxy",
        idempotencyKey: "memory-review-commercial-proxy",
      },
    );
    denied(commercialProxy, 503, "human_session_direct_route_required");
    assert.equal(commercialProxy.body.python_proxy_performed, false);
    assert.equal(proxy.calls(), 0);

    activeStage = "idempotent_replay";
    const replay = await call(REVIEWER_TOKEN, "mem_review_approve", "approve", {
      deployment: "shared",
      idempotencyKey: "memory-review-production-0001",
    });
    assert.equal(replay.response.status, 200);
    assert.equal(replay.body.outcome, "unchanged");
    assert.equal(replay.body.audit_recorded, true);
    assert.equal(replay.body.runtime_event_recorded, true);
    assert.equal(proxy.calls(), 0);

    activeStage = "strict_input";
    denied(
      await call(REVIEWER_TOKEN, "mem_review_reject", "approved", {
        idempotencyKey: "memory-review-path-decision",
      }),
      404,
      "memory_review_not_found",
    );
    denied(
      await call(REVIEWER_TOKEN, "bad/memory", "approve", {
        idempotencyKey: "memory-review-path-identifier",
      }),
      400,
      "memory_id_invalid",
    );
    denied(
      await call(REVIEWER_TOKEN, "mem_review_reject", "reject", {
        query: "?workspace_id=ws_memory_review",
        idempotencyKey: "memory-review-query-forbidden",
      }),
      400,
      "memory_review_query_unsupported",
    );
    denied(
      await call(REVIEWER_TOKEN, "mem_review_reject", "reject", {
        body: { workspace_id: WORKSPACE, reason: SECRET_CANARY },
        idempotencyKey: "memory-review-body-unknown",
      }),
      400,
      "memory_review_field_unsupported",
    );
    denied(
      await call(REVIEWER_TOKEN, "mem_review_reject", "reject", {
        body: { workspace_id: WORKSPACE, owner_user_id: "usr_attacker" },
        idempotencyKey: "memory-review-body-owned",
      }),
      403,
      "human_actor_server_owned",
    );
    denied(
      await call(REVIEWER_TOKEN, "mem_review_reject", "reject", {
        body: "[]",
        idempotencyKey: "memory-review-body-shape",
      }),
      400,
      "invalid_json",
    );
    denied(
      await call(REVIEWER_TOKEN, "mem_review_reject", "reject", {
        idempotencyKey: "short",
      }),
      400,
      "idempotency_key_required",
    );

    activeStage = "human_session_security";
    denied(
      await call(REVIEWER_TOKEN, "mem_review_reject", "reject", {
        csrf: "0".repeat(64),
        idempotencyKey: "memory-review-csrf-invalid",
      }),
      403,
      "csrf_validation_failed",
    );
    denied(
      await call(REVIEWER_TOKEN, "mem_review_reject", "reject", {
        origin: "https://attacker.invalid",
        idempotencyKey: "memory-review-origin-invalid",
      }),
      403,
      "origin_validation_failed",
    );
    denied(
      await call(REVIEWER_TOKEN, "mem_review_reject", "reject", {
        machineCredential: true,
        idempotencyKey: "memory-review-machine-invalid",
      }),
      401,
      "machine_credential_not_allowed",
    );
    denied(
      await call(OPERATOR_TOKEN, "mem_review_reject", "reject", {
        idempotencyKey: "memory-review-role-forbidden",
      }),
      403,
      "human_role_forbidden",
    );
    denied(
      await call(REVIEWER_TOKEN, "mem_review_foreign", "reject", {
        workspaceId: FOREIGN_WORKSPACE,
        headerWorkspaceId: WORKSPACE,
        idempotencyKey: "memory-review-workspace-mismatch",
      }),
      403,
      "forbidden",
    );

    activeStage = "single_winner";
    const race = await Promise.all([
      call(REVIEWER_TOKEN, "mem_review_race", "approve", {
        idempotencyKey: "memory-review-race-approve",
      }),
      call(OWNER_TOKEN, "mem_review_race", "reject", {
        idempotencyKey: "memory-review-race-reject",
      }),
    ]);
    assert.equal(race.filter((result) => result.response.status === 200).length, 1);
    assert.equal(race.filter((result) => result.response.status === 409).length, 1);
    const raceState = await fixture.owner.query<{
      review_status: string;
      requests: string;
    }>(
      `SELECT memory.review_status,
        (SELECT count(*)::text FROM human_memory_review_requests request
          WHERE request.memory_id=memory.memory_id) AS requests
      FROM memories memory WHERE memory.memory_id='mem_review_race'`,
    );
    assert.ok(["approved", "rejected"].includes(raceState.rows[0].review_status));
    assert.equal(raceState.rows[0].requests, "1");

    activeStage = "entitlement";
    await fixture.owner.query(
      "UPDATE workspace_entitlements SET status='suspended' WHERE workspace_id=$1",
      [WORKSPACE],
    );
    denied(
      await call(REVIEWER_TOKEN, "mem_review_entitlement", "approve", {
        idempotencyKey: "memory-review-entitlement-suspended",
      }),
      403,
      "workspace_entitlement_suspended",
    );
    await fixture.owner.query(
      "UPDATE workspace_entitlements SET status='active',edition='free_local' WHERE workspace_id=$1",
      [WORKSPACE],
    );
    denied(
      await call(REVIEWER_TOKEN, "mem_review_entitlement", "approve", {
        idempotencyKey: "memory-review-entitlement-edition",
      }),
      403,
      "workspace_entitlement_edition_forbidden",
    );

    activeStage = "evidence";
    const evidence = await fixture.owner.query<{
      audit_count: string;
      runtime_count: string;
      request_count: string;
    }>(
      `SELECT
        (SELECT count(*)::text FROM audit_logs
          WHERE workspace_id=$1 AND action IN ('memory.approved','memory.rejected')) AS audit_count,
        (SELECT count(*)::text FROM runtime_events
          WHERE workspace_id=$1 AND event_type IN ('memory.approved','memory.rejected')) AS runtime_count,
        (SELECT count(*)::text FROM human_memory_review_requests
          WHERE workspace_id=$1) AS request_count`,
      [WORKSPACE],
    );
    assert.equal(evidence.rows[0].audit_count, "2");
    assert.equal(evidence.rows[0].runtime_count, "2");
    assert.equal(evidence.rows[0].request_count, "2");
    const evidenceJson = JSON.stringify(await fixture.owner.query(
      `SELECT action,entity_type,entity_id,metadata_json FROM audit_logs
      WHERE workspace_id=$1 AND action IN ('memory.approved','memory.rejected')`,
      [WORKSPACE],
    ));
    assert.equal(evidenceJson.includes(SECRET_CANARY), false);

    activeStage = "free_local_proxy";
    const freeLocal = await call(REVIEWER_TOKEN, "mem_review_reject", "reject", {
      deployment: "free_local",
      idempotencyKey: "memory-review-free-local-proxy",
    });
    assert.equal(freeLocal.response.status, 200);
    assert.equal(freeLocal.body.free_local_python_proxy, true);
    assert.equal(proxy.calls(), 1);
    assert.deepEqual(proxy.paths(), [
      "/api/memories/mem_review_reject/reject",
    ]);
    assert.equal(freeLocal.response.headers.get("cache-control"), "no-store");

    console.log(JSON.stringify({
      ok: true,
      contract: "human_memory_review_postgres_v1",
      postgres_major: 16,
      schema_contract: fixture.migration.schema_contract,
      production_and_shared_typescript_postgres: true,
      production_python_proxy_calls: 0,
      free_local_python_proxy_preserved: true,
      commercial_proxy_fail_closed_503: true,
      workspace_session_binding: true,
      origin_csrf_machine_boundary: true,
      strict_path_query_body: true,
      reviewer_rbac_verified: true,
      active_commercial_entitlement_required: true,
      cross_workspace_fail_closed: true,
      idempotent_replay_verified: true,
      single_winner_verified: true,
      audit_runtime_evidence_verified: true,
      runtime_role_boundary_verified: true,
      sensitive_fields_omitted: true,
      no_store_verified: true,
      credentials_omitted: true,
      token_omitted: true,
    }));
  } finally {
    await closeControlPlanePoolForTests().catch(() => undefined);
    restoreRuntime();
    for (const name of environmentNames) {
      const value = originalEnvironment[name];
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
    await proxy.close();
    await fixture.cleanup();
  }
}

run().catch((error: unknown) => {
  const failure = error && typeof error === "object"
    ? error as { message?: unknown }
    : {};
  console.log(JSON.stringify({
    ok: false,
    contract: "human_memory_review_postgres_v1",
    stage: activeStage,
    observed_status: observedStatus,
    observed_error: observedError,
    error: String(failure.message || "contract_failed").slice(0, 240),
    credentials_omitted: true,
    row_data_omitted: true,
    token_omitted: true,
  }));
  process.exitCode = 1;
});
