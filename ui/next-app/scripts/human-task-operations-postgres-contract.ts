import assert from "node:assert/strict";
import { createHmac, randomBytes, randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

import { NextRequest } from "next/server";
import { Client } from "pg";

import { PATCH as assignTask } from "../app/api/mis/tasks/[taskId]/assign/route";
import { PATCH as updateTaskStatus } from "../app/api/mis/tasks/[taskId]/status/route";
import { closeControlPlanePoolForTests } from "../src/server/controlPlane/db";
import { createPostgresRoleBoundaryFixture } from "./postgres-role-boundary-test-helper";

const BASE_DSN = String(process.env.AGENTOPS_POSTGRES_DSN || "").trim();
const ORIGIN = "https://mis.example.test";
const HOST = "mis.example.test";
const WORKSPACE = "ws_human_task_ops";
const FOREIGN_WORKSPACE = "ws_human_task_ops_foreign";
const HMAC_KEY = randomBytes(48).toString("base64url");
const OPERATOR_TOKEN = randomBytes(32).toString("base64url");
const VIEWER_TOKEN = randomBytes(32).toString("base64url");
let activeStage = "startup";
let observedStatus: number | null = null;
let observedError = "";

type Operation = "status" | "assign";
type Session = Readonly<{ token: string; csrf: string }>;
type RouteResult = Readonly<{
  response: Response;
  body: Record<string, unknown>;
}>;

function hmac(label: string, token: string) {
  return createHmac("sha256", HMAC_KEY)
    .update(`${label}:${token}`, "utf8")
    .digest("hex");
}

function session(token: string): Session {
  return { token, csrf: hmac("csrf", token) };
}

function request(
  operation: Operation,
  taskId: string,
  body: Record<string, unknown>,
  identity: Session,
  workspaceId = WORKSPACE,
) {
  return new NextRequest(
    `${ORIGIN}/api/mis/tasks/${encodeURIComponent(taskId)}/${operation}`,
    {
      method: "PATCH",
      headers: {
        "content-type": "application/json",
        cookie: `agentops_human_session=${identity.token}`,
        host: HOST,
        origin: ORIGIN,
        "x-agentops-workspace-id": workspaceId,
        "x-agentops-csrf": identity.csrf,
      },
      body: JSON.stringify(body),
    },
  );
}

async function call(
  operation: Operation,
  taskId: string,
  body: Record<string, unknown>,
  identity = session(OPERATOR_TOKEN),
  workspaceId = WORKSPACE,
): Promise<RouteResult> {
  const route = operation === "status" ? updateTaskStatus : assignTask;
  const response = await route(
    request(operation, taskId, body, identity, workspaceId),
    { params: Promise.resolve({ taskId }) },
  );
  const result = {
    response,
    body: await response.json() as Record<string, unknown>,
  };
  observedStatus = result.response.status;
  observedError = String(result.body.error || "");
  return result;
}

function assertDenied(result: RouteResult, status: number, error: string) {
  assert.equal(result.response.status, status);
  assert.equal(result.body.error, error);
  assert.equal(Object.hasOwn(result.body, "task"), false);
}

async function seed(client: Client) {
  const now = new Date().toISOString();
  const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  await client.query(
    `INSERT INTO users(user_id,name,email,role,created_at) VALUES
      ('usr_task_ops_operator','Task operator','task-operator@example.invalid','operator',$1),
      ('usr_task_ops_viewer','Task viewer','task-viewer@example.invalid','viewer',$1)`,
    [now],
  );
  await client.query(
    `INSERT INTO workspace_memberships(
      workspace_id,user_id,role,status,created_at,updated_at
    ) VALUES
      ($1,'usr_task_ops_operator','operator','active',$3,$3),
      ($1,'usr_task_ops_viewer','viewer','active',$3,$3),
      ($2,'usr_task_ops_viewer','viewer','active',$3,$3)`,
    [WORKSPACE, FOREIGN_WORKSPACE, now],
  );
  await client.query(
    `INSERT INTO human_sessions(
      session_id,user_id,session_hash,status,created_at,expires_at,
      last_seen_at,revoked_at
    ) VALUES
      ('hsess_task_ops_operator','usr_task_ops_operator',$1,'active',$3,$4,$3,NULL),
      ('hsess_task_ops_viewer','usr_task_ops_viewer',$2,'active',$3,$4,$3,NULL)`,
    [
      hmac("session", OPERATOR_TOKEN),
      hmac("session", VIEWER_TOKEN),
      now,
      expiresAt,
    ],
  );
  await client.query(
    `INSERT INTO workspace_entitlements(
      workspace_id,edition,status,capabilities_json,max_agents,
      max_active_enrollments,max_active_sessions_per_agent,max_monthly_runs,
      max_monthly_cost_usd,max_concurrent_runs,effective_at,expires_at
    ) VALUES
      ($1,'team_governance','active',
        '{"enrollment_issue":true,"session_issue":true,"run_start":true}',
        20,20,20,100,1000,10,clock_timestamp()-interval '1 hour',
        clock_timestamp()+interval '1 year'),
      ($2,'team_governance','active','{"run_start":true}',
        20,20,20,100,1000,10,clock_timestamp()-interval '1 hour',
        clock_timestamp()+interval '1 year')`,
    [WORKSPACE, FOREIGN_WORKSPACE],
  );
  await client.query(
    `INSERT INTO agents(
      agent_id,name,role,description,runtime_type,model_provider,model_name,
      status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,
      created_at,updated_at
    ) VALUES
      ('agt_task_ops_primary','Primary worker','worker',NULL,'hermes','hermes',
        'contract-model','idle','standard','[]',100,NULL,$1,$1),
      ('agt_task_ops_secondary','Secondary worker','worker',NULL,'openclaw',
        'openclaw','contract-model','idle','standard','[]',100,NULL,$1,$1),
      ('agt_task_ops_foreign','Foreign worker','worker',NULL,'hermes','hermes',
        'contract-model','idle','standard','[]',100,NULL,$1,$1)`,
    [now],
  );
  await client.query(
    `INSERT INTO agent_gateway_tokens(
      token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,
      heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,
      last_heartbeat_at
    ) VALUES
      ('tok_task_ops_primary',$1,$4,'agt_task_ops_primary','["tasks:read"]',
        'active','primary',300,$3,NULL,NULL,NULL,NULL),
      ('tok_task_ops_secondary',$2,$4,'agt_task_ops_secondary','["tasks:read"]',
        'active','secondary',300,$3,NULL,NULL,NULL,NULL),
      ('tok_task_ops_foreign',$5,$6,'agt_task_ops_foreign','["tasks:read"]',
        'active','foreign',300,$3,NULL,NULL,NULL,NULL)`,
    [
      randomBytes(32).toString("hex"),
      randomBytes(32).toString("hex"),
      now,
      WORKSPACE,
      randomBytes(32).toString("hex"),
      FOREIGN_WORKSPACE,
    ],
  );
  await client.query(
    `INSERT INTO tasks(
      task_id,workspace_id,title,description,requester_id,owner_agent_id,
      collaborator_agent_ids,status,priority,due_date,acceptance_criteria,
      risk_level,budget_limit_usd,created_at,updated_at
    ) VALUES
      ('tsk_task_ops_status',$1,'Status operation',NULL,
        'usr_task_ops_operator','agt_task_ops_primary','[]','backlog','medium',
        NULL,NULL,'medium',10,$3,$3),
      ('tsk_task_ops_assign',$1,'Assign operation',NULL,
        'usr_task_ops_operator','agt_task_ops_primary','[]','planned','medium',
        NULL,NULL,'medium',10,$3,$3),
      ('tsk_task_ops_entitlement',$1,'Entitlement operation',NULL,
        'usr_task_ops_operator','agt_task_ops_primary','[]','planned','medium',
        NULL,NULL,'medium',10,$3,$3),
      ('tsk_task_ops_no_proxy',$1,'No proxy operation',NULL,
        'usr_task_ops_operator','agt_task_ops_primary','[]','backlog','medium',
        NULL,NULL,'medium',10,$3,$3),
      ('tsk_task_ops_foreign',$2,'Foreign operation',NULL,
        'usr_task_ops_viewer','agt_task_ops_foreign','[]','planned','medium',
        NULL,NULL,'medium',10,$3,$3)`,
    [WORKSPACE, FOREIGN_WORKSPACE, now],
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
  const paths = [
    "../src/server/controlPlane/humanTaskOperations.ts",
    "../app/api/mis/tasks/[taskId]/status/route.ts",
    "../app/api/mis/tasks/[taskId]/assign/route.ts",
  ];
  const source = (await Promise.all(paths.map((path) =>
    readFile(new URL(path, import.meta.url), "utf8")))).join("\n");
  assert.match(source, /authenticateHumanWriteMember/);
  assert.match(source, /workspace_entitlements/);
  assert.match(source, /workspace_id=\$2/);
  assert.match(source, /legacyPythonProxyAllowed/);
  assert.match(source, /python_proxy_performed: false/);
  assert.doesNotMatch(source, /server\.py|sqlite|child_process|\bfetch\s*\(/i);
}

async function run() {
  activeStage = "static_boundary";
  assert.ok(BASE_DSN, "AGENTOPS_POSTGRES_DSN is required");
  await assertStaticBoundary();
  const originalEnvironment = Object.fromEntries([
    "AGENTOPS_ALLOWED_ORIGINS",
    "AGENTOPS_API_BASE",
    "AGENTOPS_CONTROL_PLANE_MODE",
    "AGENTOPS_DEPLOYMENT_MODE",
    "AGENTOPS_HUMAN_SESSION_HMAC_KEY",
    "AGENTOPS_POSTGRES_DSN",
    "AGENTOPS_POSTGRES_SCHEMA",
    "AGENTOPS_POSTGRES_RUNTIME_API_SCHEMA",
    "AGENTOPS_POSTGRES_RUNTIME_ROLE",
  ].map((key) => [key, process.env[key]]));
  activeStage = "postgres_fixture";
  const fixture = await createPostgresRoleBoundaryFixture(BASE_DSN, "task_ops");
  activeStage = "proxy_probe";
  const proxy = await startProxyProbe();
  let restoreRuntime: () => void = () => undefined;
  try {
    activeStage = "seed";
    await seed(fixture.owner);
    restoreRuntime = fixture.activateRuntimeEnvironment();
    process.env.AGENTOPS_ALLOWED_ORIGINS = ORIGIN;
    process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = HMAC_KEY;
    process.env.AGENTOPS_API_BASE = proxy.base;

    activeStage = "status_success";
    const status = await call("status", "tsk_task_ops_status", {
      workspace_id: WORKSPACE,
      status: "planned",
    });
    assert.equal(status.response.status, 200);
    assert.equal(status.body.control_plane, "typescript_postgres");
    assert.equal((status.body.task as Record<string, unknown>).status, "planned");

    activeStage = "assign_success";
    const assignment = await call("assign", "tsk_task_ops_assign", {
      workspace_id: WORKSPACE,
      owner_agent_id: "agt_task_ops_secondary",
    });
    assert.equal(assignment.response.status, 200);
    assert.equal(
      (assignment.body.task as Record<string, unknown>).owner_agent_id,
      "agt_task_ops_secondary",
    );

    activeStage = "cross_workspace";
    assertDenied(await call("status", "tsk_task_ops_foreign", {
      workspace_id: WORKSPACE,
      status: "blocked",
    }), 404, "human_task_not_found");
    assertDenied(await call("status", "tsk_task_ops_foreign", {
      workspace_id: FOREIGN_WORKSPACE,
      status: "blocked",
    }, session(OPERATOR_TOKEN), FOREIGN_WORKSPACE), 403, "human_membership_forbidden");
    activeStage = "role_denial";
    assertDenied(await call("status", "tsk_task_ops_assign", {
      workspace_id: WORKSPACE,
      status: "blocked",
    }, session(VIEWER_TOKEN)), 403, "human_task_role_forbidden");
    activeStage = "invalid_status";
    assertDenied(await call("status", "tsk_task_ops_assign", {
      workspace_id: WORKSPACE,
      status: "completed",
    }), 400, "human_task_status_invalid");
    activeStage = "foreign_agent";
    assertDenied(await call("assign", "tsk_task_ops_assign", {
      workspace_id: WORKSPACE,
      owner_agent_id: "agt_task_ops_foreign",
    }), 400, "human_task_owner_unavailable");

    activeStage = "entitlement_denial";
    await fixture.owner.query(
      "UPDATE workspace_entitlements SET status='suspended' WHERE workspace_id=$1",
      [WORKSPACE],
    );
    assertDenied(await call("status", "tsk_task_ops_entitlement", {
      workspace_id: WORKSPACE,
      status: "blocked",
    }), 403, "workspace_entitlement_suspended");
    await fixture.owner.query(
      `UPDATE workspace_entitlements
      SET status='active',edition='free_local' WHERE workspace_id=$1`,
      [WORKSPACE],
    );
    assertDenied(await call("status", "tsk_task_ops_entitlement", {
      workspace_id: WORKSPACE,
      status: "blocked",
    }), 403, "workspace_entitlement_edition_forbidden");
    await fixture.owner.query(
      "UPDATE workspace_entitlements SET edition='team_governance' WHERE workspace_id=$1",
      [WORKSPACE],
    );

    activeStage = "production_no_proxy";
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    process.env.AGENTOPS_DEPLOYMENT_MODE = "production";
    const noProxy = await call("status", "tsk_task_ops_no_proxy", {
      workspace_id: WORKSPACE,
      status: "planned",
    });
    assert.equal(noProxy.response.status, 200);
    assert.equal(noProxy.body.python_proxy_performed, false);
    assert.equal(noProxy.response.headers.get("cache-control"), "no-store");
    assert.equal(proxy.calls(), 0);

    activeStage = "free_local_proxy";
    process.env.AGENTOPS_DEPLOYMENT_MODE = "free_local";
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    const freeLocal = await call("status", "tsk_free_local_proxy", {
      workspace_id: "local-demo",
      status: "planned",
    });
    assert.equal(freeLocal.response.status, 200);
    assert.equal(freeLocal.body.free_local_proxy, true);
    assert.equal(freeLocal.response.headers.get("cache-control"), "no-store");
    assert.equal(freeLocal.body.method, "PATCH");
    assert.equal(
      freeLocal.body.path,
      "/api/tasks/tsk_free_local_proxy/status",
    );
    assert.equal(proxy.calls(), 1);

    activeStage = "evidence";
    const evidence = await fixture.owner.query<{
      audit_count: string;
      runtime_count: string;
    }>(
      `SELECT
        (SELECT count(*)::text FROM audit_logs
          WHERE workspace_id=$1
            AND action IN ('human.task_status_update','human.task_assign'))
          AS audit_count,
        (SELECT count(*)::text FROM runtime_events
          WHERE workspace_id=$1
            AND event_type IN ('task.human_status_update','task.human_assign'))
          AS runtime_count`,
      [WORKSPACE],
    );
    assert.equal(evidence.rows[0]?.audit_count, "3");
    assert.equal(evidence.rows[0]?.runtime_count, "3");

    console.log(JSON.stringify({
      ok: true,
      contract: "human_task_operations_typescript_postgres_v1",
      paths: [
        "PATCH /api/mis/tasks/:taskId/status",
        "PATCH /api/mis/tasks/:taskId/assign",
      ],
      success_verified: true,
      cross_workspace_rejected: true,
      role_rejected: true,
      invalid_input_rejected: true,
      entitlement_fail_closed: true,
      production_python_proxy_calls: 0,
      free_local_python_proxy_preserved: true,
      postgres_audit_and_runtime_evidence: true,
      token_omitted: true,
    }));
  } finally {
    await closeControlPlanePoolForTests();
    restoreRuntime();
    await proxy.close();
    await fixture.cleanup();
    for (const [key, value] of Object.entries(originalEnvironment)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

run().catch(() => {
  console.log(JSON.stringify({
    ok: false,
    contract: "human_task_operations_typescript_postgres_v1",
    error_code: "contract_failed",
    stage: activeStage,
    observed_status: observedStatus,
    observed_error: observedError,
    credentials_omitted: true,
    row_data_omitted: true,
    token_omitted: true,
  }));
  process.exitCode = 1;
});
