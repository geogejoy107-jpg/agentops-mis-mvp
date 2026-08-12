import assert from "node:assert/strict";
import { createHmac, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

import { NextRequest } from "next/server";
import { Client } from "pg";

import { GET as exportMemories } from "../app/api/mis/memories/export/route";
import { GET as listMemories } from "../app/api/mis/memories/route";
import { closeControlPlanePoolForTests } from "../src/server/controlPlane/db";
import { createPostgresRoleBoundaryFixture } from "./postgres-role-boundary-test-helper";

const BASE_DSN = String(process.env.AGENTOPS_POSTGRES_DSN || "").trim();
const WORKSPACE = "ws_memory_export";
const FOREIGN_WORKSPACE = "ws_memory_export_foreign";
const OPERATOR_TOKEN = randomBytes(32).toString("base64url");
const VIEWER_TOKEN = randomBytes(32).toString("base64url");
const HMAC_KEY = randomBytes(48).toString("base64url");
const SECRET_CANARY = "memory-export-sensitive-canary-must-not-leak";
let activeStage = "startup";
let observedStatus: number | null = null;
let observedError = "";

type RouteResult = Readonly<{
  response: Response;
  body: Record<string, unknown> | Array<Record<string, unknown>>;
}>;

function hmac(label: string, token: string) {
  return createHmac("sha256", HMAC_KEY)
    .update(`${label}:${token}`, "utf8")
    .digest("hex");
}

function request(
  path: "list" | "export",
  token = OPERATOR_TOKEN,
  options: Readonly<{
    deployment?: "production" | "shared" | "free_local";
    headerWorkspace?: string;
    queryWorkspace?: string;
    reviewStatus?: string;
    limit?: string;
    unsupported?: boolean;
    duplicateWorkspace?: boolean;
    machineCredential?: boolean;
  }> = {},
) {
  process.env.AGENTOPS_DEPLOYMENT_MODE = options.deployment || "production";
  process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
  const suffix = path === "export" ? "/export" : "";
  const url = new URL(`https://mis.example.test/api/mis/memories${suffix}`);
  if (options.queryWorkspace) url.searchParams.set("workspace_id", options.queryWorkspace);
  if (options.reviewStatus) url.searchParams.set("review_status", options.reviewStatus);
  if (options.limit) url.searchParams.set("limit", options.limit);
  if (options.unsupported) url.searchParams.set("raw", "true");
  if (options.duplicateWorkspace) url.searchParams.append("workspace_id", WORKSPACE);
  const headers = new Headers({
    cookie: `agentops_human_session=${token}`,
    "x-agentops-workspace-id": options.headerWorkspace || WORKSPACE,
  });
  if (options.machineCredential) {
    headers.set("authorization", "Bearer machine-credential-forbidden");
  }
  return new NextRequest(url, { method: "GET", headers });
}

async function call(
  path: "list" | "export",
  token = OPERATOR_TOKEN,
  options?: Parameters<typeof request>[2],
): Promise<RouteResult> {
  const response = path === "export"
    ? await exportMemories(request(path, token, options))
    : await listMemories(request(path, token, options));
  const body = await response.json() as RouteResult["body"];
  observedStatus = response.status;
  observedError = Array.isArray(body) ? "" : String(body.error || "");
  return { response, body };
}

function objectBody(result: RouteResult) {
  assert.equal(Array.isArray(result.body), false);
  return result.body as Record<string, unknown>;
}

function assertDenied(result: RouteResult, status: number, error: string) {
  assert.equal(result.response.status, status);
  const body = objectBody(result);
  assert.equal(body.error, error);
  assert.equal(Object.hasOwn(body, "memories"), false);
  assert.equal(body.token_omitted, true);
}

async function seed(client: Client) {
  const now = new Date().toISOString();
  const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  await client.query(
    `INSERT INTO users(user_id,name,email,role,created_at) VALUES
      ('usr_memory_operator','Memory operator','memory-operator@example.invalid','operator',$1),
      ('usr_memory_viewer','Memory viewer','memory-viewer@example.invalid','viewer',$1)`,
    [now],
  );
  await client.query(
    `INSERT INTO workspace_memberships(
      workspace_id,user_id,role,status,created_at,updated_at
    ) VALUES
      ($1,'usr_memory_operator','operator','active',$3,$3),
      ($1,'usr_memory_viewer','viewer','active',$3,$3),
      ($2,'usr_memory_operator','operator','active',$3,$3)`,
    [WORKSPACE, FOREIGN_WORKSPACE, now],
  );
  await client.query(
    `INSERT INTO human_sessions(
      session_id,user_id,session_hash,status,created_at,expires_at,last_seen_at,revoked_at
    ) VALUES
      ('hsess_memory_operator','usr_memory_operator',$1,'active',$3,$4,$3,NULL),
      ('hsess_memory_viewer','usr_memory_viewer',$2,'active',$3,$4,$3,NULL)`,
    [hmac("session", OPERATOR_TOKEN), hmac("session", VIEWER_TOKEN), now, future],
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
    `INSERT INTO memories(
      memory_id,workspace_id,scope,memory_type,canonical_text,source_type,
      source_ref,project_id,task_id,run_id,agent_id,confidence,review_status,
      owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,
      created_at,updated_at
    )
    SELECT
      'mem_export_' || lpad(item::text,3,'0'),$1,'project','project_context',
      'Bounded commercial memory ' || item,'manual',$2,'commercial-project',
      NULL,NULL,NULL,0.75,
      CASE WHEN item % 2=0 THEN 'approved' ELSE 'candidate' END,
      'usr_memory_operator',NULL,NULL,$3,$4::timestamptz,
      ($4::timestamptz + item * interval '1 second')::text
    FROM generate_series(1,205) item`,
    [WORKSPACE, SECRET_CANARY, JSON.stringify([SECRET_CANARY]), now],
  );
  await client.query(
    `INSERT INTO memories(
      memory_id,workspace_id,scope,memory_type,canonical_text,source_type,
      source_ref,project_id,task_id,run_id,agent_id,confidence,review_status,
      owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,
      created_at,updated_at
    ) VALUES(
      'mem_export_foreign',$1,'org','policy',$2,'manual',$2,NULL,NULL,NULL,NULL,
      1,'approved','usr_memory_operator',NULL,NULL,$3,$4,$4
    )`,
    [FOREIGN_WORKSPACE, SECRET_CANARY, JSON.stringify([SECRET_CANARY]), now],
  );
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
    paths: () => paths,
    close: () => new Promise<void>((resolve, reject) =>
      server.close((error) => error ? reject(error) : resolve())),
  };
}

