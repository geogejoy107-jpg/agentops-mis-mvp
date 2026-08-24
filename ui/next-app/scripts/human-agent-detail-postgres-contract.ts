import assert from "node:assert/strict";
import { createHash, createHmac, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

import { NextRequest } from "next/server";
import { Client } from "pg";

import { GET as getAgentDetail } from "../app/api/mis/agents/[agentId]/route";
import { closeControlPlanePoolForTests } from "../src/server/controlPlane/db";
import { createPostgresRoleBoundaryFixture } from "./postgres-role-boundary-test-helper";

const BASE_DSN = String(process.env.AGENTOPS_POSTGRES_DSN || "").trim();
const WORKSPACE = "ws_agent_detail";
const FOREIGN_WORKSPACE = "ws_agent_detail_foreign";
const LOCAL_AGENT = "agt_agent_detail";
const FOREIGN_AGENT = "agt_agent_detail_foreign";
const SECRET_CANARY = "agent-detail-sensitive-canary-must-not-leak";
const OPERATOR_TOKEN = randomBytes(32).toString("base64url");
const VIEWER_TOKEN = randomBytes(32).toString("base64url");
const HMAC_KEY = randomBytes(48).toString("base64url");
let activeStage = "startup";
let observedStatus: number | null = null;
let observedError = "";

type Identity = Readonly<{ token: string }>;
type RouteResult = Readonly<{
  response: Response;
  body: Record<string, unknown>;
}>;

function hmac(label: string, token: string) {
  return createHmac("sha256", HMAC_KEY)
    .update(`${label}:${token}`, "utf8")
    .digest("hex");
}

function sha(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

async function reserveRunCost(
  client: Client,
  workspaceId: string,
  runId: string,
  estimatedCostUsd: string,
  createdAt: string,
) {
  await client.query(
    `INSERT INTO run_cost_reservations(
      reservation_id,workspace_id,run_id,billing_class,billing_month_utc,
      state,estimated_cost_usd,observed_cost_usd,idempotency_key_hash,
      request_hash,reserved_at,expires_at,updated_at
    ) VALUES(
      $1,$2,$3,'historical_execution',
      date_trunc('month',$6::timestamptz)::date,'reserved',$4::numeric,0,
      $5,$7,$6::timestamptz,$6::timestamptz+interval '1 hour',
      $6::timestamptz
    )`,
    [
      `rsv_${runId}`,
      workspaceId,
      runId,
      estimatedCostUsd,
      sha(`agent-detail-reservation:${workspaceId}:${runId}`),
      createdAt,
      sha(`agent-detail-request:${workspaceId}:${runId}`),
    ],
  );
}

function request(
  agentId: string,
  identity: Identity = { token: OPERATOR_TOKEN },
  options: Readonly<{
    headerWorkspace?: string;
    queryWorkspace?: string;
    machineCredential?: boolean;
    unsupportedQuery?: boolean;
  }> = {},
) {
  const url = new URL(
    `https://mis.example.test/api/mis/agents/${encodeURIComponent(agentId)}`,
  );
  if (options.queryWorkspace) {
    url.searchParams.set("workspace_id", options.queryWorkspace);
  }
  if (options.unsupportedQuery) url.searchParams.set("raw", "true");
  const headers = new Headers({
    cookie: `agentops_human_session=${identity.token}`,
    "x-agentops-workspace-id": options.headerWorkspace || WORKSPACE,
  });
  if (options.machineCredential) {
    headers.set("authorization", "Bearer machine-credential-forbidden");
  }
  return new NextRequest(url, { method: "GET", headers });
}

async function call(
  agentId: string,
  identity?: Identity,
  options?: Parameters<typeof request>[2],
): Promise<RouteResult> {
  const response = await getAgentDetail(
    request(agentId, identity, options),
    { params: Promise.resolve({ agentId }) },
  );
  const body = await response.json() as Record<string, unknown>;
  observedStatus = response.status;
  observedError = String(body.error || "");
  return { response, body };
}

function assertDenied(result: RouteResult, status: number, error: string) {
  assert.equal(result.response.status, status);
  assert.equal(result.body.error, error);
  assert.equal(Object.hasOwn(result.body, "agent"), false);
  assert.equal(Object.hasOwn(result.body, "runs"), false);
  assert.equal(Object.hasOwn(result.body, "tasks"), false);
  assert.equal(result.body.token_omitted, true);
}

async function seed(client: Client) {
  const now = new Date().toISOString();
  const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  await client.query(
    `INSERT INTO users(user_id,name,email,role,created_at) VALUES
      ('usr_agent_detail_operator','Agent detail operator',
        'agent-detail-operator@example.invalid','operator',$1),
      ('usr_agent_detail_viewer','Agent detail viewer',
        'agent-detail-viewer@example.invalid','viewer',$1),
      ('usr_agent_detail_owner',$2,$3,'owner',$1)`,
    [now, SECRET_CANARY, `${SECRET_CANARY}@example.invalid`],
  );
  await client.query(
    `INSERT INTO workspace_memberships(
      workspace_id,user_id,role,status,created_at,updated_at
    ) VALUES
      ($1,'usr_agent_detail_operator','operator','active',$3,$3),
      ($1,'usr_agent_detail_viewer','viewer','active',$3,$3),
      ($2,'usr_agent_detail_operator','operator','active',$3,$3)`,
    [WORKSPACE, FOREIGN_WORKSPACE, now],
  );
  await client.query(
    `INSERT INTO human_sessions(
      session_id,user_id,session_hash,status,created_at,expires_at,
      last_seen_at,revoked_at
    ) VALUES
      ('hsess_agent_detail_operator','usr_agent_detail_operator',$1,
        'active',$3,$4,$3,NULL),
      ('hsess_agent_detail_viewer','usr_agent_detail_viewer',$2,
        'active',$3,$4,$3,NULL)`,
    [
      hmac("session", OPERATOR_TOKEN),
      hmac("session", VIEWER_TOKEN),
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
  await client.query(
    `INSERT INTO agents(
      agent_id,name,role,description,runtime_type,model_provider,model_name,
      status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,
      created_at,updated_at
    ) VALUES
      ($1,'Commercial OpenClaw','worker','Bounded commercial Agent','openclaw',
        'openclaw','commercial-model','running','standard',
        '["summarize","artifact.read"]',100,'usr_agent_detail_owner',$4,$4),
      ($2,$3,'worker',$3,'hermes','hermes',$3,'error','standard','[]',999,
        'usr_agent_detail_owner',$4,$4)`,
    [LOCAL_AGENT, FOREIGN_AGENT, SECRET_CANARY, now],
  );
  await client.query(
    `INSERT INTO agent_gateway_tokens(
      token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,
      heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,
      last_heartbeat_at
    ) VALUES
      ('tok_agent_detail_local',$1,$3,$4,'["tasks:read"]','active',$2,300,
        $6,NULL,NULL,NULL,$6),
      ('tok_agent_detail_foreign',$5,$7,$8,'["tasks:read"]','active',$2,300,
        $6,NULL,NULL,NULL,$6)`,
    [
      randomBytes(32).toString("hex"),
      SECRET_CANARY,
      WORKSPACE,
      LOCAL_AGENT,
      randomBytes(32).toString("hex"),
      now,
      FOREIGN_WORKSPACE,
      FOREIGN_AGENT,
    ],
  );
  await client.query(
    `INSERT INTO tasks(
      task_id,workspace_id,title,description,requester_id,owner_agent_id,
      collaborator_agent_ids,status,priority,due_date,acceptance_criteria,
      risk_level,budget_limit_usd,created_at,updated_at
    ) VALUES
      ('tsk_agent_detail',$1,'Bounded task title',$3,
        'usr_agent_detail_operator',$2,'[]','running','high',NULL,$3,
        'high',25,$4,$4),
      ('tsk_agent_detail_collaboration',$1,'Bounded collaboration',NULL,
        'usr_agent_detail_operator',NULL,$7,'planned','medium',NULL,NULL,
        'medium',5,$4,$4),
      ('tsk_agent_detail_foreign',$5,$3,$3,'usr_agent_detail_operator',$6,
        '[]','running','high',NULL,$3,'high',999,$4,$4)`,
    [
      WORKSPACE,
      LOCAL_AGENT,
      SECRET_CANARY,
      now,
      FOREIGN_WORKSPACE,
      FOREIGN_AGENT,
      JSON.stringify([LOCAL_AGENT]),
    ],
  );
  await reserveRunCost(client, WORKSPACE, "run_agent_detail", "0.250000", now);
  await reserveRunCost(
    client,
    FOREIGN_WORKSPACE,
    "run_agent_detail_foreign",
    "99.000000",
    now,
  );
  await client.query(
    `INSERT INTO runs(
      run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,
      ended_at,duration_ms,input_summary,output_summary,model_provider,
      model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,
      error_type,error_message,trace_id,parent_run_id,delegation_id,
      approval_required,agent_plan_id,plan_hash,billing_class,created_at
    ) VALUES
      ('run_agent_detail',$1,'tsk_agent_detail',$2,'openclaw','running',$4,
        NULL,1200,$3,$3,'openclaw','commercial-model',10,12,3,0.25,NULL,$3,$3,
        NULL,NULL,1,NULL,NULL,'historical_execution',$4),
      ('run_agent_detail_foreign',$5,'tsk_agent_detail_foreign',$6,'hermes',
        'running',$4,NULL,900,$3,$3,'hermes',$3,1,1,1,99,NULL,$3,$3,NULL,NULL,
        0,NULL,NULL,'historical_execution',$4)`,
    [WORKSPACE, LOCAL_AGENT, SECRET_CANARY, now, FOREIGN_WORKSPACE, FOREIGN_AGENT],
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

async function assertStaticBoundary() {
  const source = (await Promise.all([
    "../src/server/controlPlane/humanAgentDetail.ts",
    "../app/api/mis/agents/[agentId]/route.ts",
  ].map((path) => readFile(new URL(path, import.meta.url), "utf8")))).join("\n");
  assert.match(source, /authenticateHumanMember/);
  assert.match(source, /workspace_entitlements/);
  assert.match(source, /AGENT_DETAIL_ROLES/);
  assert.match(source, /workspace_id=\$1/);
  assert.match(source, /LIMIT \$3/);
  assert.match(source, /human\.agent_detail_read/);
  assert.match(source, /legacyPythonProxyAllowed/);
  assert.match(source, /python_proxy_performed: false/);
  assert.doesNotMatch(source, /server\.py|sqlite|child_process|\bfetch\s*\(/i);
}

async function run() {
  activeStage = "static_boundary";
  assert.ok(BASE_DSN, "AGENTOPS_POSTGRES_DSN is required");
  await assertStaticBoundary();
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
  const originalEnvironment = Object.fromEntries(
    environmentNames.map((name) => [name, process.env[name]]),
  );
  activeStage = "postgres_fixture";
  const fixture = await createPostgresRoleBoundaryFixture(BASE_DSN, "agent_detail");
  activeStage = "proxy_probe";
  const proxy = await startProxyProbe();
  let restoreRuntime: () => void = () => undefined;
  try {
    activeStage = "seed";
    await seed(fixture.owner);
    restoreRuntime = fixture.activateRuntimeEnvironment();
    process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = HMAC_KEY;
    process.env.AGENTOPS_API_BASE = proxy.base;
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    process.env.AGENTOPS_DEPLOYMENT_MODE = "production";

    activeStage = "success";
    const success = await call(LOCAL_AGENT);
    assert.equal(success.response.status, 200);
    assert.deepEqual(Object.keys(success.body), [
      "ok",
      "control_plane",
      "workspace_id",
      "entitlement_edition",
      "agent",
      "runs",
      "tasks",
      "bounds",
      "audit_recorded",
      "python_proxy_performed",
      "raw_prompt_omitted",
      "raw_response_omitted",
      "credentials_omitted",
      "token_omitted",
    ]);
    assert.equal(success.body.control_plane, "typescript_postgres");
    assert.equal(success.body.workspace_id, WORKSPACE);
    assert.equal(success.body.python_proxy_performed, false);
    assert.equal(success.response.headers.get("cache-control"), "no-store");
    assert.equal(success.response.headers.get("vary"), "Cookie, X-AgentOps-Workspace-Id");
    const agent = success.body.agent as Record<string, unknown>;
    assert.deepEqual(agent.allowed_tools, ["artifact.read", "summarize"]);
    assert.equal(Object.hasOwn(agent, "owner_user_id"), false);
    const runs = success.body.runs as Array<Record<string, unknown>>;
    assert.equal(runs.length, 1);
    assert.equal(Object.hasOwn(runs[0], "input_summary"), false);
    assert.equal(Object.hasOwn(runs[0], "output_summary"), false);
    assert.equal(Object.hasOwn(runs[0], "error_message"), false);
    assert.equal(Object.hasOwn(runs[0], "trace_id"), false);
    const tasks = success.body.tasks as Array<Record<string, unknown>>;
    assert.equal(tasks.length, 2);
    assert.deepEqual(
      tasks.map((task) => task.task_id).sort(),
      ["tsk_agent_detail", "tsk_agent_detail_collaboration"],
    );
    assert.equal(Object.hasOwn(tasks[0], "description"), false);
    assert.equal(Object.hasOwn(tasks[0], "acceptance_criteria"), false);
    assert.equal(Object.hasOwn(tasks[0], "requester_id"), false);
    const serialized = JSON.stringify(success.body);
    assert.equal(serialized.includes(SECRET_CANARY), false);
    assert.equal(serialized.includes(OPERATOR_TOKEN), false);
    assert.equal(serialized.includes(FOREIGN_AGENT), false);

    activeStage = "audit";
    const audit = (await fixture.owner.query<{
      action: string;
      workspace_id: string;
      actor_id: string;
      entity_id: string;
      metadata_json: string;
    }>(
      `SELECT action,workspace_id,actor_id,entity_id,metadata_json
      FROM audit_logs WHERE action='human.agent_detail_read'`,
    )).rows;
    assert.equal(audit.length, 1);
    assert.equal(audit[0].workspace_id, WORKSPACE);
    assert.equal(audit[0].actor_id, "usr_agent_detail_operator");
    assert.equal(audit[0].entity_id, LOCAL_AGENT);
    assert.equal(audit[0].metadata_json.includes(OPERATOR_TOKEN), false);
    assert.equal(audit[0].metadata_json.includes(SECRET_CANARY), false);

    activeStage = "role_denial";
    assertDenied(
      await call(LOCAL_AGENT, { token: VIEWER_TOKEN }),
      403,
      "human_agent_detail_role_forbidden",
    );
    activeStage = "cross_workspace";
    assertDenied(
      await call(FOREIGN_AGENT),
      404,
      "human_agent_not_found",
    );
    assertDenied(
      await call(LOCAL_AGENT, undefined, { queryWorkspace: FOREIGN_WORKSPACE }),
      403,
      "forbidden",
    );
    assertDenied(
      await call(LOCAL_AGENT, undefined, { headerWorkspace: FOREIGN_WORKSPACE }),
      404,
      "human_agent_not_found",
    );
    activeStage = "machine_credential";
    assertDenied(
      await call(LOCAL_AGENT, undefined, { machineCredential: true }),
      401,
      "machine_credential_not_allowed",
    );
    activeStage = "bounded_query";
    assertDenied(
      await call(LOCAL_AGENT, undefined, { unsupportedQuery: true }),
      400,
      "human_agent_detail_query_unsupported",
    );

    activeStage = "entitlement_denial";
    await fixture.owner.query(
      "UPDATE workspace_entitlements SET status='suspended' WHERE workspace_id=$1",
      [WORKSPACE],
    );
    assertDenied(
      await call(LOCAL_AGENT),
      403,
      "workspace_entitlement_suspended",
    );
    await fixture.owner.query(
      `UPDATE workspace_entitlements SET status='active',edition='free_local'
      WHERE workspace_id=$1`,
      [WORKSPACE],
    );
    assertDenied(
      await call(LOCAL_AGENT),
      403,
      "workspace_entitlement_edition_forbidden",
    );
    await fixture.owner.query(
      `UPDATE workspace_entitlements SET edition='team_governance'
      WHERE workspace_id=$1`,
      [WORKSPACE],
    );

    activeStage = "production_no_proxy";
    const production = await call(LOCAL_AGENT);
    assert.equal(production.response.status, 200);
    assert.equal(production.body.python_proxy_performed, false);
    assert.equal(proxy.calls(), 0);

    activeStage = "free_local_proxy";
    process.env.AGENTOPS_DEPLOYMENT_MODE = "free_local";
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    const freeLocal = await call("agt_free_local");
    assert.equal(freeLocal.response.status, 200);
    assert.equal(freeLocal.body.free_local_proxy, true);
    assert.equal(freeLocal.body.method, "GET");
    assert.equal(freeLocal.body.path, "/api/agents/agt_free_local");
    assert.equal(proxy.calls(), 1);

    console.log(JSON.stringify({
      ok: true,
      contract: "human_agent_detail_postgres_v1",
      schema_contract: fixture.migration.schema_contract,
      workspace_session_binding: true,
      rbac_verified: true,
      active_commercial_entitlement_required: true,
      cross_workspace_fail_closed: true,
      bounded_canonical_response: true,
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
  const failure = error && typeof error === "object"
    ? error as { message?: unknown }
    : {};
  console.log(JSON.stringify({
    ok: false,
    contract: "human_agent_detail_postgres_v1",
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
