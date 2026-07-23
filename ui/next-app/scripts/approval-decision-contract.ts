import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHmac, randomBytes } from "node:crypto";
import http from "node:http";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { NextRequest } from "next/server";
import { Client, type Pool, type PoolClient } from "pg";

import { POST as decideApprovalRoute } from "../app/api/mis/approvals/[approvalId]/[decision]/route";
import { POST as reviewApprovalFormRoute } from "../app/workspace/approvals/review/route";
import { appendAudit } from "../src/server/controlPlane/ledger";

const NEXT_APP_ROOT = fileURLToPath(new URL("../", import.meta.url));
const TSX_PATH = fileURLToPath(new URL("../node_modules/.bin/tsx", import.meta.url));
const MIGRATOR_PATH = fileURLToPath(new URL("./migrate-postgres.ts", import.meta.url));

const ORIGIN = "http://127.0.0.1:3001";
const WORKSPACE_A = "ws_approval_a";
const WORKSPACE_B = "ws_approval_b";
const APPROVER_A = "usr_approval_a";
const VIEWER_A = "usr_viewer_a";
const OPERATOR_A = "usr_operator_a";
const APPROVER_B = "usr_approval_b";
const TOKEN_A = randomBytes(32).toString("base64url");
const TOKEN_VIEWER = randomBytes(32).toString("base64url");
const TOKEN_OPERATOR = randomBytes(32).toString("base64url");
const TOKEN_B = randomBytes(32).toString("base64url");
const HMAC_KEY = `approval-decision-contract-${randomBytes(32).toString("hex")}`;
const MACHINE_CREDENTIAL = randomBytes(32).toString("base64url");
const AGENT_A = "agt_approval_a";
const AGENT_B = "agt_approval_b";
let currentStage = "bootstrap";

type Row = Record<string, unknown>;
type Decision = "approve" | "reject";
type ApprovalKind =
  | "tool_execution"
  | "prepared_action"
  | "run_execution"
  | "agent_enrollment"
  | "customer_delivery";

function output(value: Record<string, unknown>) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

function sslEnabled() {
  return ["1", "true", "require", "required", "on"]
    .includes(String(process.env.AGENTOPS_POSTGRES_SSL || "").trim().toLowerCase());
}

function scopedDsn(dsn: string, schema: string) {
  const url = new URL(dsn);
  url.searchParams.set("options", `-csearch_path=${schema}`);
  return url.toString();
}

function hmac(label: string, value: string) {
  return createHmac("sha256", HMAC_KEY).update(`${label}:${value}`, "utf8").digest("hex");
}

function csrf(token: string) {
  return hmac("csrf", token);
}

function sessionHash(token: string) {
  return hmac("session", token);
}

function assertExactFields(value: unknown, expected: string[], label: string) {
  assert.ok(value && typeof value === "object" && !Array.isArray(value), `${label}_must_be_object`);
  assert.deepEqual(Object.keys(value as Row).sort(), [...expected].sort(), `${label}_field_mismatch`);
}

function assertPrivateHeaders(response: Response) {
  assert.match(String(response.headers.get("cache-control") || ""), /no-store/i);
  const vary = String(response.headers.get("vary") || "").toLowerCase();
  assert.ok(vary.includes("cookie"), "private_response_must_vary_cookie");
  assert.ok(vary.includes("x-agentops-workspace-id"), "private_response_must_vary_workspace");
}

function decisionHeaders(input: {
  token?: string;
  workspaceId?: string;
  csrfToken?: string;
  idempotencyKey?: string;
  origin?: string;
  host?: string;
  machineCredential?: boolean;
}) {
  const headers = new Headers({
    "content-type": "application/json",
    host: input.host ?? "127.0.0.1:3001",
    origin: input.origin ?? ORIGIN,
  });
  if (input.token) headers.set("cookie", `agentops_human_session=${encodeURIComponent(input.token)}`);
  if (input.workspaceId) headers.set("x-agentops-workspace-id", input.workspaceId);
  if (input.csrfToken) headers.set("x-agentops-csrf", input.csrfToken);
  if (input.idempotencyKey) headers.set("idempotency-key", input.idempotencyKey);
  if (input.machineCredential) headers.set("authorization", `Bearer ${MACHINE_CREDENTIAL}`);
  return headers;
}

async function callDecision(input: {
  approvalId: string;
  decision: string;
  token?: string;
  workspaceId?: string;
  csrfToken?: string;
  idempotencyKey?: string;
  origin?: string;
  host?: string;
  machineCredential?: boolean;
  body?: Record<string, unknown>;
}) {
  const request = new NextRequest(
    `${ORIGIN}/api/mis/approvals/${encodeURIComponent(input.approvalId)}/${encodeURIComponent(input.decision)}`,
    {
      method: "POST",
      headers: decisionHeaders(input),
      body: JSON.stringify(input.body ?? (input.workspaceId ? { workspace_id: input.workspaceId } : {})),
    },
  );
  return decideApprovalRoute(request, {
    params: Promise.resolve({ approvalId: input.approvalId, decision: input.decision }),
  });
}

async function callAsApprover(
  approvalId: string,
  requestedDecision: Decision,
  idempotencyKey: string,
) {
  return callDecision({
    approvalId,
    decision: requestedDecision,
    token: TOKEN_A,
    workspaceId: WORKSPACE_A,
    csrfToken: csrf(TOKEN_A),
    idempotencyKey,
  });
}

async function json(response: Response) {
  const body = await response.json() as Row;
  assertNoSensitiveOutput(body);
  return body;
}

function assertNoSensitiveOutput(value: unknown) {
  const serialized = JSON.stringify(value);
  for (const secret of [
    HMAC_KEY,
    TOKEN_A,
    TOKEN_VIEWER,
    TOKEN_OPERATOR,
    TOKEN_B,
    MACHINE_CREDENTIAL,
  ]) {
    assert.equal(serialized.includes(secret), false, "sensitive_value_exposed");
  }
  const visit = (candidate: unknown) => {
    if (Array.isArray(candidate)) {
      candidate.forEach(visit);
      return;
    }
    if (!candidate || typeof candidate !== "object") return;
    for (const [key, item] of Object.entries(candidate as Row)) {
      const normalized = key.toLowerCase();
      const sensitiveField = /^(?:credential|credentials|token)(?:_|$)/.test(normalized)
        || /(?:^|_)(?:csrf_token|session_token|access_token|refresh_token)$/.test(normalized)
        || /^raw_(?:body|payload|prompt|response|transcript)(?:_|$)/.test(normalized);
      if (sensitiveField) {
        assert.match(normalized, /_omitted$/, `sensitive_output_key:${key}`);
        assert.equal(item, true, `sensitive_output_not_omitted:${key}`);
      }
      visit(item);
    }
  };
  visit(value);
}