async function assertStaticBoundary() {
  const source = (await Promise.all([
    "../src/server/controlPlane/memoryCandidates.ts",
    "../app/api/mis/memories/route.ts",
    "../app/api/mis/memories/export/route.ts",
  ].map((path) => readFile(new URL(path, import.meta.url), "utf8")))).join("\n");
  assert.match(source, /authenticateHumanMember/);
  assert.match(source, /HUMAN_MEMORY_READ_ROLES/);
  assert.match(source, /workspace_entitlements/);
  assert.match(source, /WHERE workspace_id=\$1/);
  assert.match(source, /LIMIT \$3/);
  assert.match(source, /human\.memory_\$\{options\.operation\}_read/);
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
  const fixture = await createPostgresRoleBoundaryFixture(BASE_DSN, "memory_export");
  const proxy = await startProxyProbe();
  let restoreRuntime: () => void = () => undefined;
  try {
    activeStage = "seed";
    await seed(fixture.owner);
    restoreRuntime = fixture.activateRuntimeEnvironment();
    process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = HMAC_KEY;
    process.env.AGENTOPS_API_BASE = proxy.base;

    activeStage = "production_export";
    const production = await call("export", OPERATOR_TOKEN, {
      deployment: "production",
    });
    assert.equal(production.response.status, 200);
    const body = objectBody(production);
    assert.equal(body.control_plane, "typescript_postgres");
    assert.equal(body.workspace_id, WORKSPACE);
    assert.equal(body.python_proxy_performed, false);
    assert.equal(body.audit_recorded, true);
    assert.deepEqual(body.bounds, { memories: 200 });
    const memories = body.memories as Array<Record<string, unknown>>;
    assert.equal(memories.length, 200);
    assert.equal(Object.hasOwn(memories[0], "source_ref"), false);
    assert.equal(Object.hasOwn(memories[0], "owner_user_id"), false);
    assert.equal(Object.hasOwn(memories[0], "access_tags"), false);
    assert.equal(JSON.stringify(body).includes(SECRET_CANARY), false);
    assert.equal(production.response.headers.get("cache-control"), "no-store");
    assert.equal(
      production.response.headers.get("vary"),
      "Cookie, X-AgentOps-Workspace-Id",
    );

    activeStage = "shared_export";
    const shared = await call("export", OPERATOR_TOKEN, {
      deployment: "shared",
      reviewStatus: "approved",
      limit: "1",
    });
    assert.equal(shared.response.status, 200);
    const sharedBody = objectBody(shared);
    assert.equal((sharedBody.memories as unknown[]).length, 1);
    assert.equal(sharedBody.python_proxy_performed, false);
    assert.equal(proxy.calls(), 0);

    activeStage = "candidate_list";
    const candidates = await call("list");
    assert.equal(candidates.response.status, 200);
    assert.equal(Array.isArray(candidates.body), true);
    assert.equal((candidates.body as unknown[]).length, 103);
    assert.equal(JSON.stringify(candidates.body).includes(SECRET_CANARY), false);

    activeStage = "audit";
    const audits = (await fixture.owner.query<{
      action: string;
      workspace_id: string;
      actor_id: string;
      metadata_json: string;
    }>(
      `SELECT action,workspace_id,actor_id,metadata_json
      FROM audit_logs
      WHERE action IN ('human.memory_export_read','human.memory_candidates_read')
      ORDER BY created_at`,
    )).rows;
    assert.equal(audits.length, 3);
    assert.equal(audits.every((row) => row.workspace_id === WORKSPACE), true);
    assert.equal(audits.every((row) => row.actor_id === "usr_memory_operator"), true);
    assert.equal(JSON.stringify(audits).includes(SECRET_CANARY), false);

    activeStage = "rbac";
    assertDenied(
      await call("export", VIEWER_TOKEN),
      403,
      "human_memory_read_role_forbidden",
    );
    activeStage = "machine_credential";
    assertDenied(
      await call("export", OPERATOR_TOKEN, { machineCredential: true }),
      401,
      "machine_credential_not_allowed",
    );
    activeStage = "cross_workspace";
    assertDenied(
      await call("export", OPERATOR_TOKEN, {
        queryWorkspace: FOREIGN_WORKSPACE,
      }),
      403,
      "forbidden",
    );
    activeStage = "query_bounds";
    assertDenied(
      await call("export", OPERATOR_TOKEN, { unsupported: true }),
      400,
      "human_memory_query_unsupported",
    );
    assertDenied(
      await call("list", OPERATOR_TOKEN, { unsupported: true }),
      400,
      "human_memory_query_unsupported",
    );
    assertDenied(
      await call("list", OPERATOR_TOKEN, {
        queryWorkspace: WORKSPACE,
        duplicateWorkspace: true,
      }),
      400,
      "human_memory_query_ambiguous",
    );
    assertDenied(
      await call("export", OPERATOR_TOKEN, { limit: "201" }),
      400,
      "human_memory_limit_invalid",
    );
    assertDenied(
      await call("export", OPERATOR_TOKEN, { reviewStatus: "unknown" }),
      400,
      "human_memory_review_status_invalid",
    );

    activeStage = "entitlement";
    await fixture.owner.query(
      "UPDATE workspace_entitlements SET status='suspended' WHERE workspace_id=$1",
      [WORKSPACE],
    );
    assertDenied(
      await call("export"),
      403,
      "workspace_entitlement_suspended",
    );
    await fixture.owner.query(
      `UPDATE workspace_entitlements SET status='active',edition='free_local'
      WHERE workspace_id=$1`,
      [WORKSPACE],
    );
    assertDenied(
      await call("export"),
      403,
      "workspace_entitlement_edition_forbidden",
    );

    activeStage = "free_local_proxy";
    const freeExport = await call("export", OPERATOR_TOKEN, {
      deployment: "free_local",
      reviewStatus: "approved",
      limit: "2",
    });
    assert.equal(freeExport.response.status, 200);
    assert.equal(objectBody(freeExport).free_local_proxy, true);
    const freeList = await call("list", OPERATOR_TOKEN, {
      deployment: "free_local",
    });
    assert.equal(freeList.response.status, 200);
    assert.equal(objectBody(freeList).free_local_proxy, true);
    assert.deepEqual(proxy.paths(), [
      "/api/memories/export?review_status=approved&limit=2",
      "/api/memories",
    ]);

    console.log(JSON.stringify({
      ok: true,
      contract: "human_memory_export_postgres_v1",
      schema_contract: fixture.migration.schema_contract,
      production_and_shared_typescript_postgres: true,
      workspace_session_binding: true,
      rbac_verified: true,
      active_commercial_entitlement_required: true,
      cross_workspace_fail_closed: true,
      bounded_response_limit: 200,
      access_audit_recorded: true,
      sensitive_fields_omitted: true,
      runtime_role_boundary_verified: true,
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
    contract: "human_memory_export_postgres_v1",
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
