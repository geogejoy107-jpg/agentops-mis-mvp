import assert from "node:assert/strict";
import { createHash, createHmac, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

import { NextRequest } from "next/server";
import { Client } from "pg";

import { GET as getReadiness } from "../app/api/mis/workers/adapter-readiness/route";
import { GET as getFleet } from "../app/api/mis/workers/fleet/route";
import { GET as getStatus } from "../app/api/mis/workers/status/route";
import { closeControlPlanePoolForTests } from "../src/server/controlPlane/db";
import { createPostgresRoleBoundaryFixture } from "./postgres-role-boundary-test-helper";

const BASE_DSN = String(process.env.AGENTOPS_POSTGRES_DSN || "").trim();
const WORKSPACE = "ws_worker_fleet";
const FOREIGN_WORKSPACE = "ws_worker_fleet_foreign";
const SECRET_CANARY = "worker-fleet-foreign-secret-must-not-leak";
const OPERATOR_TOKEN = randomBytes(32).toString("base64url");
const VIEWER_TOKEN = randomBytes(32).toString("base64url");
const HMAC_KEY = randomBytes(48).toString("base64url");
let stage = "startup";
let observedStatus: number | null = null;
let observedError = "";

type Kind = "status" | "fleet" | "adapter-readiness";
type Result = { response: Response; body: Record<string, unknown> };

function hmac(label: string, token: string) {
  return createHmac("sha256", HMAC_KEY)
    .update(`${label}:${token}`, "utf8")
    .digest("hex");
}

function sha(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

async function reserveRunCost(client: Client, runId: string, createdAt: string) {
  await client.query(
    `INSERT INTO run_cost_reservations(
      reservation_id,workspace_id,run_id,billing_class,billing_month_utc,state,
      estimated_cost_usd,observed_cost_usd,idempotency_key_hash,request_hash,
      reserved_at,expires_at,updated_at
    ) VALUES($1,$2,$3,'historical_execution',
      date_trunc('month',$6::timestamptz)::date,'reserved',0.001,0,$4,$5,
      $6::timestamptz,$6::timestamptz+interval '1 hour',$6::timestamptz)`,
    [
      `rsv_${runId}`,
      WORKSPACE,
      runId,
      sha(`worker-fleet-idempotency:${runId}`),
      sha(`worker-fleet-request:${runId}`),
      createdAt,
    ],
  );
}

function request(kind: Kind, input: Readonly<{
  token?: string;
  headerWorkspace?: string;
  queryWorkspace?: string;
  machineCredential?: boolean;
  unsupportedQuery?: boolean;
}> = {}) {
  const url = new URL(`https://mis.example.test/api/mis/workers/${kind}`);
  if (input.queryWorkspace) url.searchParams.set("workspace_id", input.queryWorkspace);
  if (input.unsupportedQuery) url.searchParams.set("limit", "999999");
  const headers = new Headers({
    cookie: `agentops_human_session=${input.token || OPERATOR_TOKEN}`,
    "x-agentops-workspace-id": input.headerWorkspace || WORKSPACE,
  });
  if (input.machineCredential) headers.set("authorization", "Bearer forbidden-machine-credential");
  return new NextRequest(url, { method: "GET", headers });
}

async function call(kind: Kind, input?: Parameters<typeof request>[1]): Promise<Result> {
  const route = kind === "status" ? getStatus : kind === "fleet" ? getFleet : getReadiness;
  const response = await route(request(kind, input));
  const body = await response.json() as Record<string, unknown>;
  observedStatus = response.status;
  observedError = String(body.error || "");
  return { response, body };
}

function denied(result: Result, status: number, error: string) {
  assert.equal(result.response.status, status);
  assert.equal(result.body.error, error);
  assert.equal(result.body.token_omitted, true);
  assert.equal(Object.hasOwn(result.body, "workers"), false);
  assert.equal(Object.hasOwn(result.body, "lanes"), false);
  assert.equal(Object.hasOwn(result.body, "adapters"), false);
}

async function seed(client: Client) {
  const now = new Date().toISOString();
  const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  await client.query(
    `INSERT INTO users(user_id,name,email,role,created_at) VALUES
      ('usr_worker_operator','Worker operator','worker-operator@example.invalid','operator',$1),
      ('usr_worker_viewer','Worker viewer','worker-viewer@example.invalid','viewer',$1),
      ('usr_worker_owner',$2,$3,'owner',$1)`,
    [now, SECRET_CANARY, `${SECRET_CANARY}@example.invalid`],
  );
  await client.query(
    `INSERT INTO workspace_memberships(
      workspace_id,user_id,role,status,created_at,updated_at
    ) VALUES
      ($1,'usr_worker_operator','operator','active',$2,$2),
      ($1,'usr_worker_viewer','viewer','active',$2,$2)`,
    [WORKSPACE, now],
  );
  await reserveRunCost(client, "run_worker_completed", now);
  await client.query(
    `INSERT INTO human_sessions(
      session_id,user_id,session_hash,status,created_at,expires_at,last_seen_at,revoked_at
    ) VALUES
      ('hsess_worker_operator','usr_worker_operator',$1,'active',$3,$4,$3,NULL),
      ('hsess_worker_viewer','usr_worker_viewer',$2,'active',$3,$4,$3,NULL)`,
    [hmac("session", OPERATOR_TOKEN), hmac("session", VIEWER_TOKEN), now, future],
  );
  await client.query(
    `INSERT INTO workspace_entitlements(
      workspace_id,edition,status,capabilities_json,max_agents,
      max_active_enrollments,max_active_sessions_per_agent,max_monthly_runs,
      max_monthly_cost_usd,max_concurrent_runs,effective_at,expires_at
    ) VALUES
      ($1,'team_governance','active','{}',100,100,20,1000,1000,50,
        clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 year'),
      ($2,'enterprise_byoc','active','{}',100,100,20,1000,1000,50,
        clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 year')`,
    [WORKSPACE, FOREIGN_WORKSPACE],
  );

  for (let index = 0; index < 55; index += 1) {
    const agentId = `agt_worker_${String(index).padStart(2, "0")}`;
    const runtime = index % 4 === 0 ? "openclaw" : index % 4 === 1 ? "hermes" : index % 4 === 2 ? "codex" : "mock";
    const heartbeat = index === 1
      ? new Date(Date.now() - 30 * 60 * 1000).toISOString()
      : new Date(Date.now() - index * 1000).toISOString();
    await client.query(
      `INSERT INTO agents(
        agent_id,name,role,description,runtime_type,model_provider,model_name,
        status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,
        created_at,updated_at
      ) VALUES($1,$2,'worker',NULL,$3,$3,NULL,'running','standard','[]',10,
        'usr_worker_owner',$4,$4)`,
      [agentId, `Worker ${String(index).padStart(2, "0")}`, runtime, now],
    );
    await client.query(
      `INSERT INTO agent_gateway_tokens(
        token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,
        heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at
      ) VALUES($1,$2,$3,$4,'["tasks:read","tasks:claim"]','active',NULL,300,
        $5,$6,NULL,$5,$7)`,
      [`tok_worker_${index}`, randomBytes(32).toString("hex"), WORKSPACE, agentId, now, future, heartbeat],
    );
    await client.query(
      `INSERT INTO agent_gateway_sessions(
        session_id,session_hash,parent_token_id,workspace_id,agent_id,scopes_json,
        status,created_at,expires_at,revoked_at,last_used_at
      ) VALUES($1,$2,$3,$4,$5,'["tasks:read"]','active',$6,$7,NULL,$6)`,
      [`ags_worker_${index}`, randomBytes(32).toString("hex"), `tok_worker_${index}`, WORKSPACE, agentId, now, future],
    );
  }

  await client.query(
    `INSERT INTO agents(
      agent_id,name,role,description,runtime_type,model_provider,model_name,status,
      permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at
    ) VALUES('agt_worker_foreign',$1,'worker',$1,'openclaw',$1,$1,'error',
      'standard','[]',999,'usr_worker_owner',$2,$2)`,
    [SECRET_CANARY, now],
  );
  await client.query(
    `INSERT INTO agent_gateway_tokens(
      token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,
      heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at
    ) VALUES('tok_worker_foreign',$1,$2,'agt_worker_foreign','[]','active',$3,300,
      $4,$5,NULL,$4,$4)`,
    [randomBytes(32).toString("hex"), FOREIGN_WORKSPACE, SECRET_CANARY, now, future],
  );

  await client.query(
    `INSERT INTO tasks(
      task_id,workspace_id,title,description,requester_id,owner_agent_id,
      collaborator_agent_ids,status,priority,due_date,acceptance_criteria,
      risk_level,budget_limit_usd,created_at,updated_at
    ) VALUES
      ('tsk_worker_pending',$1,'Pending worker task',NULL,'usr_worker_operator',
        'agt_worker_00','[]','planned','medium',NULL,NULL,'medium',1,$2,$2),
      ('tsk_worker_stuck',$1,'Stuck worker task',NULL,'usr_worker_operator',
        'agt_worker_00','[]','running','high',NULL,NULL,'high',1,$2,
        (clock_timestamp()-interval '30 minutes')::text)`,
    [WORKSPACE, now],
  );
  await client.query(
    `INSERT INTO runs(
      run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,
      duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,
      output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,
      parent_run_id,delegation_id,approval_required,agent_plan_id,plan_hash,billing_class,created_at
    ) VALUES('run_worker_completed',$1,'tsk_worker_pending','agt_worker_00',
      'openclaw','completed',$2,$2,10,$3,$3,'openclaw','model',1,1,0,0,NULL,$3,
      $3,NULL,NULL,0,NULL,NULL,'historical_execution',$2)`,
    [WORKSPACE, now, SECRET_CANARY],
  );
  for (let index = 0; index < 30; index += 1) {
    await client.query(
      `INSERT INTO runtime_events(
        runtime_event_id,runtime_connector_id,event_type,status,run_id,task_id,
        agent_id,model_name,latency_ms,prompt_hash,input_summary,output_summary,
        error_message,raw_payload_hash,created_at,workspace_id
      ) VALUES($1,NULL,'agent_worker.heartbeat',$2,NULL,NULL,$3,NULL,$4,$5,$5,$5,$5,$5,$6,$7)`,
      [
        `rte_worker_${index}`,
        index === 1 ? "failed" : "completed",
        `agt_worker_${String(index % 20).padStart(2, "0")}`,
        index,
        SECRET_CANARY,
        new Date(Date.now() - index * 1000).toISOString(),
        WORKSPACE,
      ],
    );
  }
  await client.query(
    `INSERT INTO runtime_events(
      runtime_event_id,runtime_connector_id,event_type,status,run_id,task_id,
      agent_id,model_name,latency_ms,prompt_hash,input_summary,output_summary,
      error_message,raw_payload_hash,created_at,workspace_id
    ) VALUES('rte_worker_foreign',NULL,$1,'failed',NULL,NULL,'agt_worker_foreign',
      $1,999,$1,$1,$1,$1,$1,$2,$3)`,
    [SECRET_CANARY, now, FOREIGN_WORKSPACE],
  );
}

async function startProxyProbe() {
  let calls = 0;
  const server = createServer((incoming, response) => {
    calls += 1;
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({
      ok: true,
      free_local_proxy: true,
      method: incoming.method,
      path: incoming.url,
    }));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  return {
    base: `http://127.0.0.1:${address.port}/api`,
    calls: () => calls,
    close: () => new Promise<void>((resolve, reject) =>
      server.close((error) => error ? reject(error) : resolve())),
  };
}

async function staticBoundary() {
  const source = (await Promise.all([
    "../src/server/controlPlane/humanWorkerFleetReads.ts",
    "../app/api/mis/workers/status/route.ts",
    "../app/api/mis/workers/fleet/route.ts",
    "../app/api/mis/workers/adapter-readiness/route.ts",
  ].map((path) => readFile(new URL(path, import.meta.url), "utf8")))).join("\n");
  assert.match(source, /authenticateHumanMember/);
  assert.match(source, /workspace_entitlements/);
  assert.match(source, /HUMAN_WORKER_READ_ROLES/);
  assert.match(source, /workspace_id=\$1/);
  assert.match(source, /LIMIT \$2/);
  assert.match(source, /appendAudit/);
  assert.match(source, /legacyPythonProxyAllowed/);
  assert.match(source, /python_proxy_performed: false/);
  assert.doesNotMatch(source, /server\.py|sqlite|child_process|execFile|spawn\s*\(|\bfetch\s*\(/i);
}

async function run() {
  stage = "static_boundary";
  assert.ok(BASE_DSN, "AGENTOPS_POSTGRES_DSN is required");
  await staticBoundary();
  const environmentNames = [
    "AGENTOPS_API_BASE",
    "AGENTOPS_CONTROL_PLANE_MODE",
    "AGENTOPS_DEPLOYMENT_MODE",
    "AGENTOPS_HUMAN_SESSION_HMAC_KEY",
    "AGENTOPS_POSTGRES_DSN",
    "AGENTOPS_POSTGRES_SCHEMA",
    "AGENTOPS_POSTGRES_RUNTIME_API_SCHEMA",
    "AGENTOPS_POSTGRES_RUNTIME_ROLE",
  ];
  const originalEnvironment = Object.fromEntries(environmentNames.map((name) => [name, process.env[name]]));
  stage = "postgres_fixture";
  const fixture = await createPostgresRoleBoundaryFixture(BASE_DSN, "worker_fleet");
  stage = "proxy_probe";
  const proxy = await startProxyProbe();
  let restoreRuntime: () => void = () => undefined;
  try {
    stage = "seed";
    await seed(fixture.owner);
    restoreRuntime = fixture.activateRuntimeEnvironment();
    process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = HMAC_KEY;
    process.env.AGENTOPS_API_BASE = proxy.base;
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    process.env.AGENTOPS_DEPLOYMENT_MODE = "production";

    stage = "success";
    const status = await call("status");
    const fleet = await call("fleet");
    const readiness = await call("adapter-readiness");
    for (const result of [status, fleet, readiness]) {
      assert.equal(result.response.status, 200);
      assert.equal(result.response.headers.get("cache-control"), "no-store");
      assert.equal(result.response.headers.get("vary"), "Cookie, X-AgentOps-Workspace-Id");
      assert.equal(result.body.control_plane, "typescript_postgres");
      assert.equal(result.body.workspace_id, WORKSPACE);
      assert.equal(result.body.entitlement_edition, "team_governance");
      assert.equal(result.body.python_proxy_performed, false);
      assert.equal(result.body.audit_recorded, true);
      assert.equal(JSON.stringify(result.body).includes(SECRET_CANARY), false);
      assert.equal(JSON.stringify(result.body).includes(OPERATOR_TOKEN), false);
    }
    assert.equal(status.body.worker_count, 50);
    assert.equal((status.body.workers as unknown[]).length, 50);
    assert.equal((status.body.recent_events as unknown[]).length, 25);
    assert.equal((status.body.daemons as unknown[]).length, 0);
    assert.equal(status.body.running_workers, 0);
    assert.ok(Number(status.body.stale_service_workers) >= 1);
    assert.equal((fleet.body.lanes as unknown[]).length, 50);
    assert.equal((fleet.body.summary as Record<string, unknown>).lane_count, 50);
    assert.equal((fleet.body.safety as Record<string, unknown>).read_only, true);
    const adapters = readiness.body.adapters as Record<string, Record<string, unknown>>;
    assert.deepEqual(Object.keys(adapters), ["mock", "codex", "hermes", "openclaw"]);
    assert.equal((adapters.openclaw.checks as Record<string, unknown>).process_state_verified, false);
    assert.equal(readiness.body.live_execution_performed, false);

    stage = "audit";
    const audits = (await fixture.owner.query<{ action: string; workspace_id: string; metadata_json: string }>(
      `SELECT action,workspace_id,metadata_json FROM audit_logs
      WHERE action LIKE 'human.worker_%_read' ORDER BY action`,
    )).rows;
    assert.deepEqual(audits.map((row) => row.action), [
      "human.worker_adapter_readiness_read",
      "human.worker_fleet_read",
      "human.worker_status_read",
    ]);
    assert.ok(audits.every((row) => row.workspace_id === WORKSPACE));
    assert.ok(audits.every((row) => !row.metadata_json.includes(SECRET_CANARY)));

    stage = "role_denial";
    denied(await call("status", { token: VIEWER_TOKEN }), 403, "human_worker_fleet_role_forbidden");
    stage = "cross_workspace";
    denied(await call("fleet", { queryWorkspace: FOREIGN_WORKSPACE }), 403, "forbidden");
    denied(await call("adapter-readiness", { headerWorkspace: FOREIGN_WORKSPACE }), 403, "human_membership_forbidden");
    stage = "machine_credential";
    denied(await call("status", { machineCredential: true }), 401, "machine_credential_not_allowed");
    stage = "query_bound";
    denied(await call("fleet", { unsupportedQuery: true }), 400, "human_worker_fleet_query_unsupported");

    stage = "entitlement_denial";
    await fixture.owner.query(
      "UPDATE workspace_entitlements SET status='suspended' WHERE workspace_id=$1",
      [WORKSPACE],
    );
    denied(await call("adapter-readiness"), 403, "workspace_entitlement_suspended");
    await fixture.owner.query(
      "UPDATE workspace_entitlements SET status='active',edition='free_local' WHERE workspace_id=$1",
      [WORKSPACE],
    );
    denied(await call("status"), 403, "workspace_entitlement_edition_forbidden");
    await fixture.owner.query(
      "UPDATE workspace_entitlements SET edition='team_governance' WHERE workspace_id=$1",
      [WORKSPACE],
    );

    stage = "production_no_proxy";
    assert.equal((await call("fleet")).response.status, 200);
    assert.equal(proxy.calls(), 0);

    stage = "free_local_proxy";
    process.env.AGENTOPS_DEPLOYMENT_MODE = "free_local";
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    for (const kind of ["status", "fleet", "adapter-readiness"] as const) {
      const local = await call(kind);
      assert.equal(local.response.status, 200);
      assert.equal(local.body.free_local_proxy, true);
      assert.equal(local.body.path, `/api/workers/${kind}`);
    }
    assert.equal(proxy.calls(), 3);

    console.log(JSON.stringify({
      ok: true,
      contract: "human_worker_fleet_postgres_v1",
      endpoints: [
        "GET /api/mis/workers/status",
        "GET /api/mis/workers/fleet",
        "GET /api/mis/workers/adapter-readiness",
      ],
      schema_contract: fixture.migration.schema_contract,
      workspace_session_binding: true,
      rbac_verified: true,
      active_commercial_entitlement_required: true,
      cross_workspace_fail_closed: true,
      bounded_workers: 50,
      bounded_events: 25,
      access_audit_recorded: true,
      sensitive_fields_omitted: true,
      runtime_role_boundary_verified: true,
      production_typescript_postgres: true,
      production_python_proxy_calls: 0,
      free_local_python_proxy_preserved: true,
      credentials_omitted: true,
      token_omitted: true,
    }));
  } finally {
    await closeControlPlanePoolForTests();
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
  const failure = error && typeof error === "object" ? error as { message?: unknown } : {};
  console.log(JSON.stringify({
    ok: false,
    contract: "human_worker_fleet_postgres_v1",
    stage,
    observed_status: observedStatus,
    observed_error: observedError,
    error: String(failure.message || "contract_failed").slice(0, 240),
    credentials_omitted: true,
    row_data_omitted: true,
    token_omitted: true,
  }));
  process.exitCode = 1;
});