function safeFailureDiagnostic(error: unknown) {
  const source = error instanceof Error ? error.message : String(error);
  let message = source;
  for (const secret of [
    HMAC_KEY,
    TOKEN_A,
    TOKEN_VIEWER,
    TOKEN_OPERATOR,
    TOKEN_B,
    MACHINE_CREDENTIAL,
  ]) {
    message = message.replaceAll(secret, "[REDACTED]");
  }
  message = message
    .replace(/postgres(?:ql)?:\/\/[^\s'"}]+/gi, "postgresql://[REDACTED]")
    .replace(/(bearer\s+)[a-z0-9._-]+/gi, "$1[REDACTED]")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 240);
  const stack = error instanceof Error ? String(error.stack || "") : "";
  const location = stack.match(/approval-decision-contract\.ts:\d+:\d+/)?.[0] || null;
  return {
    assertion: message || "assertion_failed",
    location,
  };
}

async function expectError(response: Response, status: number, code: string) {
  assert.equal(response.status, status);
  assertPrivateHeaders(response);
  const body = await json(response);
  assert.equal(body.error, code);
  assert.equal(body.token_omitted, true);
  return body;
}

async function createBaseSchema(client: Client) {
  await client.query(`
    CREATE TABLE users(user_id TEXT PRIMARY KEY,name TEXT NOT NULL);
    CREATE TABLE agents(agent_id TEXT PRIMARY KEY,name TEXT NOT NULL,status TEXT NOT NULL);
    CREATE TABLE tasks(
      task_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,title TEXT NOT NULL,description TEXT,
      status TEXT NOT NULL,priority TEXT NOT NULL,risk_level TEXT NOT NULL,owner_agent_id TEXT,
      collaborator_agent_ids TEXT NOT NULL DEFAULT '[]',acceptance_criteria TEXT,
      budget_limit_usd DOUBLE PRECISION NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
    );
    CREATE TABLE runs(
      run_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,task_id TEXT NOT NULL,agent_id TEXT NOT NULL,
      runtime_type TEXT NOT NULL,model_provider TEXT,status TEXT NOT NULL,
      approval_required INTEGER NOT NULL DEFAULT 0,
      started_at TEXT NOT NULL,ended_at TEXT,duration_ms INTEGER,input_summary TEXT,output_summary TEXT,
      error_type TEXT,error_message TEXT,cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
      parent_run_id TEXT,delegation_id TEXT,created_at TEXT NOT NULL
    );
    CREATE TABLE tool_calls(
      tool_call_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,agent_id TEXT NOT NULL,tool_name TEXT NOT NULL,
      tool_version TEXT NOT NULL,tool_category TEXT NOT NULL,normalized_args_json TEXT NOT NULL,
      target_resource TEXT,risk_level TEXT NOT NULL,status TEXT NOT NULL,result_summary TEXT,
      side_effect_id TEXT,started_at TEXT NOT NULL,ended_at TEXT,created_at TEXT NOT NULL
    );
    CREATE TABLE approvals(
      approval_id TEXT PRIMARY KEY,decision TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,
      tool_call_id TEXT,requested_by_agent_id TEXT,approver_user_id TEXT,reason TEXT,expires_at TEXT,
      decided_at TEXT,created_at TEXT NOT NULL
    );
    CREATE TABLE memories(
      memory_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,scope TEXT NOT NULL,memory_type TEXT NOT NULL,
      canonical_text TEXT NOT NULL,source_type TEXT NOT NULL,source_ref TEXT,confidence DOUBLE PRECISION NOT NULL,
      review_status TEXT NOT NULL,task_id TEXT,agent_id TEXT,ttl_review_due_at TEXT,
      access_tags TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
    );
    CREATE TABLE evaluations(
      evaluation_id TEXT PRIMARY KEY,task_id TEXT NOT NULL,run_id TEXT NOT NULL,agent_id TEXT NOT NULL,
      evaluator_type TEXT NOT NULL,score DOUBLE PRECISION NOT NULL,pass_fail TEXT NOT NULL,
      rubric_json TEXT NOT NULL,notes TEXT,created_at TEXT NOT NULL
    );
    CREATE TABLE artifacts(
      artifact_id TEXT PRIMARY KEY,task_id TEXT,run_id TEXT,artifact_type TEXT NOT NULL,title TEXT NOT NULL,
      uri TEXT,summary TEXT,created_at TEXT NOT NULL
    );
    CREATE TABLE audit_logs(
      audit_id TEXT PRIMARY KEY,actor_type TEXT NOT NULL,actor_id TEXT,action TEXT NOT NULL,
      entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,before_hash TEXT,after_hash TEXT,
      metadata_json TEXT NOT NULL DEFAULT '{}',tamper_chain_hash TEXT,created_at TEXT NOT NULL
    );
    CREATE TABLE runtime_events(
      runtime_event_id TEXT PRIMARY KEY,runtime_connector_id TEXT,event_type TEXT NOT NULL,status TEXT NOT NULL,
      run_id TEXT,task_id TEXT,agent_id TEXT,model_name TEXT,latency_ms INTEGER,prompt_hash TEXT,
      input_summary TEXT,output_summary TEXT,error_message TEXT,raw_payload_hash TEXT,created_at TEXT NOT NULL
    );
    CREATE TABLE agent_gateway_tokens(
      token_id TEXT PRIMARY KEY,token_hash TEXT NOT NULL UNIQUE,workspace_id TEXT NOT NULL,agent_id TEXT NOT NULL,
      scopes_json TEXT NOT NULL,status TEXT NOT NULL,label TEXT,heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 300,
      created_at TEXT NOT NULL,expires_at TEXT,revoked_at TEXT,last_used_at TEXT,last_heartbeat_at TEXT
    );
    CREATE TABLE agent_gateway_sessions(
      session_id TEXT PRIMARY KEY,session_hash TEXT NOT NULL UNIQUE,parent_token_id TEXT,workspace_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,scopes_json TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,
      expires_at TEXT NOT NULL,revoked_at TEXT,last_used_at TEXT
    );
    CREATE TABLE prepared_actions(
      prepared_action_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,
      tool_call_id TEXT NOT NULL,approval_id TEXT,requested_by_agent_id TEXT,status TEXT NOT NULL,
      updated_at TEXT NOT NULL,approved_at TEXT,created_at TEXT NOT NULL
    );
    CREATE TABLE agent_gateway_enrollment_requests(
      request_id TEXT PRIMARY KEY,approval_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,
      workspace_id TEXT NOT NULL,agent_id TEXT NOT NULL,status TEXT NOT NULL,updated_at TEXT NOT NULL,
      decided_at TEXT,token_id TEXT,created_at TEXT NOT NULL
    );
    CREATE TABLE agent_plans(
      plan_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,task_id TEXT,run_id TEXT,agent_id TEXT NOT NULL,
      task_understanding TEXT NOT NULL,referenced_specs_json TEXT NOT NULL,referenced_memories_json TEXT NOT NULL,
      referenced_bases_json TEXT NOT NULL,proposed_files_to_change_json TEXT NOT NULL,risk_level TEXT NOT NULL,
      approval_required INTEGER NOT NULL,execution_steps_json TEXT NOT NULL,verification_plan TEXT,
      rollback_plan TEXT,status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
    );
    CREATE TABLE plan_evidence_manifests(
      manifest_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,plan_id TEXT NOT NULL,task_id TEXT,run_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,mismatch_policy TEXT NOT NULL,expected_steps_json TEXT NOT NULL,
      tool_call_ids_json TEXT NOT NULL,evaluation_ids_json TEXT NOT NULL,artifact_ids_json TEXT NOT NULL,
      audit_ids_json TEXT NOT NULL,status TEXT NOT NULL,verification_json TEXT NOT NULL,
      created_at TEXT NOT NULL,updated_at TEXT NOT NULL
    );
  `);
}

async function applyMigrations(dsn: string) {
  const result = await new Promise<{ exitCode: number | null; stdout: string; stderr: string }>((resolve, reject) => {
    const child = spawn(TSX_PATH, [MIGRATOR_PATH], {
      cwd: NEXT_APP_ROOT,
      env: {
        ...process.env,
        AGENTOPS_POSTGRES_DSN: dsn,
        DATABASE_URL: dsn,
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => { stdout += chunk; });
    child.stderr.on("data", (chunk: string) => { stderr += chunk; });
    child.once("error", reject);
    child.once("close", (exitCode) => resolve({ exitCode, stdout, stderr }));
  });
  const finalOutput = result.stdout.trim().split("\n").filter(Boolean).at(-1) || "{}";
  assert.equal(result.exitCode, 0, `real_migration_runner_failed:${finalOutput.slice(0, 240)}`);
  const receipt = JSON.parse(finalOutput) as Row;
  assert.equal(receipt.ready, true);
  assert.equal(receipt.credentials_omitted, true);
  assert.equal(JSON.stringify(receipt).includes(HMAC_KEY), false);
  for (const token of [
    TOKEN_A,
    TOKEN_VIEWER,
    TOKEN_OPERATOR,
    TOKEN_B,
    MACHINE_CREDENTIAL,
  ]) {
    assert.equal(JSON.stringify(receipt).includes(token), false);
  }
}

type ApprovalCase = {
  name: string;
  approvalKind: ApprovalKind;
  workspaceId?: string;
  agentId?: string;
  toolRisk?: string;
  expiresAt?: string | null;
  reason?: string;
};

async function seedCase(client: Client, input: ApprovalCase) {
  const workspaceId = input.workspaceId || WORKSPACE_A;
  const agentId = input.agentId || AGENT_A;
  const now = new Date().toISOString();
  const taskId = `tsk_${input.name}`;
  const runId = `run_${input.name}`;
  const approvalId = `ap_${input.name}`;
  const toolId = input.toolRisk ? `tool_${input.name}` : null;
  await client.query(
    `INSERT INTO tasks(
      task_id,workspace_id,title,status,priority,risk_level,owner_agent_id,collaborator_agent_ids,
      budget_limit_usd,created_at,updated_at
    ) VALUES($1,$2,$1,'waiting_approval','high',$3,$4,'[]',10,$5,$5)`,
    [taskId, workspaceId, input.toolRisk || "medium", agentId, now],
  );
  await client.query(
    `INSERT INTO runs(
      run_id,workspace_id,task_id,agent_id,runtime_type,model_provider,status,
      approval_required,started_at,cost_usd,created_at
    ) VALUES($1,$2,$3,$4,'openclaw','openclaw','waiting_approval',1,$5,0,$5)`,
    [runId, workspaceId, taskId, agentId, now],
  );
  if (toolId) {
    await client.query(
      `INSERT INTO tool_calls(
        tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,
        risk_level,status,started_at,created_at
      ) VALUES($1,$2,$3,'contract-tool','1','action','{}',$4,'waiting_approval',$5,$5)`,
      [toolId, runId, agentId, input.toolRisk, now],
    );
  }
  await client.query(
    `INSERT INTO approvals(
      approval_id,approval_kind,decision,task_id,run_id,tool_call_id,requested_by_agent_id,reason,expires_at,created_at
    ) VALUES($1,$2,'pending',$3,$4,$5,$6,$7,$8,$9)`,
    [
      approvalId,
      input.approvalKind,
      taskId,
      runId,
      toolId,
      agentId,
      input.reason || `${input.name} approval`,
      input.expiresAt || null,
      now,
    ],
  );
  return { approvalId, approvalKind: input.approvalKind, taskId, runId, toolId, workspaceId, agentId, now };
}

async function seedFixtures(client: Client) {
  const now = new Date();
  const nowText = now.toISOString();
  const future = new Date(now.getTime() + 60 * 60 * 1000).toISOString();
  const past = new Date(now.getTime() - 60 * 60 * 1000).toISOString();
  await client.query(
    `INSERT INTO users(user_id,name) VALUES
      ($1,'Approver A'),($2,'Viewer A'),($3,'Operator A'),($4,'Approver B')`,
    [APPROVER_A, VIEWER_A, OPERATOR_A, APPROVER_B],
  );
  await client.query(
    `INSERT INTO workspace_memberships(workspace_id,user_id,role,status,created_at,updated_at) VALUES
      ($1,$3,'approver','active',$7,$7),
      ($1,$4,'viewer','active',$7,$7),
      ($1,$5,'operator','active',$7,$7),
      ($2,$6,'owner','active',$7,$7)`,
    [WORKSPACE_A, WORKSPACE_B, APPROVER_A, VIEWER_A, OPERATOR_A, APPROVER_B, nowText],
  );
  await client.query(
    `INSERT INTO human_sessions(session_id,user_id,session_hash,status,created_at,expires_at) VALUES
      ('hss_approval_a',$1,$5,'active',$9,$10),
      ('hss_viewer_a',$2,$6,'active',$9,$10),
      ('hss_operator_a',$3,$7,'active',$9,$10),
      ('hss_approval_b',$4,$8,'active',$9,$10)`,
    [
      APPROVER_A,
      VIEWER_A,
      OPERATOR_A,
      APPROVER_B,
      sessionHash(TOKEN_A),
      sessionHash(TOKEN_VIEWER),
      sessionHash(TOKEN_OPERATOR),
      sessionHash(TOKEN_B),
      nowText,
      future,
    ],
  );
  await client.query(
    "INSERT INTO agents(agent_id,name,status) VALUES($1,'Agent A','running'),($2,'Agent B','running')",
    [AGENT_A, AGENT_B],
  );
  await client.query(
    `INSERT INTO memories(
      memory_id,workspace_id,scope,memory_type,canonical_text,source_type,confidence,review_status,
      access_tags,created_at,updated_at
    ) VALUES('mem_contract',$1,'org','fact','fixture','manual',1,'approved','[]',$2,$2)`,
    [WORKSPACE_A, nowText],
  );

  const ordinary = await seedCase(client, { name: "ordinary", approvalKind: "run_execution" });
  const rejected = await seedCase(client, {
    name: "rejected",
    approvalKind: "tool_execution",
    toolRisk: "medium",
  });
  const prepared = await seedCase(client, {
    name: "prepared",
    approvalKind: "prepared_action",
    toolRisk: "high",
  });
  const preparedRejected = await seedCase(client, {
    name: "prepared_rejected",
    approvalKind: "prepared_action",
    toolRisk: "critical",
  });
  const expired = await seedCase(client, {
    name: "expired",
    approvalKind: "run_execution",
    expiresAt: past,
  });
  const high = await seedCase(client, {
    name: "high_unprepared",
    approvalKind: "tool_execution",
    toolRisk: "critical",
  });
  const enrollment = await seedCase(client, { name: "enrollment", approvalKind: "agent_enrollment" });
  const enrollmentRejected = await seedCase(client, {
    name: "enrollment_rejected",
    approvalKind: "agent_enrollment",
  });
  const delivery = await seedCase(client, {
    name: "kind_bound_delivery_missing_manifest",
    approvalKind: "customer_delivery",
    reason: "Release checkpoint review",
  });
  const deliveryVerified = await seedCase(client, {
    name: "kind_bound_delivery_verified_manifest",
    approvalKind: "customer_delivery",
    reason: "Release checkpoint review",
  });
  const deliveryRejected = await seedCase(client, {
    name: "kind_bound_delivery_rejected",
    approvalKind: "customer_delivery",
    reason: "Release checkpoint review",
  });
  const deliveryIncompleteRejected = await seedCase(client, {
    name: "kind_bound_delivery_incomplete_rejected",
    approvalKind: "customer_delivery",
    reason: "Release checkpoint review",
  });
  const deliveryHeuristicDecoy = await seedCase(client, {
    name: "customer_worker_delivery_decoy",
    approvalKind: "run_execution",
    reason: "Customer delivery approval",
  });
  const siblingPrepared = await seedCase(client, {
    name: "sibling_prepared_target",
    approvalKind: "prepared_action",
    toolRisk: "high",
  });
  const siblingEnrollment = await seedCase(client, {
    name: "sibling_enrollment_target",
    approvalKind: "agent_enrollment",
  });
  const parentFirstRun = await seedCase(client, {
    name: "parent_first_run",
    approvalKind: "run_execution",
  });
  const parentFirstTool = await seedCase(client, {
    name: "parent_first_tool",
    approvalKind: "tool_execution",
    toolRisk: "medium",
  });
  const toolBeforeApproval = await seedCase(client, {
    name: "tool_before_approval",
    approvalKind: "tool_execution",
    toolRisk: "medium",
  });
  const foreign = await seedCase(client, {
    name: "foreign",
    approvalKind: "run_execution",
    workspaceId: WORKSPACE_B,
    agentId: AGENT_B,
  });
  const form = await seedCase(client, { name: "form", approvalKind: "run_execution" });
  const race = await seedCase(client, { name: "race", approvalKind: "run_execution" });
  const collision = await seedCase(client, { name: "collision", approvalKind: "run_execution" });
  const production = await seedCase(client, { name: "production", approvalKind: "run_execution" });
  const terminalOrdinary = await seedCase(client, {
    name: "terminal_ordinary",
    approvalKind: "run_execution",
  });

  await client.query(
    "UPDATE runs SET status='completed',ended_at=$1 WHERE run_id=$2",
    [nowText, delivery.runId],
  );
  await client.query(
    "UPDATE runs SET status='completed',ended_at=$1 WHERE run_id=$2",
    [nowText, terminalOrdinary.runId],
  );
  await client.query(
    "UPDATE tasks SET status='completed',updated_at=$1 WHERE task_id=$2",
    [nowText, terminalOrdinary.taskId],
  );
  await client.query(
    `UPDATE runs SET status='completed',ended_at=$1,duration_ms=417,
      output_summary='Bounded customer delivery execution evidence.',error_type=NULL,error_message=NULL
    WHERE run_id=$2`,
    [nowText, deliveryRejected.runId],
  );

  const siblingPreparedRejectorId = "ap_sibling_prepared_rejector";
  const siblingEnrollmentRejectorId = "ap_sibling_enrollment_rejector";
  await client.query(
    `INSERT INTO approvals(
      approval_id,approval_kind,decision,task_id,run_id,tool_call_id,requested_by_agent_id,reason,created_at
    ) VALUES
      ($1,'run_execution','pending',$2,$3,NULL,$4,'Reject sibling Prepared Action',$8),
      ($5,'run_execution','pending',$6,$7,NULL,$4,'Reject sibling enrollment',$8)`,
    [
      siblingPreparedRejectorId,
      siblingPrepared.taskId,
      siblingPrepared.runId,
      AGENT_A,
      siblingEnrollmentRejectorId,
      siblingEnrollment.taskId,
      siblingEnrollment.runId,
      nowText,
    ],
  );

  await client.query(
    `INSERT INTO prepared_actions(
      prepared_action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,requested_by_agent_id,
      status,updated_at,created_at
    ) VALUES
      ('pa_prepared',$1,$2,$3,$4,$5,$6,'waiting_approval',$11,$11),
      ('pa_prepared_rejected',$1,$7,$8,$9,$10,$6,'waiting_approval',$11,$11)`,
    [
      WORKSPACE_A,
      prepared.taskId,
      prepared.runId,
      prepared.toolId,
      prepared.approvalId,
      AGENT_A,
      preparedRejected.taskId,
      preparedRejected.runId,
      preparedRejected.toolId,
      preparedRejected.approvalId,
      nowText,
    ],
  );
  await client.query(
    `INSERT INTO prepared_actions(
      prepared_action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,requested_by_agent_id,
      status,updated_at,created_at
    ) VALUES('pa_sibling_prepared',$1,$2,$3,$4,$5,$6,'waiting_approval',$7,$7)`,
    [
      WORKSPACE_A,
      siblingPrepared.taskId,
      siblingPrepared.runId,
      siblingPrepared.toolId,
      siblingPrepared.approvalId,
      AGENT_A,
      nowText,
    ],
  );
  await client.query(
    `INSERT INTO agent_gateway_enrollment_requests(
      request_id,approval_id,task_id,run_id,workspace_id,agent_id,status,updated_at,token_id,created_at
    ) VALUES
      ('enr_approval',$1,$2,$3,$7,$8,'pending',$9,NULL,$9),
      ('enr_rejected',$4,$5,$6,$7,$8,'pending',$9,NULL,$9)`,
    [
      enrollment.approvalId,
      enrollment.taskId,
      enrollment.runId,
      enrollmentRejected.approvalId,
      enrollmentRejected.taskId,
      enrollmentRejected.runId,
      WORKSPACE_A,
      AGENT_A,
      nowText,
    ],
  );
  await client.query(
    `INSERT INTO agent_gateway_enrollment_requests(
      request_id,approval_id,task_id,run_id,workspace_id,agent_id,status,updated_at,token_id,created_at
    ) VALUES('enr_sibling',$1,$2,$3,$4,$5,'pending',$6,NULL,$6)`,
    [
      siblingEnrollment.approvalId,
      siblingEnrollment.taskId,
      siblingEnrollment.runId,
      WORKSPACE_A,
      AGENT_A,
      nowText,
    ],
  );

  const deliveryRejectionEvidence = {
    runtimeEventId: "rte_delivery_rejection_evidence",
    evaluationId: "eval_delivery_rejection_evidence",
    artifactId: "art_delivery_rejection_evidence",
  };
  await client.query(
    `INSERT INTO runtime_events(
      runtime_event_id,event_type,status,run_id,task_id,agent_id,output_summary,created_at
    ) VALUES($1,'run.completed','completed',$2,$3,$4,'Bounded execution evidence.',$5)`,
    [
      deliveryRejectionEvidence.runtimeEventId,
      deliveryRejected.runId,
      deliveryRejected.taskId,
      AGENT_A,
      nowText,
    ],
  );
  await client.query(
    `INSERT INTO evaluations(
      evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at
    ) VALUES($1,$2,$3,$4,'rule',1,'pass','{}','Delivery execution passed.',$5)`,
    [
      deliveryRejectionEvidence.evaluationId,
      deliveryRejected.taskId,
      deliveryRejected.runId,
      AGENT_A,
      nowText,
    ],
  );
  await client.query(
    `INSERT INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,summary,created_at)
    VALUES($1,$2,$3,'delivery','Completed delivery evidence','Bounded artifact evidence.',$4)`,
    [deliveryRejectionEvidence.artifactId, deliveryRejected.taskId, deliveryRejected.runId, nowText],
  );

  const planId = "plan_delivery_verified";
  const evidenceToolId = "tool_delivery_verified";
  const evaluationId = "eval_delivery_verified";
  const artifactId = "art_delivery_verified";
  const auditId = "aud_delivery_verified";
  const manifestId = "manifest_delivery_verified";
  const steps = JSON.stringify(["read", "execute", "verify"]);
  await client.query(
    `INSERT INTO agent_plans(
      plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,referenced_specs_json,
      referenced_memories_json,referenced_bases_json,proposed_files_to_change_json,risk_level,
      approval_required,execution_steps_json,verification_plan,rollback_plan,status,created_at,updated_at
    ) VALUES($1,$2,$3,$4,$5,'Verify customer delivery',$6,$7,$8,$9,'low',0,$10,
      'Verify all evidence','Keep delivery pending','submitted',$11,$11)`,
    [
      planId,
      WORKSPACE_A,
      deliveryVerified.taskId,
      deliveryVerified.runId,
      AGENT_A,
      JSON.stringify(["commercial-readiness"]),
      JSON.stringify(["mem_contract"]),
      JSON.stringify(["agent-gateway"]),
      JSON.stringify(["delivery-artifact"]),
      steps,
      nowText,
    ],
  );
  await client.query(
    `INSERT INTO tool_calls(
      tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,
      risk_level,status,started_at,ended_at,created_at
    ) VALUES($1,$2,$3,'agent_worker.openclaw','1','action',$4,'low','completed',$5,$5,$5)`,
    [
      evidenceToolId,
      deliveryVerified.runId,
      AGENT_A,
      JSON.stringify({
        adapter: "openclaw",
        provider_call_performed: true,
        dry_run: false,
        raw_omitted: true,
      }),
      nowText,
    ],
  );
  await client.query(
    `INSERT INTO evaluations(
      evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,created_at
    ) VALUES($1,$2,$3,$4,'rule',1,'pass',$5,$6)`,
    [
      evaluationId,
      deliveryVerified.taskId,
      deliveryVerified.runId,
      AGENT_A,
      JSON.stringify({
        adapter: "openclaw",
        provider_call_performed: true,
        dry_run: false,
        raw_prompt_response_omitted: true,
      }),
      nowText,
    ],
  );
  await client.query(
    `INSERT INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,created_at)
    VALUES($1,$2,$3,'delivery','Verified delivery',$4)`,
    [artifactId, deliveryVerified.taskId, deliveryVerified.runId, nowText],
  );
  await client.query(
    `INSERT INTO runs(
      run_id,workspace_id,task_id,agent_id,runtime_type,model_provider,status,approval_required,
      started_at,ended_at,cost_usd,created_at
    ) VALUES('run_delivery_verified_sibling',$1,$2,$3,'openclaw','openclaw','completed',0,$4,$4,0,$4)`,
    [WORKSPACE_A, deliveryVerified.taskId, AGENT_A, nowText],
  );
  await client.query(
    `INSERT INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,created_at)
    VALUES('art_delivery_verified_sibling',$1,'run_delivery_verified_sibling',
      'delivery','Sibling run artifact must not satisfy this run',$2)`,
    [deliveryVerified.taskId, nowText],
  );
  await client.query(
    `INSERT INTO audit_logs(
      audit_id,workspace_id,actor_type,actor_id,action,entity_type,entity_id,metadata_json,created_at
    ) VALUES($1,$2,'system','contract-fixture','contract.fixture_marker','agent_plans',$3,$4,$5)`,
    [auditId, WORKSPACE_A, planId, JSON.stringify({ workspace_id: WORKSPACE_A }), nowText],
  );
  const auditClient = client as unknown as PoolClient;
  await appendAudit(auditClient, {
    workspaceId: WORKSPACE_A,
    actorType: "agent",
    actorId: AGENT_A,
    action: "agent_gateway.agent_plan_create",
    entityType: "agent_plans",
    entityId: planId,
    after: { plan_id: planId, status: "submitted" },
    metadata: { workspace_id: WORKSPACE_A, raw_omitted: true },
  });
  await appendAudit(auditClient, {
    workspaceId: WORKSPACE_A,
    actorType: "system",
    actorId: "agent-gateway",
    action: "tool_call.create",
    entityType: "tool_calls",
    entityId: evidenceToolId,
    after: { tool_call_id: evidenceToolId, status: "completed" },
    metadata: { workspace_id: WORKSPACE_A, raw_omitted: true },
  });
  await appendAudit(auditClient, {
    workspaceId: WORKSPACE_A,
    actorType: "system",
    actorId: "agent-gateway",
    action: "evaluation.create",
    entityType: "evaluations",
    entityId: evaluationId,
    after: { evaluation_id: evaluationId, pass_fail: "pass" },
    metadata: { workspace_id: WORKSPACE_A, raw_payload_omitted: true },
  });
  await appendAudit(auditClient, {
    workspaceId: WORKSPACE_A,
    actorType: "agent",
    actorId: AGENT_A,
    action: "agent_gateway.artifact_record",
    entityType: "artifacts",
    entityId: artifactId,
    after: { artifact_id: artifactId, run_id: deliveryVerified.runId },
    metadata: {
      workspace_id: WORKSPACE_A,
      content_hash: hmac("artifact", artifactId),
      raw_content_omitted: true,
    },
  });
  await appendAudit(auditClient, {
    workspaceId: WORKSPACE_A,
    actorType: "agent",
    actorId: AGENT_A,
    action: "agent_worker.task_processed",
    entityType: "runs",
    entityId: deliveryVerified.runId,
    after: { status: "completed" },
    metadata: {
      workspace_id: WORKSPACE_A,
      adapter: "openclaw",
      provider_call_performed: true,
      dry_run: false,
      raw_omitted: true,
    },
  });
  await client.query(
    `INSERT INTO plan_evidence_manifests(
      manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,expected_steps_json,
      tool_call_ids_json,evaluation_ids_json,artifact_ids_json,audit_ids_json,status,verification_json,
      created_at,updated_at
    ) VALUES($1,$2,$3,$4,$5,$6,'block',$7,$8,$9,$10,$11,'verified','{}',$12,$12)`,
    [
      manifestId,
      WORKSPACE_A,
      planId,
      deliveryVerified.taskId,
      deliveryVerified.runId,
      AGENT_A,
      steps,
      JSON.stringify([evidenceToolId]),
      JSON.stringify([evaluationId]),
      JSON.stringify([artifactId]),
      JSON.stringify([]),
      nowText,
    ],
  );
  const cases = {
    ordinary,
    rejected,
    prepared,
    preparedRejected,
    expired,
    high,
    enrollment,
    enrollmentRejected,
    delivery,
    deliveryVerified,
    deliveryRejected: { ...deliveryRejected, evidence: deliveryRejectionEvidence },
    deliveryIncompleteRejected,
    deliveryHeuristicDecoy,
    siblingPrepared: { ...siblingPrepared, rejectorApprovalId: siblingPreparedRejectorId },
    siblingEnrollment: { ...siblingEnrollment, rejectorApprovalId: siblingEnrollmentRejectorId },
    parentFirstRun,
    parentFirstTool,
    toolBeforeApproval,
    foreign,
    form,
    race,
    collision,
    production,
    terminalOrdinary,
  };
  return cases;
}

async function seed(client: Client) {
  await client.query("BEGIN");
  try {
    const cases = await seedFixtures(client);
    await client.query("COMMIT");
    return cases;
  } catch (error) {
    await client.query("ROLLBACK").catch(() => undefined);
    throw error;
  }
}

async function row(client: Client, table: string, idColumn: string, id: string) {
  if (!/^[a-z_]+$/.test(table) || !/^[a-z_]+$/.test(idColumn)) throw new Error("unsafe_contract_query");
  const result = await client.query<Row>(`SELECT * FROM ${table} WHERE ${idColumn}=$1`, [id]);
  return result.rows[0];
}

async function count(client: Client, table: string) {
  if (!/^[a-z_]+$/.test(table)) throw new Error("unsafe_contract_query");
  const result = await client.query<{ count: number }>(`SELECT COUNT(*)::int AS count FROM ${table}`);
  return Number(result.rows[0]?.count || 0);
}

async function expectTransactionalFailure(
  client: Client,
  expectedCode: string,
  label: string,
  operation: () => Promise<void>,
  expectedMessage?: string,
) {
  let failure: unknown;
  await client.query("BEGIN");
  try {
    await operation();
    await client.query("SET CONSTRAINTS ALL IMMEDIATE");
  } catch (error) {
    failure = error;
  } finally {
    await client.query("ROLLBACK").catch(() => undefined);
  }
  assert.equal((failure as { code?: string } | undefined)?.code, expectedCode, label);
  if (expectedMessage) {
    assert.equal((failure as { message?: string } | undefined)?.message, expectedMessage, label);
  }
}

async function expectTransactionalSuccess(
  client: Client,
  label: string,
  operation: () => Promise<void>,
) {
  let failure: unknown;
  await client.query("BEGIN");
  try {
    await operation();
    await client.query("SET CONSTRAINTS ALL IMMEDIATE");
  } catch (error) {
    failure = error;
  } finally {
    await client.query("ROLLBACK").catch(() => undefined);
  }
  assert.equal(
    failure,
    undefined,
    `${label}:${String((failure as { code?: string } | undefined)?.code || "unexpected_failure")}`,
  );
}

async function verifyApprovalKindDatabaseBindings(client: Client, cases: {
  ordinary: { approvalId: string; taskId: string; runId: string };
  rejected: { approvalId: string };
  prepared: { approvalId: string; taskId: string; runId: string; toolId: string | null };
  enrollment: { approvalId: string; taskId: string; runId: string };
  foreign: { taskId: string; runId: string };
}) {
  const now = new Date().toISOString();
  await expectTransactionalFailure(client, "23502", "approval_kind_must_be_explicit", async () => {
    await client.query(
      `INSERT INTO approvals(
        approval_id,decision,task_id,run_id,requested_by_agent_id,reason,created_at
      ) VALUES('ap_missing_explicit_kind','pending',$1,$2,$3,'No implicit kind',$4)`,
      [cases.ordinary.taskId, cases.ordinary.runId, AGENT_A, now],
    );
  });
  await expectTransactionalFailure(client, "23514", "approval_kind_enum_must_be_exact", async () => {
    await client.query(
      `INSERT INTO approvals(
        approval_id,approval_kind,decision,task_id,run_id,requested_by_agent_id,reason,created_at
      ) VALUES('ap_invalid_kind','delivery','pending',$1,$2,$3,'Invalid kind',$4)`,
      [cases.ordinary.taskId, cases.ordinary.runId, AGENT_A, now],
    );
  });
  await expectTransactionalFailure(client, "23514", "approval_kind_must_be_immutable", async () => {
    await client.query(
      "UPDATE approvals SET approval_kind='customer_delivery' WHERE approval_id=$1",
      [cases.ordinary.approvalId],
    );
  });
  await expectTransactionalFailure(client, "23505", "enrollment_approval_binding_must_be_unique", async () => {
    await client.query(
      `INSERT INTO agent_gateway_enrollment_requests(
        request_id,approval_id,task_id,run_id,workspace_id,agent_id,status,updated_at,created_at
      ) VALUES('enr_duplicate_binding',$1,$2,$3,$4,$5,'pending',$6,$6)`,
      [cases.enrollment.approvalId, cases.enrollment.taskId, cases.enrollment.runId, WORKSPACE_A, AGENT_A, now],
    );
  });
  await expectTransactionalFailure(client, "23514", "prepared_action_workspace_edge_must_match", async () => {
    await client.query(
      "UPDATE prepared_actions SET workspace_id=$1 WHERE approval_id=$2",
      [WORKSPACE_B, cases.prepared.approvalId],
    );
  });
  await expectTransactionalFailure(client, "23514", "enrollment_workspace_edge_must_match", async () => {
    await client.query(
      "UPDATE agent_gateway_enrollment_requests SET workspace_id=$1 WHERE approval_id=$2",
      [WORKSPACE_B, cases.enrollment.approvalId],
    );
  });
  await expectTransactionalFailure(client, "23514", "prepared_action_orphan_binding_must_fail", async () => {
    await client.query(
      `INSERT INTO prepared_actions(
        prepared_action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,requested_by_agent_id,
        status,updated_at,created_at
      ) VALUES('pa_orphan_binding',$1,$2,$3,$4,'ap_missing_parent',$5,'waiting_approval',$6,$6)`,
      [WORKSPACE_A, cases.prepared.taskId, cases.prepared.runId, cases.prepared.toolId, AGENT_A, now],
    );
  });
  await expectTransactionalFailure(client, "23514", "approval_task_run_workspace_edge_must_match", async () => {
    await client.query(
      "UPDATE approvals SET task_id=$1 WHERE approval_id=$2",
      [cases.foreign.taskId, cases.ordinary.approvalId],
    );
  });
  await expectTransactionalFailure(client, "23514", "approval_binding_must_be_immutable_even_when_rebind_is_consistent", async () => {
    await client.query(
      `UPDATE approvals SET task_id=$1,run_id=$2,requested_by_agent_id=$3
      WHERE approval_id=$4`,
      [cases.foreign.taskId, cases.foreign.runId, AGENT_B, cases.ordinary.approvalId],
    );
  });
  await expectTransactionalFailure(client, "23514", "approval_tool_run_workspace_edge_must_match", async () => {
    await client.query(
      `INSERT INTO tool_calls(
        tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,
        risk_level,status,started_at,created_at
      ) VALUES('tool_foreign_binding',$1,$2,'foreign','1','action','{}','medium','waiting_approval',$3,$3)`,
      [cases.foreign.runId, AGENT_B, now],
    );
    await client.query(
      "UPDATE approvals SET tool_call_id='tool_foreign_binding' WHERE approval_id=$1",
      [cases.rejected.approvalId],
    );
  });
  await expectTransactionalFailure(client, "23514", "approval_ledger_must_be_append_only", async () => {
    await client.query("DELETE FROM approvals WHERE approval_id=$1", [cases.rejected.approvalId]);
  }, "approval_append_only");
  await expectTransactionalFailure(client, "23514", "task_workspace_binding_must_be_immutable", async () => {
    await client.query(
      "UPDATE tasks SET workspace_id=$1 WHERE task_id=$2",
      [WORKSPACE_B, cases.ordinary.taskId],
    );
  }, "approval_parent_binding_immutable");
  await expectTransactionalFailure(client, "23514", "run_execution_binding_must_be_immutable", async () => {
    await client.query(
      "UPDATE runs SET task_id=$1,workspace_id=$2,agent_id=$3 WHERE run_id=$4",
      [cases.foreign.taskId, WORKSPACE_B, AGENT_B, cases.ordinary.runId],
    );
  }, "approval_parent_binding_immutable");
  await expectTransactionalFailure(client, "23514", "tool_execution_binding_must_be_immutable", async () => {
    await client.query(
      "UPDATE tool_calls SET run_id=$1,agent_id=$2 WHERE tool_call_id=$3",
      [cases.foreign.runId, AGENT_B, cases.prepared.toolId],
    );
  }, "approval_parent_binding_immutable");
  await expectTransactionalFailure(client, "23514", "audit_ledger_update_must_fail", async () => {
    await client.query(
      "UPDATE audit_logs SET action='tampered' WHERE audit_id='aud_delivery_verified'",
    );
  }, "audit_log_append_only");
  await expectTransactionalFailure(client, "23514", "audit_ledger_delete_must_fail", async () => {
    await client.query("DELETE FROM audit_logs WHERE audit_id='aud_delivery_verified'");
  }, "audit_log_append_only");
  await expectTransactionalFailure(client, "23514", "prepared_action_delete_must_not_orphan_approval", async () => {
    await client.query("DELETE FROM prepared_actions WHERE approval_id=$1", [cases.prepared.approvalId]);
  });
  await expectTransactionalFailure(client, "23514", "prepared_action_approval_delete_must_not_orphan_child", async () => {
    await client.query("DELETE FROM approvals WHERE approval_id=$1", [cases.prepared.approvalId]);
  });
  await expectTransactionalFailure(client, "23514", "enrollment_delete_must_not_orphan_approval", async () => {
    await client.query("DELETE FROM agent_gateway_enrollment_requests WHERE approval_id=$1", [cases.enrollment.approvalId]);
  });
  await expectTransactionalFailure(client, "23514", "enrollment_approval_delete_must_not_orphan_child", async () => {
    await client.query("DELETE FROM approvals WHERE approval_id=$1", [cases.enrollment.approvalId]);
  });
}

async function verifyOrdinaryAndIdempotency(client: Client, approvalId: string, runId: string, taskId: string) {
  const key = "approval-ordinary-0001";
  const first = await callAsApprover(approvalId, "approve", key);
  assert.equal(first.status, 200);
  assertPrivateHeaders(first);
  const firstBody = await json(first);
  assertExactFields(firstBody, [
    "approval", "control_plane", "credentials_omitted", "decision", "linked_state", "ok", "operation",
    "outcome", "provider", "raw_body_omitted", "token_omitted",
  ], "approval_decision_response");
  assert.equal(firstBody.outcome, "updated");
  assert.equal(firstBody.decision, "approved");
  assertExactFields(firstBody.approval, [
    "approval_id", "approval_kind", "approver_user_id", "created_at", "decided_at", "decision", "expires_at",
    "requested_by_agent_id", "run_id", "task_id", "tool_call_id",
  ], "approval_decision_public_approval");
  assert.equal("reason" in (firstBody.approval as Row), false);
  assert.equal((firstBody.approval as Row).approver_user_id, APPROVER_A);
  assert.equal((firstBody.linked_state as Row).run_status, "running");
  assert.equal((firstBody.linked_state as Row).task_status, "running");
  assert.equal((await row(client, "runs", "run_id", runId)).approval_required, 0);
  assert.equal((await row(client, "tasks", "task_id", taskId)).status, "running");

  const auditCount = await count(client, "audit_logs");
  const runtimeCount = await count(client, "runtime_events");
  const replay = await callAsApprover(approvalId, "approve", key);
  assert.equal(replay.status, 200);
  const replayBody = await json(replay);
  assert.equal(replayBody.outcome, "unchanged");
  assert.equal(await count(client, "audit_logs"), auditCount);
  assert.equal(await count(client, "runtime_events"), runtimeCount);
  assert.equal(await count(client, "human_approval_decision_requests"), 1);

  await expectError(
    await callAsApprover(approvalId, "reject", "approval-ordinary-reverse-0001"),
    409,
    "approval_decision_conflict",
  );
  await expectTransactionalFailure(client, "23514", "terminal_approval_cannot_return_pending", async () => {
    await client.query(
      "UPDATE approvals SET decision='pending',approver_user_id=NULL,decided_at=NULL WHERE approval_id=$1",
      [approvalId],
    );
  }, "approval_terminal_immutable");
  await expectTransactionalFailure(client, "23514", "terminal_approval_cannot_be_deleted", async () => {
    await client.query("DELETE FROM approvals WHERE approval_id=$1", [approvalId]);
  }, "approval_append_only");
  return key;
}

async function verifyRejected(client: Client, approvalId: string, runId: string, taskId: string, toolId: string) {
  const response = await callAsApprover(approvalId, "reject", "approval-rejected-0001");
  assert.equal(response.status, 200);
  const body = await json(response);
  assert.equal(body.decision, "rejected");
  assert.equal((body.linked_state as Row).tool_call_status, "blocked");
  assert.equal((await row(client, "runs", "run_id", runId)).status, "blocked");
  assert.equal((await row(client, "tasks", "task_id", taskId)).status, "blocked");
  assert.equal((await row(client, "tool_calls", "tool_call_id", toolId)).status, "blocked");
}

async function verifyPrepared(client: Client, approvalId: string, runId: string, taskId: string, toolId: string) {
  const response = await callAsApprover(approvalId, "approve", "approval-prepared-0001");
  assert.equal(response.status, 200);
  const body = await json(response);
  assert.equal((body.linked_state as Row).prepared_action_status, "approved");
  assert.equal((body.linked_state as Row).tool_call_status, "planned");
  assert.equal((await row(client, "runs", "run_id", runId)).status, "waiting_approval");
  assert.equal((await row(client, "runs", "run_id", runId)).approval_required, 0);
  assert.equal((await row(client, "tasks", "task_id", taskId)).status, "waiting_approval");
  assert.equal((await row(client, "tool_calls", "tool_call_id", toolId)).status, "planned");
  assert.equal((await row(client, "prepared_actions", "prepared_action_id", "pa_prepared")).status, "approved");
  assert.equal((await row(client, "approvals", "approval_id", approvalId)).approver_user_id, APPROVER_A);
}

async function verifyPreparedRejected(
  client: Client,
  approvalId: string,
  runId: string,
  taskId: string,
  toolId: string,
) {
  const response = await callAsApprover(approvalId, "reject", "approval-prepared-rejected-0001");
  assert.equal(response.status, 200);
  const body = await json(response);
  assert.equal(body.decision, "rejected");
  assert.equal((body.linked_state as Row).prepared_action_status, "rejected");
  assert.equal((body.linked_state as Row).tool_call_status, "blocked");
  assert.equal((await row(client, "prepared_actions", "prepared_action_id", "pa_prepared_rejected")).status, "rejected");
  assert.equal((await row(client, "tool_calls", "tool_call_id", toolId)).status, "blocked");
  assert.equal((await row(client, "runs", "run_id", runId)).status, "blocked");
  assert.equal((await row(client, "tasks", "task_id", taskId)).status, "blocked");
  assert.equal((await row(client, "approvals", "approval_id", approvalId)).approver_user_id, APPROVER_A);
}

async function verifyEnrollment(
  client: Client,
  approved: { approvalId: string; runId: string; taskId: string },
  rejected: { approvalId: string; runId: string; taskId: string },
) {
  const before = {
    tokens: await count(client, "agent_gateway_tokens"),
    artifacts: await count(client, "artifacts"),
    evaluations: await count(client, "evaluations"),
  };
  const response = await callAsApprover(approved.approvalId, "approve", "approval-enrollment-0001");
  assert.equal(response.status, 200);
  const body = await json(response);
  assert.equal((body.linked_state as Row).enrollment_status, "approved");
  const approvedEnrollment = await row(client, "agent_gateway_enrollment_requests", "request_id", "enr_approval");
  assert.equal(approvedEnrollment.status, "approved");
  assert.equal(approvedEnrollment.token_id, null);
  assert.equal((await row(client, "runs", "run_id", approved.runId)).status, "completed");
  assert.equal((await row(client, "tasks", "task_id", approved.taskId)).status, "completed");
  assert.equal((await row(client, "approvals", "approval_id", approved.approvalId)).approver_user_id, APPROVER_A);

  const rejection = await callAsApprover(rejected.approvalId, "reject", "approval-enrollment-rejected-0001");
  assert.equal(rejection.status, 200);
  const rejectionBody = await json(rejection);
  assert.equal((rejectionBody.linked_state as Row).enrollment_status, "rejected");
  const rejectedEnrollment = await row(client, "agent_gateway_enrollment_requests", "request_id", "enr_rejected");
  assert.equal(rejectedEnrollment.status, "rejected");
  assert.equal(rejectedEnrollment.token_id, null);
  assert.equal((await row(client, "runs", "run_id", rejected.runId)).status, "blocked");
  assert.equal((await row(client, "tasks", "task_id", rejected.taskId)).status, "blocked");
  assert.equal((await row(client, "approvals", "approval_id", rejected.approvalId)).approver_user_id, APPROVER_A);
  assert.deepEqual({
    tokens: await count(client, "agent_gateway_tokens"),
    artifacts: await count(client, "artifacts"),
    evaluations: await count(client, "evaluations"),
  }, before);
}

async function verifyRejectedSiblingBlocksLaterApprovals(
  client: Client,
  prepared: {
    approvalId: string;
    rejectorApprovalId: string;
    runId: string;
    taskId: string;
    toolId: string | null;
  },
  enrollment: {
    approvalId: string;
    rejectorApprovalId: string;
    runId: string;
    taskId: string;
  },
) {
  const preparedRejection = await callAsApprover(
    prepared.rejectorApprovalId,
    "reject",
    "approval-sibling-prepared-rejector-0001",
  );
  assert.equal(preparedRejection.status, 200);
  assert.equal((await json(preparedRejection)).decision, "rejected");
  assert.equal((await row(client, "runs", "run_id", prepared.runId)).status, "blocked");
  await expectError(
    await callAsApprover(prepared.approvalId, "approve", "approval-sibling-prepared-target-0001"),
    409,
    "approval_parent_state_blocked",
  );
  assert.equal((await row(client, "approvals", "approval_id", prepared.approvalId)).decision, "pending");
  assert.equal((await row(client, "approvals", "approval_id", prepared.approvalId)).approver_user_id, null);
  assert.equal((await row(client, "prepared_actions", "prepared_action_id", "pa_sibling_prepared")).status, "waiting_approval");
  assert.equal((await row(client, "tool_calls", "tool_call_id", String(prepared.toolId))).status, "waiting_approval");

  const enrollmentRejection = await callAsApprover(
    enrollment.rejectorApprovalId,
    "reject",
    "approval-sibling-enrollment-rejector-0001",
  );
  assert.equal(enrollmentRejection.status, 200);
  assert.equal((await json(enrollmentRejection)).decision, "rejected");
  assert.equal((await row(client, "runs", "run_id", enrollment.runId)).status, "blocked");
  await expectError(
    await callAsApprover(enrollment.approvalId, "approve", "approval-sibling-enrollment-target-0001"),
    409,
    "approval_parent_state_blocked",
  );
  assert.equal((await row(client, "approvals", "approval_id", enrollment.approvalId)).decision, "pending");
  assert.equal((await row(client, "approvals", "approval_id", enrollment.approvalId)).approver_user_id, null);
  assert.equal((await row(client, "agent_gateway_enrollment_requests", "request_id", "enr_sibling")).status, "pending");
}

async function verifyDeliveryRejectionPreservesExecution(
  client: Client,
  delivery: {
    approvalId: string;
    runId: string;
    taskId: string;
    evidence: { runtimeEventId: string; evaluationId: string; artifactId: string };
  },
) {
  const runBefore = await row(client, "runs", "run_id", delivery.runId);
  const runtimeEvidenceBefore = await row(
    client,
    "runtime_events",
    "runtime_event_id",
    delivery.evidence.runtimeEventId,
  );
  const evaluationEvidenceBefore = await row(
    client,
    "evaluations",
    "evaluation_id",
    delivery.evidence.evaluationId,
  );
  const artifactEvidenceBefore = await row(client, "artifacts", "artifact_id", delivery.evidence.artifactId);
  assert.equal(runBefore.status, "completed");

  const response = await callAsApprover(
    delivery.approvalId,
    "reject",
    "approval-delivery-rejected-0001",
  );
  assert.equal(response.status, 200);
  assertPrivateHeaders(response);
  const body = await json(response);
  assert.equal(body.decision, "rejected");
  assert.equal((body.approval as Row).approval_kind, "customer_delivery");
  assert.equal((body.linked_state as Row).run_status, "completed");

  const runAfter = await row(client, "runs", "run_id", delivery.runId);
  for (const field of [
    "status",
    "ended_at",
    "duration_ms",
    "output_summary",
    "error_type",
    "error_message",
    "cost_usd",
  ]) {
    assert.deepEqual(runAfter[field], runBefore[field], `delivery_rejection_changed_run_${field}`);
  }
  assert.equal(runAfter.approval_required, 0);
  assert.equal((await row(client, "tasks", "task_id", delivery.taskId)).status, "blocked");
  assert.deepEqual(
    await row(client, "runtime_events", "runtime_event_id", delivery.evidence.runtimeEventId),
    runtimeEvidenceBefore,
  );
  assert.deepEqual(
    await row(client, "evaluations", "evaluation_id", delivery.evidence.evaluationId),
    evaluationEvidenceBefore,
  );
  assert.deepEqual(await row(client, "artifacts", "artifact_id", delivery.evidence.artifactId), artifactEvidenceBefore);
  const rejectionAudit = await client.query<{ count: number }>(
    "SELECT COUNT(*)::int AS count FROM audit_logs WHERE action='approval.rejected' AND entity_id=$1",
    [delivery.approvalId],
  );
  assert.equal(rejectionAudit.rows[0]?.count, 1);
  const rejectionEvent = await client.query<{ count: number }>(
    "SELECT COUNT(*)::int AS count FROM runtime_events WHERE event_type='approval.rejected' AND run_id=$1",
    [delivery.runId],
  );
  assert.equal(rejectionEvent.rows[0]?.count, 1);
}

async function verifyIncompleteDeliveryRejectionBlocked(
  client: Client,
  delivery: { approvalId: string; runId: string; taskId: string },
) {
  const approvalBefore = await row(client, "approvals", "approval_id", delivery.approvalId);
  const runBefore = await row(client, "runs", "run_id", delivery.runId);
  const taskBefore = await row(client, "tasks", "task_id", delivery.taskId);
  await expectError(
    await callAsApprover(
      delivery.approvalId,
      "reject",
      "approval-delivery-incomplete-rejected-0001",
    ),
    409,
    "customer_delivery_run_incomplete",
  );
  assert.deepEqual(await row(client, "approvals", "approval_id", delivery.approvalId), approvalBefore);
  assert.deepEqual(await row(client, "runs", "run_id", delivery.runId), runBefore);
  assert.deepEqual(await row(client, "tasks", "task_id", delivery.taskId), taskBefore);
}

async function verifyBlockedApprovals(client: Client, ids: {
  expired: string;
  high: string;
  delivery: string;
}) {
  await expectError(
    await callAsApprover(ids.expired, "approve", "approval-expired-0001"),
    409,
    "approval_expired",
  );
  await expectError(
    await callAsApprover(ids.high, "approve", "approval-high-unprepared-0001"),
    409,
    "prepared_action_required",
  );
  await expectError(
    await callAsApprover(ids.delivery, "approve", "approval-delivery-missing-0001"),
    409,
    "verified_plan_evidence_manifest_required",
  );
  for (const approvalId of Object.values(ids)) {
    const approval = await row(client, "approvals", "approval_id", approvalId);
    assert.equal(approval.decision, "pending");
    assert.equal(approval.approver_user_id, null);
  }
}

async function verifyTerminalOrdinaryDecisionBlocked(
  client: Client,
  terminal: { approvalId: string; runId: string; taskId: string },
) {
  const runBefore = await row(client, "runs", "run_id", terminal.runId);
  const taskBefore = await row(client, "tasks", "task_id", terminal.taskId);
  await expectError(
    await callAsApprover(terminal.approvalId, "reject", "approval-terminal-reject-0001"),
    409,
    "approval_parent_state_blocked",
  );
  assert.deepEqual(await row(client, "runs", "run_id", terminal.runId), runBefore);
  assert.deepEqual(await row(client, "tasks", "task_id", terminal.taskId), taskBefore);
  const approval = await row(client, "approvals", "approval_id", terminal.approvalId);
  assert.equal(approval.decision, "pending");
  assert.equal(approval.approver_user_id, null);
}

async function verifyApprovalKindClassification(
  client: Client,
  kindBoundDeliveryId: string,
  decoy: { approvalId: string; runId: string; taskId: string },
) {
  const kindBound = await row(client, "approvals", "approval_id", kindBoundDeliveryId);
  assert.equal(kindBound.approval_kind, "customer_delivery");
  assert.equal(String(kindBound.approval_id).includes("customer_worker_delivery"), false);
  assert.equal(String(kindBound.reason).toLowerCase().includes("customer delivery"), false);
  assert.equal(kindBound.decision, "pending");

  const heuristicDecoy = await row(client, "approvals", "approval_id", decoy.approvalId);
  assert.equal(heuristicDecoy.approval_kind, "run_execution");
  assert.equal(String(heuristicDecoy.approval_id).includes("customer_worker_delivery"), true);
  assert.equal(String(heuristicDecoy.reason).toLowerCase().includes("customer delivery"), true);
  const response = await callAsApprover(
    decoy.approvalId,
    "approve",
    "approval-kind-heuristic-decoy-0001",
  );
  assert.equal(response.status, 200);
  assertPrivateHeaders(response);
  const body = await json(response);
  assert.equal(body.decision, "approved");
  assert.equal((body.approval as Row).approval_kind, "run_execution");
  assert.equal((body.linked_state as Row).run_status, "running");
  assert.equal((await row(client, "runs", "run_id", decoy.runId)).status, "running");
  assert.equal((await row(client, "tasks", "task_id", decoy.taskId)).status, "running");
}

async function verifyAuthorizationAndIsolation(foreignApprovalId: string) {
  const base = {
    decision: "approve",
    workspaceId: WORKSPACE_A,
    idempotencyKey: "approval-authz-contract-0001",
  };
  await expectError(
    await callDecision({ ...base, approvalId: "ap_missing", token: TOKEN_A, csrfToken: csrf(TOKEN_A) }),
    404,
    "approval_not_found",
  );
  const foreign = await callDecision({ ...base, approvalId: foreignApprovalId, token: TOKEN_A, csrfToken: csrf(TOKEN_A) });
  const missing = await callDecision({ ...base, approvalId: "ap_missing", token: TOKEN_A, csrfToken: csrf(TOKEN_A) });
  assert.deepEqual(await expectError(foreign, 404, "approval_not_found"), await expectError(missing, 404, "approval_not_found"));
  await expectError(
    await callDecision({ ...base, approvalId: "ap_rejected", csrfToken: csrf(TOKEN_A) }),
    401,
    "human_auth_required",
  );
  await expectError(
    await callDecision({
      ...base,
      approvalId: "ap_rejected",
      token: TOKEN_VIEWER,
      csrfToken: csrf(TOKEN_VIEWER),
      idempotencyKey: "approval-viewer-contract-0001",
    }),
    403,
    "human_role_forbidden",
  );
  await expectError(
    await callDecision({
      ...base,
      approvalId: "ap_rejected",
      token: TOKEN_OPERATOR,
      csrfToken: csrf(TOKEN_OPERATOR),
      idempotencyKey: "approval-operator-contract-0001",
    }),
    403,
    "human_role_forbidden",
  );
  await expectError(
    await callDecision({ ...base, approvalId: "ap_rejected", token: TOKEN_A, csrfToken: "0".repeat(64) }),
    403,
    "csrf_validation_failed",
  );
  await expectError(
    await callDecision({
      ...base,
      approvalId: "ap_rejected",
      token: TOKEN_A,
      csrfToken: csrf(TOKEN_A),
      origin: "http://127.0.0.1:3002",
    }),
    403,
    "origin_validation_failed",
  );
  await expectError(
    await callDecision({
      ...base,
      approvalId: "ap_rejected",
      token: TOKEN_A,
      csrfToken: csrf(TOKEN_A),
      host: "127.0.0.1:3002",
      idempotencyKey: "approval-host-contract-0001",
    }),
    403,
    "origin_validation_failed",
  );
  await expectError(
    await callDecision({
      ...base,
      approvalId: "ap_rejected",
      token: TOKEN_A,
      csrfToken: csrf(TOKEN_A),
      machineCredential: true,
    }),
    401,
    "machine_credential_not_allowed",
  );
  await expectError(
    await callDecision({
      approvalId: "invalid approval id",
      decision: "approve",
      token: TOKEN_A,
      workspaceId: WORKSPACE_A,
      csrfToken: csrf(TOKEN_A),
      idempotencyKey: "approval-invalid-id-0001",
    }),
    400,
    "approval_id_invalid",
  );
  await expectError(
    await callDecision({
      approvalId: "ap_rejected",
      decision: "approve",
      token: TOKEN_A,
      workspaceId: WORKSPACE_A,
      csrfToken: csrf(TOKEN_A),
    }),
    400,
    "idempotency_key_required",
  );
  await expectError(
    await callDecision({
      approvalId: "ap_rejected",
      decision: "approved",
      token: TOKEN_A,
      workspaceId: WORKSPACE_A,
      csrfToken: csrf(TOKEN_A),
      idempotencyKey: "approval-invalid-decision-0001",
    }),
    404,
    "approval_decision_not_found",
  );
}

async function verifyConcurrency(client: Client, approvalId: string) {
  const key = "approval-race-contract-0001";
  const responses = await Promise.all(
    Array.from({ length: 16 }, () => callAsApprover(approvalId, "approve", key)),
  );
  const outcomes: unknown[] = [];
  for (const response of responses) {
    assert.equal(response.status, 200);
    assertPrivateHeaders(response);
    outcomes.push((await json(response)).outcome);
  }
  assert.equal(outcomes.filter((outcome) => outcome === "updated").length, 1);
  assert.equal(outcomes.filter((outcome) => outcome === "unchanged").length, 15);
  const requests = await client.query<{ count: number }>(
    "SELECT COUNT(*)::int AS count FROM human_approval_decision_requests WHERE approval_id=$1",
    [approvalId],
  );
  assert.equal(requests.rows[0]?.count, 1);
  const audits = await client.query<{ count: number }>(
    "SELECT COUNT(*)::int AS count FROM audit_logs WHERE action='approval.approved' AND entity_id=$1",
    [approvalId],
  );
  assert.equal(audits.rows[0]?.count, 1);
  const events = await client.query<{ count: number }>(
    `SELECT COUNT(*)::int AS count FROM runtime_events
    WHERE event_type='approval.approved' AND run_id=(SELECT run_id FROM approvals WHERE approval_id=$1)`,
    [approvalId],
  );
  assert.equal(events.rows[0]?.count, 1);
}

async function verifyDecisionCollision(client: Client, approvalId: string) {
  const responses = await Promise.all(Array.from({ length: 16 }, (_, index) => callAsApprover(
    approvalId,
    index % 2 === 0 ? "approve" : "reject",
    `approval-collision-${String(index).padStart(2, "0")}-0001`,
  )));
  const winners = responses.filter((response) => response.status === 200);
  const conflicts = responses.filter((response) => response.status === 409);
  assert.equal(winners.length, 1);
  assert.equal(conflicts.length, 15);
  const winner = await json(winners[0]);
  assert.ok(["approved", "rejected"].includes(String(winner.decision)));
  for (const response of conflicts) {
    await expectError(response, 409, "approval_decision_conflict");
  }
  const approval = await row(client, "approvals", "approval_id", approvalId);
  assert.equal(approval.approver_user_id, APPROVER_A);
  assert.ok(["approved", "rejected"].includes(String(approval.decision)));
  const requests = await client.query<{ count: number }>(
    "SELECT COUNT(*)::int AS count FROM human_approval_decision_requests WHERE approval_id=$1",
    [approvalId],
  );
  assert.equal(requests.rows[0]?.count, 1);
  const audits = await client.query<{ count: number }>(
    `SELECT COUNT(*)::int AS count FROM audit_logs
    WHERE entity_id=$1 AND action IN ('approval.approved','approval.rejected')`,
    [approvalId],
  );
  assert.equal(audits.rows[0]?.count, 1);
  const events = await client.query<{ count: number }>(
    `SELECT COUNT(*)::int AS count FROM runtime_events
    WHERE run_id=(SELECT run_id FROM approvals WHERE approval_id=$1)
      AND event_type IN ('approval.approved','approval.rejected')`,
    [approvalId],
  );
  assert.equal(events.rows[0]?.count, 1);
}

type LockOrderProbe = {
  approvalId: string;
  taskId: string;
  runId: string;
  toolId: string | null;
};

type DecisionProbeOutcome = {
  response: Response | null;
  errorCode: string | null;
};

async function waitForControlPlaneBlockedBy(
  client: Client,
  blockerPid: number,
  relationName: "tasks" | "tool_calls",
  stage: string,
) {
  const deadline = Date.now() + 5_000;
  while (Date.now() < deadline) {
    const result = await client.query<{ pid: number }>(
      `SELECT activity.pid
      FROM pg_stat_activity activity
      WHERE activity.datname=current_database()
        AND activity.pid<>pg_backend_pid()
        AND activity.application_name='agentops-mis-typescript-control-plane'
        AND $1::int=ANY(pg_blocking_pids(activity.pid))
        AND activity.wait_event_type='Lock'
        AND activity.query ILIKE $2
        AND activity.query ILIKE '%FOR UPDATE%'
      ORDER BY activity.pid
      LIMIT 1`,
      [blockerPid, `%FROM ${relationName}%`],
    );
    if (result.rows[0]) return result.rows[0].pid;
    await new Promise<void>((resolve) => setTimeout(resolve, 20));
  }
  throw new Error(`${stage}:control_plane_${relationName}_lock_wait_not_observed`);
}

async function settleWithin<T>(promise: Promise<T>, timeoutMs: number, timeoutCode: string) {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_, reject) => {
        timeout = setTimeout(() => reject(new Error(timeoutCode)), timeoutMs);
      }),
    ]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

function startDecisionProbe(approvalId: string, idempotencyKey: string): Promise<DecisionProbeOutcome> {
  return callAsApprover(approvalId, "approve", idempotencyKey).then(
    (response) => ({ response, errorCode: null }),
    (error: unknown) => ({
      response: null,
      errorCode: String((error as { code?: string })?.code || "typescript_approval_writer_failed"),
    }),
  );
}

function assertNoLockFailure(errorCode: string | null, stage: string) {
  if (!errorCode) return;
  const failure = errorCode === "40P01"
    ? "deadlock_detected"
    : errorCode === "55P03"
      ? "lock_not_available_or_lock_timeout"
      : errorCode === "57014"
        ? "statement_or_lock_wait_timeout"
        : "unexpected_lock_writer_failure";
  assert.fail(`${stage}:${failure}:${errorCode}`);
}

async function assertDecisionProbeSucceeded(
  decisionPromise: Promise<DecisionProbeOutcome>,
  stage: string,
) {
  const outcome = await settleWithin(decisionPromise, 8_000, `${stage}:route_lock_timeout`);
  assert.equal(outcome.errorCode, null, `${stage}:route_rejected:${outcome.errorCode}`);
  assert.ok(outcome.response, `${stage}:route_response_missing`);
  assertPrivateHeaders(outcome.response);
  const body = await json(outcome.response);
  assert.notEqual(
    outcome.response.status,
    503,
    `${stage}:forbidden_503:${String(body.error || "typescript_control_plane_unavailable")}`,
  );
  assert.equal(
    outcome.response.status,
    200,
    `${stage}:unexpected_status:${outcome.response.status}:${String(body.error || "unknown")}`,
  );
  assert.equal(body.decision, "approved");
}

async function verifyParentFirstLockProbe(
  observer: Client,
  dsn: string,
  approval: LockOrderProbe,
  stage: string,
  idempotencyKey: string,
) {
  const writer = new Client({
    connectionString: dsn,
    ssl: sslEnabled() ? { rejectUnauthorized: true } : undefined,
    application_name: `agentops-contract-${stage}`,
  });
  let transactionOpen = false;
  let writerErrorCode: string | null = null;
  let decisionPromise: Promise<DecisionProbeOutcome> | null = null;
  try {
    await writer.connect();
    await writer.query("BEGIN");
    transactionOpen = true;
    await writer.query("SET LOCAL lock_timeout='5s'");
    await writer.query("SET LOCAL statement_timeout='8s'");
    const blocker = await writer.query<{ pid: number }>("SELECT pg_backend_pid()::int AS pid");
    const blockerPid = blocker.rows[0]?.pid;
    assert.ok(blockerPid, `${stage}:writer_backend_pid_missing`);

    await writer.query("SELECT task_id FROM tasks WHERE task_id=$1 FOR UPDATE", [approval.taskId]);
    decisionPromise = startDecisionProbe(approval.approvalId, idempotencyKey);
    const blockedPid = await waitForControlPlaneBlockedBy(observer, blockerPid, "tasks", stage);
    assert.notEqual(blockedPid, blockerPid, `${stage}:control_plane_pid_mismatch`);

    try {
      await writer.query("SELECT run_id FROM runs WHERE run_id=$1 FOR UPDATE", [approval.runId]);
      if (approval.toolId) {
        await writer.query(
          "SELECT tool_call_id FROM tool_calls WHERE tool_call_id=$1 FOR UPDATE",
          [approval.toolId],
        );
      }
      await writer.query(
        "SELECT approval_id FROM approvals WHERE approval_id=$1 FOR UPDATE",
        [approval.approvalId],
      );
      await writer.query("COMMIT");
      transactionOpen = false;
    } catch (error) {
      writerErrorCode = String((error as { code?: string })?.code || "parent_first_writer_failed");
      await writer.query("ROLLBACK").catch(() => undefined);
      transactionOpen = false;
    }

    await assertDecisionProbeSucceeded(decisionPromise, stage);
    assertNoLockFailure(writerErrorCode, stage);
    assert.equal((await row(observer, "approvals", "approval_id", approval.approvalId)).decision, "approved");
  } finally {
    if (transactionOpen) await writer.query("ROLLBACK").catch(() => undefined);
    await writer.end().catch(() => undefined);
    if (decisionPromise) {
      await settleWithin(decisionPromise, 8_000, `${stage}:cleanup_timeout`).catch(() => undefined);
    }
  }
}

async function verifyPythonWriterLockOrderCompatibility(
  observer: Client,
  dsn: string,
  runOnly: LockOrderProbe,
  toolBound: LockOrderProbe,
) {
  currentStage = "parent_first_run_only_lock_order";
  await verifyParentFirstLockProbe(
    observer,
    dsn,
    runOnly,
    currentStage,
    "approval-parent-first-run-only-0001",
  );
  currentStage = "parent_first_tool_bound_lock_order";
  await verifyParentFirstLockProbe(
    observer,
    dsn,
    toolBound,
    currentStage,
    "approval-parent-first-tool-bound-0001",
  );
}

async function verifyToolBeforeApprovalLockOrder(
  observer: Client,
  dsn: string,
  approval: LockOrderProbe,
) {
  const stage = "tool_before_approval_lock_order";
  currentStage = stage;
  assert.ok(approval.toolId, `${stage}:tool_binding_missing`);
  const toolBlocker = new Client({
    connectionString: dsn,
    ssl: sslEnabled() ? { rejectUnauthorized: true } : undefined,
    application_name: "agentops-contract-tool-order-blocker",
  });
  const approvalObserver = new Client({
    connectionString: dsn,
    ssl: sslEnabled() ? { rejectUnauthorized: true } : undefined,
    application_name: "agentops-contract-tool-order-observer",
  });
  let toolTransactionOpen = false;
  let approvalTransactionOpen = false;
  let approvalLockErrorCode: string | null = null;
  let decisionPromise: Promise<DecisionProbeOutcome> | null = null;
  try {
    await Promise.all([toolBlocker.connect(), approvalObserver.connect()]);
    await toolBlocker.query("BEGIN");
    toolTransactionOpen = true;
    await toolBlocker.query("SET LOCAL lock_timeout='5s'");
    await toolBlocker.query("SET LOCAL statement_timeout='8s'");
    const blocker = await toolBlocker.query<{ pid: number }>("SELECT pg_backend_pid()::int AS pid");
    const blockerPid = blocker.rows[0]?.pid;
    assert.ok(blockerPid, `${stage}:tool_blocker_backend_pid_missing`);
    await toolBlocker.query(
      "SELECT tool_call_id FROM tool_calls WHERE tool_call_id=$1 FOR UPDATE",
      [approval.toolId],
    );
    decisionPromise = startDecisionProbe(
      approval.approvalId,
      "approval-tool-before-approval-0001",
    );
    const blockedPid = await waitForControlPlaneBlockedBy(observer, blockerPid, "tool_calls", stage);
    assert.notEqual(blockedPid, blockerPid, `${stage}:control_plane_pid_mismatch`);

    await approvalObserver.query("BEGIN");
    approvalTransactionOpen = true;
    await approvalObserver.query("SET LOCAL statement_timeout='5s'");
    try {
      await approvalObserver.query(
        "SELECT approval_id FROM approvals WHERE approval_id=$1 FOR UPDATE NOWAIT",
        [approval.approvalId],
      );
      await approvalObserver.query("COMMIT");
      approvalTransactionOpen = false;
    } catch (error) {
      approvalLockErrorCode = String((error as { code?: string })?.code || "approval_observer_lock_failed");
      await approvalObserver.query("ROLLBACK").catch(() => undefined);
      approvalTransactionOpen = false;
    }

    await toolBlocker.query("COMMIT");
    toolTransactionOpen = false;
    await assertDecisionProbeSucceeded(decisionPromise, stage);
    assertNoLockFailure(approvalLockErrorCode, stage);
    assert.equal((await row(observer, "approvals", "approval_id", approval.approvalId)).decision, "approved");
  } finally {
    if (approvalTransactionOpen) await approvalObserver.query("ROLLBACK").catch(() => undefined);
    if (toolTransactionOpen) await toolBlocker.query("ROLLBACK").catch(() => undefined);
    await Promise.all([
      approvalObserver.end().catch(() => undefined),
      toolBlocker.end().catch(() => undefined),
    ]);
    if (decisionPromise) {
      await settleWithin(decisionPromise, 8_000, `${stage}:cleanup_timeout`).catch(() => undefined);
    }
  }
}

async function verifyVerifiedDelivery(
  client: Client,
  approvalId: string,
  runId: string,
  taskId: string,
  rebindRunId: string,
  contractDsn: string,
) {
  const key = "approval-delivery-verified-0001";
  const requestCountBefore = await count(client, "human_approval_decision_requests");
  await expectError(
    await callAsApprover(approvalId, "approve", key),
    409,
    "customer_delivery_run_incomplete",
  );
  assert.equal((await row(client, "approvals", "approval_id", approvalId)).decision, "pending");
  assert.equal(await count(client, "human_approval_decision_requests"), requestCountBefore);
  await client.query(
    "UPDATE runs SET status='completed',ended_at=$1 WHERE run_id=$2 AND status='waiting_approval'",
    [new Date().toISOString(), runId],
  );
  await client.query(
    "UPDATE evaluations SET evaluator_type='llm_mock' WHERE evaluation_id='eval_delivery_verified'",
  );
  await expectError(
    await callAsApprover(approvalId, "approve", key),
    409,
    "verified_plan_evidence_manifest_required",
  );
  assert.equal((await row(client, "approvals", "approval_id", approvalId)).decision, "pending");
  assert.equal(await count(client, "human_approval_decision_requests"), requestCountBefore);
  await client.query(
    "UPDATE evaluations SET evaluator_type='rule' WHERE evaluation_id='eval_delivery_verified'",
  );
  const evidenceWriter = new Client({
    connectionString: contractDsn,
    application_name: "agentops-mis-approved-evidence-race-contract",
  });
  await evidenceWriter.connect();
  let evidenceTransactionOpen = false;
  let decisionSettled = false;
  let decisionPromise: Promise<Response> | null = null;
  let response: Response | null = null;
  try {
    await evidenceWriter.query("BEGIN");
    evidenceTransactionOpen = true;
    await evidenceWriter.query(
      `UPDATE tool_calls SET result_summary='Pre-decision evidence transaction.'
      WHERE tool_call_id='tool_delivery_verified'`,
    );
    decisionPromise = callAsApprover(approvalId, "approve", key).finally(() => {
      decisionSettled = true;
    });
    await new Promise<void>((resolve) => setTimeout(resolve, 200));
    assert.equal(decisionSettled, false, "approval_must_wait_for_inflight_evidence_transaction");
    await evidenceWriter.query("COMMIT");
    evidenceTransactionOpen = false;
    response = await settleWithin(
      decisionPromise,
      8_000,
      "approval_after_evidence_commit_timeout",
    );
  } finally {
    if (evidenceTransactionOpen) await evidenceWriter.query("ROLLBACK").catch(() => undefined);
    await evidenceWriter.end().catch(() => undefined);
    if (decisionPromise) {
      await settleWithin(decisionPromise, 8_000, "approval_evidence_race_cleanup_timeout").catch(() => undefined);
    }
  }
  if (!response) throw new Error("approval_after_evidence_commit_missing_response");
  const body = await json(response);
  assert.equal(response.status, 200, String(body.error || "verified_delivery_approval_failed"));
  assertPrivateHeaders(response);
  assert.equal(body.decision, "approved");
  assert.equal("delivery_approval_gate" in body, false);
  assert.equal((await row(client, "approvals", "approval_id", approvalId)).approver_user_id, APPROVER_A);
  assert.equal((await row(client, "tasks", "task_id", taskId)).status, "completed");
  assert.equal((await row(client, "runs", "run_id", runId)).approval_required, 0);
  const sealedOperations: Array<[string, () => Promise<void>]> = [
    ["tool_update", async () => {
      await client.query(
        "UPDATE tool_calls SET normalized_args_json='{\"tampered\":true}' WHERE tool_call_id='tool_delivery_verified'",
      );
    }],
    ["tool_insert", async () => {
      await client.query(
        `INSERT INTO tool_calls(
          tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,
          risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at
        ) SELECT 'tool_delivery_sealed_insert',run_id,agent_id,tool_name,tool_version,tool_category,
          normalized_args_json,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at
        FROM tool_calls WHERE tool_call_id='tool_delivery_verified'`,
      );
    }],
    ["tool_delete", async () => {
      await client.query("DELETE FROM tool_calls WHERE tool_call_id='tool_delivery_verified'");
    }],
    ["evaluation_update", async () => {
      await client.query(
        "UPDATE evaluations SET notes='tampered' WHERE evaluation_id='eval_delivery_verified'",
      );
    }],
    ["evaluation_insert", async () => {
      await client.query(
        `INSERT INTO evaluations(
          evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at
        ) SELECT 'eval_delivery_sealed_insert',task_id,run_id,agent_id,evaluator_type,score,
          pass_fail,rubric_json,notes,created_at
        FROM evaluations WHERE evaluation_id='eval_delivery_verified'`,
      );
    }],
    ["evaluation_delete", async () => {
      await client.query("DELETE FROM evaluations WHERE evaluation_id='eval_delivery_verified'");
    }],
    ["artifact_update", async () => {
      await client.query(
        "UPDATE artifacts SET title='tampered' WHERE artifact_id='art_delivery_verified'",
      );
    }],
    ["artifact_insert", async () => {
      await client.query(
        `INSERT INTO artifacts(
          artifact_id,task_id,run_id,artifact_type,title,uri,summary,created_at
        ) SELECT 'art_delivery_sealed_insert',task_id,run_id,artifact_type,title,uri,summary,created_at
        FROM artifacts WHERE artifact_id='art_delivery_verified'`,
      );
    }],
    ["artifact_delete", async () => {
      await client.query("DELETE FROM artifacts WHERE artifact_id='art_delivery_verified'");
    }],
    ["manifest_update", async () => {
      await client.query(
        "UPDATE plan_evidence_manifests SET verification_json='{}' WHERE manifest_id='manifest_delivery_verified'",
      );
    }],
    ["manifest_insert", async () => {
      await client.query(
        `INSERT INTO plan_evidence_manifests(
          manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,expected_steps_json,
          tool_call_ids_json,evaluation_ids_json,artifact_ids_json,audit_ids_json,status,verification_json,
          created_at,updated_at
        ) SELECT 'manifest_delivery_sealed_insert',workspace_id,plan_id,task_id,run_id,agent_id,
          mismatch_policy,expected_steps_json,tool_call_ids_json,evaluation_ids_json,artifact_ids_json,
          audit_ids_json,status,verification_json,created_at,updated_at
        FROM plan_evidence_manifests WHERE manifest_id='manifest_delivery_verified'`,
      );
    }],
    ["manifest_delete", async () => {
      await client.query(
        "DELETE FROM plan_evidence_manifests WHERE manifest_id='manifest_delivery_verified'",
      );
    }],
    ["plan_update", async () => {
      await client.query(
        "UPDATE agent_plans SET task_understanding='tampered' WHERE plan_id='plan_delivery_verified'",
      );
    }],
    ["plan_insert", async () => {
      await client.query(
        `INSERT INTO agent_plans(
          plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,referenced_specs_json,
          referenced_memories_json,referenced_bases_json,proposed_files_to_change_json,risk_level,
          approval_required,execution_steps_json,verification_plan,rollback_plan,status,created_at,updated_at
        ) SELECT 'plan_delivery_sealed_insert',workspace_id,task_id,run_id,agent_id,task_understanding,
          referenced_specs_json,referenced_memories_json,referenced_bases_json,proposed_files_to_change_json,
          risk_level,approval_required,execution_steps_json,verification_plan,rollback_plan,status,
          created_at,updated_at
        FROM agent_plans WHERE plan_id='plan_delivery_verified'`,
      );
    }],
    ["plan_delete", async () => {
      await client.query("DELETE FROM agent_plans WHERE plan_id='plan_delivery_verified'");
    }],
  ];
  for (const [label, operation] of sealedOperations) {
    await expectTransactionalFailure(
      client,
      "23514",
      `customer_delivery_${label}_must_be_sealed`,
      operation,
      "customer_delivery_evidence_sealed",
    );
  }
  await expectTransactionalFailure(
    client,
    "23514",
    "tool_parent_rebind_must_be_immutable",
    async () => {
      await client.query(
        "UPDATE tool_calls SET run_id=$1 WHERE tool_call_id='tool_delivery_verified'",
        [rebindRunId],
      );
    },
    "approval_parent_binding_immutable",
  );
  assert.equal(
    (await row(client, "tool_calls", "tool_call_id", "tool_delivery_verified")).run_id,
    runId,
  );
}

async function verifyFormFallback(client: Client, approvalId: string) {
  const form = new URLSearchParams({
    approval_id: approvalId,
    decision: "approve",
    workspace_id: WORKSPACE_A,
    csrf_token: csrf(TOKEN_A),
    idempotency_key: "approval-form-contract-0001",
  });
  const response = await reviewApprovalFormRoute(new Request(`${ORIGIN}/workspace/approvals/review`, {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      cookie: `agentops_human_session=${encodeURIComponent(TOKEN_A)}`,
      host: "127.0.0.1:3001",
      origin: ORIGIN,
    },
    body: form.toString(),
  }));
  assert.equal(response.status, 303);
  assertPrivateHeaders(response);
  assert.match(String(response.headers.get("location") || ""), /decision=approved/);
  assert.equal((await row(client, "approvals", "approval_id", approvalId)).decision, "approved");

  const invalid = await reviewApprovalFormRoute(new Request(`${ORIGIN}/workspace/approvals/review`, {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      cookie: `agentops_human_session=${encodeURIComponent(TOKEN_A)}`,
      host: "127.0.0.1:3001",
      origin: ORIGIN,
    },
    body: new URLSearchParams({ approval_id: approvalId, decision: "approved" }).toString(),
  }));
  assert.equal(invalid.status, 400);
  assertPrivateHeaders(invalid);
  assert.equal((await json(invalid)).error, "decision_invalid");
}

