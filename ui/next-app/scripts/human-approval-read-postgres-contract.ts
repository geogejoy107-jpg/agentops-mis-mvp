import assert from "node:assert/strict";
import { createHash, createHmac, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

import { NextRequest } from "next/server";
import { Client } from "pg";

import { GET as getApproval } from "../app/api/mis/approvals/[approvalId]/route";
import { GET as getApprovals } from "../app/api/mis/approvals/route";
import { closeControlPlanePoolForTests } from "../src/server/controlPlane/db";
import { stableHash } from "../src/server/controlPlane/ledger";
import { createPostgresRoleBoundaryFixture } from "./postgres-role-boundary-test-helper";

const BASE_DSN = String(process.env.AGENTOPS_POSTGRES_DSN || "").trim();
const WORKSPACE = "ws_approval_read";
const FOREIGN_WORKSPACE = "ws_approval_read_foreign";
const APPROVAL_ID = "apr_read_000";
const FOREIGN_APPROVAL_ID = "apr_read_foreign";
const SECRET_CANARY = "approval-read-sensitive-canary-must-not-leak";
const OPERATOR_TOKEN = randomBytes(32).toString("base64url");
const VIEWER_TOKEN = randomBytes(32).toString("base64url");
const HMAC_KEY = randomBytes(48).toString("base64url");
const PLAN_ID = "plan_approval_read";
const MANIFEST_ID = "pem_approval_read";
const TOOL_ID = "tc_approval_read";
const EVALUATION_ID = "eval_approval_read";
const ARTIFACT_ID = "art_approval_read";

type Result = Readonly<{ response: Response; body: unknown }>;

function hmac(token: string) {
  return createHmac("sha256", HMAC_KEY)
    .update(`session:${token}`, "utf8")
    .digest("hex");
}

function sha(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

async function reserveRun(
  client: Client,
  workspaceId: string,
  runId: string,
  createdAt: string,
) {
  await client.query(
    `INSERT INTO run_cost_reservations(
      reservation_id,workspace_id,run_id,billing_class,billing_month_utc,state,
      estimated_cost_usd,observed_cost_usd,idempotency_key_hash,request_hash,
      reserved_at,expires_at,updated_at
    ) VALUES($1,$2,$3,'historical_execution',
      date_trunc('month',$4::timestamptz)::date,'reserved',0.001,0,$5,$6,
      $4::timestamptz,$4::timestamptz+interval '1 hour',$4::timestamptz)`,
    [
      `rsv_${runId}`,
      workspaceId,
      runId,
      createdAt,
      sha(`approval-read-reservation:${workspaceId}:${runId}`),
      sha(`approval-read-request:${workspaceId}:${runId}`),
    ],
  );
}

async function settleRun(client: Client, workspaceId: string, runId: string) {
  await client.query(
    `SELECT reservation_id FROM agentops_settle_run_cost_v10($1,$2,0,$3,$4)`,
    [
      workspaceId,
      runId,
      sha(`approval-read-settle:${workspaceId}:${runId}`),
      sha(`approval-read-settle-request:${workspaceId}:${runId}`),
    ],
  );
}

function verificationHash(
  planId: string,
  verification: Record<string, unknown>,
) {
  const quality = verification.quality as Record<string, unknown>;
  return stableHash({
    plan_id: planId,
    plan_hash: verification.plan_hash,
    pass: verification.pass,
    failed_checks: [],
    summary: verification.summary,
    quality: {
      version: quality.version,
      score: quality.score,
      status: quality.status,
      failed_rubric_ids: quality.failed_rubric_ids,
    },
  });
}

function request(
  path: string,
  options: Readonly<{
    token?: string;
    workspace?: string;
    query?: string;
    machineCredential?: boolean;
  }> = {},
) {
  const suffix = options.query ? `?${options.query}` : "";
  const headers = new Headers({
    cookie: `agentops_human_session=${options.token || OPERATOR_TOKEN}`,
    "x-agentops-workspace-id": options.workspace || WORKSPACE,
  });
  if (options.machineCredential) {
    headers.set("authorization", "Bearer machine-credential-forbidden");
  }
  return new NextRequest(`https://mis.example.test${path}${suffix}`, {
    method: "GET",
    headers,
  });
}

async function collection(
  options?: Parameters<typeof request>[1],
): Promise<Result> {
  const response = await getApprovals(request("/api/mis/approvals", options));
  return { response, body: await response.json() };
}

async function detail(
  approvalId: string,
  options?: Parameters<typeof request>[1],
): Promise<Result> {
  const response = await getApproval(
    request(`/api/mis/approvals/${encodeURIComponent(approvalId)}`, options),
    { params: Promise.resolve({ approvalId }) },
  );
  return { response, body: await response.json() };
}

function denied(result: Result, status: number, error: string) {
  assert.equal(result.response.status, status);
  assert.equal((result.body as Record<string, unknown>).error, error);
  assert.equal((result.body as Record<string, unknown>).token_omitted, true);
}

async function seed(client: Client) {
  const now = new Date().toISOString();
  const createdAt = new Date(Date.now() - 10_000).toISOString();
  const verifiedAt = new Date(Date.now() - 5_000).toISOString();
  const future = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  const steps = ["READ", "PLAN", "EXECUTE", "VERIFY", "RECORD"];
  const planContract = {
    workspace_id: WORKSPACE,
    task_id: "tsk_approval_read",
    run_id: "run_approval_read",
    agent_id: "agt_approval_read",
    task_understanding: "Read a bounded commercial approval receipt.",
    referenced_specs: ["commercial-approval-read-v1"],
    referenced_memories: [],
    referenced_bases: [],
    proposed_files_to_change: [],
    risk_level: "medium",
    approval_required: false,
    execution_steps: steps,
    verification_plan: "Verify the bounded PostgreSQL evidence graph.",
    rollback_plan: "Keep customer delivery blocked.",
    plan_version: 1,
  };
  const planHash = stableHash(planContract);
  const planVerification = {
    pass: true,
    plan_hash: planHash,
    failed_checks: [],
    summary: { quality_score: 100 },
    quality: {
      version: "agent_plan_quality_v1",
      score: 100,
      status: "ready",
      failed_rubric_ids: [],
    },
  };
  const verificationResultHash = verificationHash(PLAN_ID, planVerification);
  await client.query(
    `INSERT INTO users(user_id,name,email,role,created_at) VALUES
      ('usr_approval_operator','Approval operator',
        'approval-operator@example.invalid','operator',$1),
      ('usr_approval_viewer','Approval viewer',
        'approval-viewer@example.invalid','viewer',$1)`,
    [now],
  );
  await client.query(
    `INSERT INTO workspace_memberships(
      workspace_id,user_id,role,status,created_at,updated_at
    ) VALUES
      ($1,'usr_approval_operator','operator','active',$2,$2),
      ($1,'usr_approval_viewer','viewer','active',$2,$2)`,
    [WORKSPACE, now],
  );
  await client.query(
    `INSERT INTO human_sessions(
      session_id,user_id,session_hash,status,created_at,expires_at,
      last_seen_at,revoked_at
    ) VALUES
      ('hsess_approval_operator','usr_approval_operator',$1,'active',$3,$4,$3,NULL),
      ('hsess_approval_viewer','usr_approval_viewer',$2,'active',$3,$4,$3,NULL)`,
    [hmac(OPERATOR_TOKEN), hmac(VIEWER_TOKEN), now, future],
  );
  await client.query(
    `INSERT INTO workspace_entitlements(
      workspace_id,edition,status,capabilities_json,max_agents,
      max_active_enrollments,max_active_sessions_per_agent,max_monthly_runs,
      max_monthly_cost_usd,max_concurrent_runs,effective_at,expires_at
    ) VALUES
      ($1,'team_governance','active','{}',20,20,20,1000,1000,20,
        clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 year'),
      ($2,'enterprise_byoc','active','{}',20,20,20,1000,1000,20,
        clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 year')`,
    [WORKSPACE, FOREIGN_WORKSPACE],
  );
  await client.query(
    `INSERT INTO agents(
      agent_id,name,role,description,runtime_type,model_provider,model_name,
      status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,
      created_at,updated_at
    ) VALUES
      ('agt_approval_read','Approval Agent','worker',NULL,'openclaw',
        'openclaw','commercial-model','idle','standard','[]',1,NULL,$1,$1),
      ('agt_approval_foreign',$2,'worker',$2,'hermes',$2,$2,'idle',
        'standard','[]',1,NULL,$1,$1)`,
    [now, SECRET_CANARY],
  );
  await client.query(
    `INSERT INTO tasks(
      task_id,workspace_id,title,description,requester_id,owner_agent_id,
      collaborator_agent_ids,status,priority,due_date,acceptance_criteria,
      risk_level,budget_limit_usd,created_at,updated_at
    ) VALUES
      ('tsk_approval_read',$1,'Approval read task',NULL,
        'usr_approval_operator','agt_approval_read','[]','waiting_approval',
        'high',NULL,NULL,'high',1,$3,$3),
      ('tsk_approval_foreign',$2,$4,$4,'usr_approval_operator',
        'agt_approval_foreign','[]','waiting_approval','high',NULL,$4,
        'high',1,$3,$3)`,
    [WORKSPACE, FOREIGN_WORKSPACE, now, SECRET_CANARY],
  );
  await client.query(
    `INSERT INTO agent_plans(
      plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,
      referenced_specs_json,referenced_memories_json,referenced_bases_json,
      proposed_files_to_change_json,risk_level,approval_required,
      execution_steps_json,verification_plan,rollback_plan,status,plan_version,
      plan_hash,verified_at,verification_result_hash,approval_id,
      approved_by_user_id,approved_at,created_at,updated_at
    ) VALUES($1,$2,'tsk_approval_read',NULL,'agt_approval_read',$3,$4,'[]','[]',
      '[]','medium',0,$5,$6,$7,'submitted',1,$8,$9,$10,NULL,NULL,NULL,$11,$9)`,
    [
      PLAN_ID,
      WORKSPACE,
      planContract.task_understanding,
      JSON.stringify(planContract.referenced_specs),
      JSON.stringify(steps),
      planContract.verification_plan,
      planContract.rollback_plan,
      planHash,
      verifiedAt,
      verificationResultHash,
      createdAt,
    ],
  );
  await reserveRun(client, WORKSPACE, "run_approval_read", now);
  await reserveRun(client, FOREIGN_WORKSPACE, "run_approval_foreign", now);
  await client.query(
    `INSERT INTO runs(
      run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,
      ended_at,duration_ms,input_summary,output_summary,model_provider,
      model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,
      error_type,error_message,trace_id,parent_run_id,delegation_id,
      approval_required,agent_plan_id,plan_hash,billing_class,created_at
    ) VALUES
      ('run_approval_read',$1,'tsk_approval_read','agt_approval_read',
        'openclaw','completed',$3,$3,1,$4,$4,'openclaw',
        'commercial-model',0,0,0,0,NULL,$4,$4,NULL,NULL,1,NULL,NULL,
        'historical_execution',$3),
      ('run_approval_foreign',$2,'tsk_approval_foreign','agt_approval_foreign',
        'hermes','waiting_approval',$3,NULL,1,$4,$4,'hermes',$4,0,0,0,0,
        NULL,$4,$4,NULL,NULL,1,NULL,NULL,'historical_execution',$3)`,
    [WORKSPACE, FOREIGN_WORKSPACE, now, SECRET_CANARY],
  );
  await client.query(
    "UPDATE runs SET agent_plan_id=$1,plan_hash=$2 WHERE run_id='run_approval_read'",
    [PLAN_ID, planHash],
  );
  await client.query(
    "UPDATE agent_plans SET run_id='run_approval_read' WHERE plan_id=$1",
    [PLAN_ID],
  );
  await settleRun(client, WORKSPACE, "run_approval_read");
  await client.query(
    `INSERT INTO tool_calls(
      tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,
      normalized_args_json,target_resource,risk_level,status,result_summary,
      side_effect_id,started_at,ended_at,created_at
    ) VALUES($1,'run_approval_read','agt_approval_read','agent_worker.openclaw',
      'v1','custom',$2,NULL,'low','completed',NULL,NULL,$3,$4,$3)`,
    [
      TOOL_ID,
      JSON.stringify({
        adapter: "openclaw",
        provider_call_performed: true,
        dry_run: false,
      }),
      createdAt,
      verifiedAt,
    ],
  );
  await client.query(
    `INSERT INTO evaluations(
      evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,
      rubric_json,notes,created_at
    ) VALUES($1,'tsk_approval_read','run_approval_read','agt_approval_read',
      'rule',1,'pass',$2,NULL,$3)`,
    [
      EVALUATION_ID,
      JSON.stringify({
        adapter: "openclaw",
        provider_call_performed: true,
        dry_run: false,
      }),
      createdAt,
    ],
  );
  await client.query(
    `INSERT INTO artifacts(
      artifact_id,task_id,run_id,artifact_type,title,uri,summary,
      content_hash,created_at
    ) VALUES($1,'tsk_approval_read','run_approval_read','report',
      'Approval read artifact',NULL,NULL,$2,$3)`,
    [ARTIFACT_ID, sha("approval-read-artifact"), createdAt],
  );
  const auditRows = [
    ["aud_approval_plan", "agent_gateway.agent_plan_create", "agent_plans", PLAN_ID, {}],
    ["aud_approval_tool", "tool_call.create", "tool_calls", TOOL_ID, {}],
    ["aud_approval_eval", "evaluation.create", "evaluations", EVALUATION_ID, {}],
    ["aud_approval_art", "agent_gateway.artifact_record", "artifacts", ARTIFACT_ID, {
      content_hash: sha("approval-read-artifact"),
    }],
    ["aud_approval_worker", "agent_worker.task_processed", "runs", "run_approval_read", {
      adapter: "openclaw",
      provider_call_performed: true,
      dry_run: false,
    }],
  ] as const;
  for (const [auditId, action, entityType, entityId, metadata] of auditRows) {
    await client.query(
      `INSERT INTO audit_logs(
        audit_id,workspace_id,actor_type,actor_id,action,entity_type,entity_id,
        before_hash,after_hash,metadata_json,tamper_chain_hash,created_at
      ) VALUES($1,$2,'agent','agt_approval_read',$3,$4,$5,NULL,NULL,$6,$7,$8)`,
      [
        auditId,
        WORKSPACE,
        action,
        entityType,
        entityId,
        JSON.stringify({ ...metadata, workspace_id: WORKSPACE }),
        sha(`approval-read-chain:${auditId}`),
        createdAt,
      ],
    );
  }
  await client.query(
    `INSERT INTO plan_evidence_manifests(
      manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,
      expected_steps_json,tool_call_ids_json,evaluation_ids_json,
      artifact_ids_json,audit_ids_json,plan_hash,verification_result_hash,
      status,verification_json,created_at,updated_at
    ) VALUES($1,$2,$3,'tsk_approval_read','run_approval_read',
      'agt_approval_read','block',$4,$5,$6,$7,'[]',$8,$9,'verified',$10,$11,$12)`,
    [
      MANIFEST_ID,
      WORKSPACE,
      PLAN_ID,
      JSON.stringify(steps),
      JSON.stringify([TOOL_ID]),
      JSON.stringify([EVALUATION_ID]),
      JSON.stringify([ARTIFACT_ID]),
      planHash,
      verificationResultHash,
      JSON.stringify({
        pass: true,
        status: "verified",
        failed_checks: [],
        plan_verification: planVerification,
      }),
      createdAt,
      verifiedAt,
    ],
  );
  await client.query(
    `INSERT INTO approvals(
      approval_id,approval_kind,task_id,run_id,tool_call_id,
      requested_by_agent_id,approver_user_id,decision,reason,expires_at,
      created_at,decided_at
    ) VALUES($1,'customer_delivery','tsk_approval_read','run_approval_read',NULL,
      'agt_approval_read',NULL,'pending',$2,$3,$4,NULL)`,
    [APPROVAL_ID, SECRET_CANARY, future, now],
  );
  await client.query(
    `INSERT INTO approvals(
      approval_id,approval_kind,task_id,run_id,tool_call_id,
      requested_by_agent_id,approver_user_id,decision,reason,expires_at,
      created_at,decided_at
    ) VALUES($1,'customer_delivery','tsk_approval_foreign',
      'run_approval_foreign',NULL,'agt_approval_foreign',NULL,'pending',$2,$3,$4,NULL)`,
    [FOREIGN_APPROVAL_ID, SECRET_CANARY, future, now],
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
  const [collectionRoute, detailRoute, queue, decisions, boundary] =
    await Promise.all([
      readFile(new URL("../app/api/mis/approvals/route.ts", import.meta.url), "utf8"),
      readFile(new URL("../app/api/mis/approvals/[approvalId]/route.ts", import.meta.url), "utf8"),
      readFile(new URL("../src/server/controlPlane/approvalQueue.ts", import.meta.url), "utf8"),
      readFile(new URL("../src/server/controlPlane/approvalDecisions.ts", import.meta.url), "utf8"),
      readFile(new URL("../src/server/controlPlane/approvalReadBoundary.ts", import.meta.url), "utf8"),
    ]);
  for (const route of [collectionRoute, detailRoute]) {
    assert.match(route, /legacyPythonProxyAllowed/);
    assert.match(route, /proxyControlPlaneRequest/);
    assert.match(route, /Cache-Control/);
  }
  for (const owner of [queue, decisions, boundary]) {
    assert.doesNotMatch(owner, /proxyControlPlaneRequest/);
    assert.doesNotMatch(owner, /sqlite/i);
  }
  assert.doesNotMatch(queue, /approval\.reason/);
  assert.doesNotMatch(queue, /action\.target_resource/);
  assert.doesNotMatch(queue, /action\.provider_side_effect_id/);
  assert.match(queue, /human\.approval_collection_read/);
  assert.match(decisions, /human\.approval_detail_read/);
  assert.match(boundary, /workspace_entitlements/);
}

async function main() {
  assert.ok(BASE_DSN, "PostgreSQL contract DSN is required");
  process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = HMAC_KEY;
  process.env.AGENTOPS_POSTGRES_POOL_MAX = "8";
  await staticBoundary();
  const fixture = await createPostgresRoleBoundaryFixture(
    BASE_DSN,
    "approval_read",
  );
  const restoreRuntime = fixture.activateRuntimeEnvironment();
  let probe: Awaited<ReturnType<typeof startProxyProbe>> | undefined;
  try {
    const version = await fixture.owner.query<{ server_version_num: string }>(
      "SHOW server_version_num",
    );
    assert.equal(Math.floor(Number(version.rows[0].server_version_num) / 10_000), 16);
    assert.equal(fixture.migration.schema_contract, "agentops_commercial_postgres_v11");
    await seed(fixture.owner);

    probe = await startProxyProbe();
    process.env.AGENTOPS_API_BASE = probe.base;

    const listed = await collection({
      query: `workspace_id=${WORKSPACE}&decision=pending`,
    });
    assert.equal(listed.response.status, 200);
    assert.equal(listed.response.headers.get("cache-control"), "no-store");
    const rows = listed.body as Array<Record<string, unknown>>;
    assert.equal(rows.length, 1);
    assert.equal(rows[0].reason_omitted, true);
    assert.equal(rows[0].target_resource_omitted, true);
    assert.equal(rows[0].provider_side_effect_id_omitted, true);
    assert.equal(JSON.stringify(rows).includes(SECRET_CANARY), false);
    const bounded = await collection({
      query: `workspace_id=${WORKSPACE}&limit=1`,
    });
    assert.equal((bounded.body as unknown[]).length, 1);
    denied(await collection({
      query: `workspace_id=${WORKSPACE}&limit=201`,
    }), 400, "approval_limit_invalid");

    const receipt = await detail(APPROVAL_ID, {
      query: `workspace_id=${WORKSPACE}`,
    });
    assert.equal(receipt.response.status, 200);
    assert.equal(receipt.response.headers.get("cache-control"), "no-store");
    const receiptBody = receipt.body as Record<string, unknown>;
    assert.equal(receiptBody.control_plane, "typescript_postgres");
    assert.equal(receiptBody.python_proxy_performed, false);
    assert.equal(receiptBody.sensitive_fields_omitted, true);
    assert.equal(receiptBody.audit_recorded, true);
    assert.equal(JSON.stringify(receiptBody).includes(SECRET_CANARY), false);

    denied(await collection({ query: `workspace_id=${WORKSPACE}&raw=true` }), 400,
      "approval_read_query_unsupported");
    denied(await collection({
      query: `workspace_id=${WORKSPACE}&workspace_id=${WORKSPACE}`,
    }), 400, "approval_read_query_ambiguous");
    denied(await collection({ query: "workspace_id=" }), 400,
      "approval_read_query_invalid");
    denied(await collection({
      query: `workspace_id=${WORKSPACE}&decision=%20pending%20`,
    }), 400, "approval_read_query_invalid");
    denied(await collection({
      query: `workspace_id=${WORKSPACE}&limit=001`,
    }), 400, "approval_limit_invalid");
    denied(await detail(APPROVAL_ID, {
      query: `workspace_id=${WORKSPACE}&limit=1`,
    }), 400, "approval_read_query_unsupported");
    denied(await detail("../foreign", { query: `workspace_id=${WORKSPACE}` }), 400,
      "approval_id_invalid");
    denied(await collection({
      token: VIEWER_TOKEN,
      query: `workspace_id=${WORKSPACE}`,
    }), 403, "human_approval_read_role_forbidden");
    denied(await collection({
      query: `workspace_id=${WORKSPACE}`,
      machineCredential: true,
    }), 401, "machine_credential_not_allowed");
    denied(await collection({
      workspace: WORKSPACE,
      query: `workspace_id=${FOREIGN_WORKSPACE}`,
    }), 403, "forbidden");
    denied(await detail(FOREIGN_APPROVAL_ID, {
      query: `workspace_id=${WORKSPACE}`,
    }), 404, "approval_not_found");

    await fixture.owner.query(
      "UPDATE workspace_entitlements SET status='suspended' WHERE workspace_id=$1",
      [WORKSPACE],
    );
    denied(await collection({ query: `workspace_id=${WORKSPACE}` }), 403,
      "workspace_entitlement_suspended");
    await fixture.owner.query(
      "UPDATE workspace_entitlements SET status='active' WHERE workspace_id=$1",
      [WORKSPACE],
    );

    const audits = await fixture.owner.query<{ action: string }>(
      `SELECT action FROM audit_logs WHERE workspace_id=$1
      AND action IN ('human.approval_collection_read','human.approval_detail_read')
      ORDER BY action`,
      [WORKSPACE],
    );
    assert.deepEqual(
      new Set(audits.rows.map((row) => row.action)),
      new Set(["human.approval_collection_read", "human.approval_detail_read"]),
    );
    assert.equal(probe.calls(), 0);

    await closeControlPlanePoolForTests();
    restoreRuntime();
    process.env.AGENTOPS_DEPLOYMENT_MODE = "free_local";
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    const localList = await collection();
    const localDetail = await detail(APPROVAL_ID);
    assert.equal(localList.response.status, 200);
    assert.equal(localDetail.response.status, 200);
    assert.equal((localList.body as Record<string, unknown>).free_local_proxy, true);
    assert.equal((localDetail.body as Record<string, unknown>).free_local_proxy, true);
    assert.equal(probe.calls(), 2);

    console.log(JSON.stringify({
      contract: "human_approval_read_postgres_v1",
      postgres_major: 16,
      schema_contract: fixture.migration.schema_contract,
      production_typescript_postgres: true,
      production_python_proxy_calls: 0,
      free_local_python_proxy_preserved: true,
      collection_bound: 200,
      cross_workspace_isolation: true,
      commercial_entitlement_fail_closed: true,
      rbac_fail_closed: true,
      sensitive_projection_omitted: true,
      read_audit_recorded: true,
    }));
  } finally {
    await closeControlPlanePoolForTests().catch(() => undefined);
    if (probe) await probe.close().catch(() => undefined);
    await fixture.cleanup();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