async function verifyProxyBoundaries(productionApprovalId: string) {
  const requests: Array<{ url: string; body: string }> = [];
  const server = http.createServer((request, response) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      requests.push({ url: String(request.url || ""), body });
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ decision: "approved", token_omitted: true }));
    });
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const priorBase = process.env.AGENTOPS_API_BASE;
  const priorMode = process.env.AGENTOPS_CONTROL_PLANE_MODE;
  const priorDeployment = process.env.AGENTOPS_DEPLOYMENT_MODE;
  process.env.AGENTOPS_API_BASE = `http://127.0.0.1:${address.port}/api`;
  try {
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    process.env.AGENTOPS_DEPLOYMENT_MODE = "free_local";
    const proxied = await callDecision({
      approvalId: "ap_free_local_proxy",
      decision: "approve",
      body: { workspace_id: "local-demo" },
    });
    assert.equal(proxied.status, 200);
    assertPrivateHeaders(proxied);
    assert.deepEqual(requests, [{
      url: "/api/approvals/ap_free_local_proxy/approve",
      body: JSON.stringify({ workspace_id: "local-demo" }),
    }]);

    requests.length = 0;
    process.env.AGENTOPS_DEPLOYMENT_MODE = "production";
    const direct = await callAsApprover(productionApprovalId, "approve", "approval-production-direct-0001");
    assert.equal(direct.status, 200);
    assert.deepEqual(requests, []);
    assert.equal((await json(direct)).control_plane, "typescript_postgres");
  } finally {
    if (priorBase === undefined) delete process.env.AGENTOPS_API_BASE;
    else process.env.AGENTOPS_API_BASE = priorBase;
    if (priorMode === undefined) delete process.env.AGENTOPS_CONTROL_PLANE_MODE;
    else process.env.AGENTOPS_CONTROL_PLANE_MODE = priorMode;
    if (priorDeployment === undefined) delete process.env.AGENTOPS_DEPLOYMENT_MODE;
    else process.env.AGENTOPS_DEPLOYMENT_MODE = priorDeployment;
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
}

async function closeControlPlanePool() {
  const state = globalThis as typeof globalThis & { __agentOpsControlPlanePool?: Pool };
  if (state.__agentOpsControlPlanePool) {
    await state.__agentOpsControlPlanePool.end();
    state.__agentOpsControlPlanePool = undefined;
  }
}

async function main() {
  const baseDsn = String(process.env.AGENTOPS_TEST_POSTGRES_DSN || process.env.AGENTOPS_POSTGRES_DSN || "").trim();
  if (!baseDsn) throw new Error("postgres_dsn_required");
  const schema = `agentops_approval_decision_${randomBytes(8).toString("hex")}`;
  const quotedSchema = `"${schema}"`;
  const contractDsn = scopedDsn(baseDsn, schema);
  const admin = new Client({
    connectionString: baseDsn,
    ssl: sslEnabled() ? { rejectUnauthorized: true } : undefined,
    application_name: "agentops-approval-decision-contract-setup",
  });
  let schemaCreated = false;
  process.env.AGENTOPS_POSTGRES_DSN = contractDsn;
  process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = HMAC_KEY;
  process.env.AGENTOPS_ALLOWED_ORIGINS = ORIGIN;
  process.env.AGENTOPS_CONTROL_PLANE_MODE = "postgres";
  process.env.AGENTOPS_DEPLOYMENT_MODE = "production";
  process.env.AGENTOPS_POSTGRES_POOL_MAX = "24";
  try {
    currentStage = "schema_setup";
    await admin.connect();
    await admin.query(`CREATE SCHEMA ${quotedSchema}`);
    schemaCreated = true;
    await admin.query(`SET search_path TO ${quotedSchema}`);
    await createBaseSchema(admin);
    currentStage = "real_migration_runner";
    await applyMigrations(contractDsn);
    currentStage = "seed";
    const cases = await seed(admin);

    currentStage = "approval_kind_database_bindings";
    await verifyApprovalKindDatabaseBindings(admin, cases);

    currentStage = "ordinary_and_replay";
    const ordinaryKey = await verifyOrdinaryAndIdempotency(
      admin,
      cases.ordinary.approvalId,
      cases.ordinary.runId,
      cases.ordinary.taskId,
    );
    await expectError(
      await callAsApprover(cases.rejected.approvalId, "reject", ordinaryKey),
      409,
      "approval_idempotency_conflict",
    );
    currentStage = "ordinary_reject";
    await verifyRejected(
      admin,
      cases.rejected.approvalId,
      cases.rejected.runId,
      cases.rejected.taskId,
      String(cases.rejected.toolId),
    );
    currentStage = "prepared_approve";
    await verifyPrepared(
      admin,
      cases.prepared.approvalId,
      cases.prepared.runId,
      cases.prepared.taskId,
      String(cases.prepared.toolId),
    );
    currentStage = "prepared_reject";
    await verifyPreparedRejected(
      admin,
      cases.preparedRejected.approvalId,
      cases.preparedRejected.runId,
      cases.preparedRejected.taskId,
      String(cases.preparedRejected.toolId),
    );
    currentStage = "enrollment_decisions";
    await verifyEnrollment(admin, cases.enrollment, cases.enrollmentRejected);
    currentStage = "rejected_sibling_blocks_later_work";
    await verifyRejectedSiblingBlocksLaterApprovals(
      admin,
      cases.siblingPrepared,
      cases.siblingEnrollment,
    );
    currentStage = "fail_closed_gates";
    await verifyBlockedApprovals(admin, {
      expired: cases.expired.approvalId,
      high: cases.high.approvalId,
      delivery: cases.delivery.approvalId,
    });
    currentStage = "terminal_ordinary_decision_blocked";
    await verifyTerminalOrdinaryDecisionBlocked(admin, cases.terminalOrdinary);
    currentStage = "approval_kind_classification";
    await verifyApprovalKindClassification(
      admin,
      cases.delivery.approvalId,
      cases.deliveryHeuristicDecoy,
    );
    currentStage = "delivery_rejection_preserves_execution";
    await verifyIncompleteDeliveryRejectionBlocked(admin, cases.deliveryIncompleteRejected);
    await verifyDeliveryRejectionPreservesExecution(admin, cases.deliveryRejected);
    currentStage = "verified_delivery";
    await verifyVerifiedDelivery(
      admin,
      cases.deliveryVerified.approvalId,
      cases.deliveryVerified.runId,
      cases.deliveryVerified.taskId,
      cases.ordinary.runId,
      contractDsn,
    );
    currentStage = "human_boundary";
    await verifyAuthorizationAndIsolation(cases.foreign.approvalId);
    currentStage = "same_key_concurrency_16";
    await verifyConcurrency(admin, cases.race.approvalId);
    currentStage = "decision_collision_16";
    await verifyDecisionCollision(admin, cases.collision.approvalId);
    currentStage = "parent_first_lock_order";
    await verifyPythonWriterLockOrderCompatibility(
      admin,
      contractDsn,
      cases.parentFirstRun,
      cases.parentFirstTool,
    );
    currentStage = "tool_before_approval_lock_order";
    await verifyToolBeforeApprovalLockOrder(admin, contractDsn, cases.toolBeforeApproval);
    currentStage = "form_fallback";
    await verifyFormFallback(admin, cases.form.approvalId);
    currentStage = "proxy_boundaries";
    await verifyProxyBoundaries(cases.production.approvalId);

    currentStage = "complete";
    const receipt = {
      ok: true,
      contract: "nextjs_postgres_human_approval_decision_v1",
      checks: {
        isolated_schema_real_migration_runner: true,
        human_session_reviewer_rbac_csrf_origin: true,
        viewer_and_operator_rejected: true,
        machine_credentials_rejected: true,
        workspace_isolation_and_hidden_404: true,
        strict_route_id_decision_and_idempotency_key: true,
        exact_replay_is_side_effect_free: true,
        idempotency_key_rebinding_rejected: true,
        concurrent_same_key_16_way_single_winner: true,
        concurrent_approve_reject_collision_single_winner: true,
        terminal_decision_immutable: true,
        rejection_blocks_linked_state: true,
        explicit_approval_kind_fixture_binding: true,
        prepared_action_approve_and_reject: true,
        enrollment_approve_and_reject_without_token_or_mock_evidence: true,
        rejected_sibling_blocks_later_prepared_action_and_enrollment: true,
        expired_and_unprepared_high_risk_approvals_blocked: true,
        customer_delivery_requires_verified_manifest: true,
        customer_delivery_requires_completed_run: true,
        customer_delivery_mock_evidence_rejected: true,
        customer_delivery_verified_manifest_accepted: true,
        sibling_run_artifact_excluded_from_delivery_manifest: true,
        customer_delivery_evidence_matrix_sealed: true,
        customer_delivery_evidence_decision_race_serialized: true,
        customer_delivery_rejection_preserves_completed_run_evidence: true,
        customer_delivery_rejection_requires_completed_run: true,
        customer_delivery_classification_uses_approval_kind_only: true,
        parent_first_lock_order_deadlock_free: true,
        tool_before_approval: true,
        browser_form_fallback_direct_postgres: true,
        free_local_python_path_preserved: true,
        production_python_proxy_blocked: true,
        response_projection_and_private_headers: true,
        approval_kind_explicit_immutable_and_edge_bound: true,
        approval_execution_binding_immutable: true,
        terminal_run_rejection_non_mutating: true,
        enrollment_approval_unique_binding: true,
      },
      credentials_omitted: true,
      raw_body_omitted: true,
      token_omitted: true,
    };
    assertNoSensitiveOutput(receipt);
    output(receipt);
  } finally {
    await closeControlPlanePool().catch(() => undefined);
    if (schemaCreated) {
      await admin.query("SET search_path TO public").catch(() => undefined);
      await admin.query(`DROP SCHEMA ${quotedSchema} CASCADE`).catch(() => undefined);
    }
    await admin.end().catch(() => undefined);
  }
}

main().catch((error: unknown) => {
  const candidate = error as { code?: string };
  const code = candidate?.code && /^[a-z0-9_]+$/i.test(candidate.code)
    ? candidate.code
    : "approval_decision_contract_failed";
  const diagnostic = safeFailureDiagnostic(error);
  const failure = {
    ok: false,
    error: code,
    stage: currentStage,
    assertion: diagnostic.assertion,
    location: diagnostic.location,
    credentials_omitted: true,
    raw_body_omitted: true,
    token_omitted: true,
  };
  assertNoSensitiveOutput(failure);
  output(failure);
  process.exitCode = 1;
});
