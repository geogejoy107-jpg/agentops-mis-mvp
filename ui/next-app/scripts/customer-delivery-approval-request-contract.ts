import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import http from "node:http";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { NextRequest } from "next/server";
import { Client, type Pool } from "pg";

import { POST as requestApprovalRoute } from "../app/api/mis/agent-gateway/approvals/request/route";
import { requestCustomerDeliveryApproval } from "../src/server/controlPlane/agentGatewayApprovals";
import { errorPayload } from "../src/server/controlPlane/http";

const WORKSPACE = "ws_delivery_request";
const OTHER_WORKSPACE = "ws_delivery_request_other";
const AGENT = "agt_delivery_request";
const OTHER_AGENT = "agt_delivery_request_other";
const TOKEN_A = randomBytes(32).toString("base64url");
const TOKEN_B = randomBytes(32).toString("base64url");
const TOKEN_NO_SCOPE = randomBytes(32).toString("base64url");
const TOKEN_OTHER = randomBytes(32).toString("base64url");
const SECRET_MARKER = `contract-secret-${randomBytes(12).toString("hex")}`;
const V4_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_approval_kind_bindings_v4.sql", import.meta.url),
);
const V5_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260724_customer_delivery_run_unique_v5.sql", import.meta.url),
);

type JsonObject = Record<string, unknown>;
type CapturedResponse = { status: number; body: JsonObject };

function tokenHash(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function sha256(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function scopedDsn(dsn: string, schema: string) {
  const url = new URL(dsn);
  url.searchParams.set("options", `-csearch_path=${schema}`);
  return url.toString();
}

function gatewayRequest(input: {
  token?: string;
  workspaceId?: string;
  agentId?: string;
  body: JsonObject;
}) {
  const headers = new Headers({ "content-type": "application/json" });
  if (input.token) headers.set("authorization", `Bearer ${input.token}`);
  if (input.workspaceId) headers.set("x-agentops-workspace-id", input.workspaceId);
  if (input.agentId) headers.set("x-agentops-agent-id", input.agentId);
  return new NextRequest(
    "http://127.0.0.1:3001/api/mis/agent-gateway/approvals/request",
    {
      method: "POST",
      headers,
      body: JSON.stringify(input.body),
    },
  );
}

async function responseJson(response: Response) {
  const body = await response.json() as JsonObject;
  const serialized = JSON.stringify(body);
  for (const secret of [TOKEN_A, TOKEN_B, TOKEN_NO_SCOPE, TOKEN_OTHER, SECRET_MARKER]) {
    assert.equal(serialized.includes(secret), false, "response_must_omit_sensitive_values");
  }
  return body;
}

async function expectRouteError(response: Response, status: number, code: string) {
  assert.equal(response.status, status);
  assert.match(String(response.headers.get("cache-control") || ""), /no-store/i);
  const body = await responseJson(response);
  assert.equal(body.error, code);
  assert.equal(body.token_omitted, true);
  return body;
}

async function captureFunction(request: Request): Promise<CapturedResponse> {
  try {
    return await requestCustomerDeliveryApproval(request);
  } catch (error) {
    return errorPayload(error);
  }
}

async function createBaseSchema(client: Client) {
  await client.query(`
    CREATE TABLE agents(
      agent_id TEXT PRIMARY KEY,
      runtime_type TEXT NOT NULL,
      model_provider TEXT,
      model_name TEXT
    );
    CREATE TABLE tasks(
      task_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      owner_agent_id TEXT,
      collaborator_agent_ids TEXT NOT NULL DEFAULT '[]',
      status TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE runs(
      run_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      task_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,
      runtime_type TEXT NOT NULL,
      model_provider TEXT,
      status TEXT NOT NULL
    );
    CREATE TABLE tool_calls(
      tool_call_id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,
      tool_name TEXT NOT NULL,
      normalized_args_json TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE evaluations(
      evaluation_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,
      evaluator_type TEXT NOT NULL,
      rubric_json TEXT NOT NULL,
      pass_fail TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE artifacts(
      artifact_id TEXT PRIMARY KEY,
      task_id TEXT,
      run_id TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE approvals(
      approval_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      tool_call_id TEXT,
      requested_by_agent_id TEXT,
      approver_user_id TEXT,
      decision TEXT NOT NULL,
      reason TEXT,
      expires_at TEXT,
      created_at TEXT NOT NULL,
      decided_at TEXT
    );
    CREATE TABLE prepared_actions(
      prepared_action_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      tool_call_id TEXT NOT NULL,
      approval_id TEXT,
      requested_by_agent_id TEXT
    );
    CREATE TABLE agent_gateway_enrollment_requests(
      request_id TEXT PRIMARY KEY,
      approval_id TEXT NOT NULL,
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      workspace_id TEXT NOT NULL,
      agent_id TEXT NOT NULL
    );
    CREATE TABLE agent_plans(
      plan_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      task_id TEXT,
      run_id TEXT,
      agent_id TEXT NOT NULL,
      task_understanding TEXT NOT NULL,
      referenced_specs_json TEXT NOT NULL,
      referenced_memories_json TEXT NOT NULL,
      referenced_bases_json TEXT NOT NULL,
      proposed_files_to_change_json TEXT NOT NULL,
      risk_level TEXT NOT NULL,
      approval_required INTEGER NOT NULL,
      execution_steps_json TEXT NOT NULL,
      verification_plan TEXT,
      rollback_plan TEXT,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE plan_evidence_manifests(
      manifest_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      plan_id TEXT NOT NULL,
      task_id TEXT,
      run_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,
      mismatch_policy TEXT NOT NULL,
      expected_steps_json TEXT NOT NULL,
      tool_call_ids_json TEXT NOT NULL,
      evaluation_ids_json TEXT NOT NULL,
      artifact_ids_json TEXT NOT NULL,
      audit_ids_json TEXT NOT NULL,
      status TEXT NOT NULL,
      verification_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE audit_logs(
      audit_id TEXT PRIMARY KEY,
      workspace_id TEXT,
      actor_type TEXT NOT NULL,
      actor_id TEXT,
      action TEXT NOT NULL,
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      before_hash TEXT,
      after_hash TEXT,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      tamper_chain_hash TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE runtime_events(
      runtime_event_id TEXT PRIMARY KEY,
      runtime_connector_id TEXT,
      event_type TEXT NOT NULL,
      status TEXT NOT NULL,
      run_id TEXT,
      task_id TEXT,
      agent_id TEXT,
      model_name TEXT,
      latency_ms INTEGER,
      prompt_hash TEXT,
      input_summary TEXT,
      output_summary TEXT,
      error_message TEXT,
      raw_payload_hash TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE agent_gateway_tokens(
      token_id TEXT PRIMARY KEY,
      token_hash TEXT NOT NULL UNIQUE,
      workspace_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,
      scopes_json TEXT NOT NULL,
      status TEXT NOT NULL,
      expires_at TEXT,
      last_used_at TEXT
    );
    CREATE TABLE agent_gateway_sessions(
      session_id TEXT PRIMARY KEY,
      session_hash TEXT NOT NULL UNIQUE,
      parent_token_id TEXT,
      workspace_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,
      scopes_json TEXT NOT NULL,
      status TEXT NOT NULL,
      expires_at TEXT,
      revoked_at TEXT,
      last_used_at TEXT
    );
  `);
  await client.query(await readFile(V4_MIGRATION_PATH, "utf8"));
  await client.query(await readFile(V5_MIGRATION_PATH, "utf8"));
}

async function seedVerifiedRun(
  client: Client,
  input: {
    taskId: string;
    runId: string;
    workspaceId?: string;
    agentId?: string;
    runtimeType?: "hermes" | "openclaw" | "mock";
    runStatus?: string;
    taskStatus?: string;
  },
) {
  const workspaceId = input.workspaceId || WORKSPACE;
  const agentId = input.agentId || AGENT;
  const runtimeType = input.runtimeType || "hermes";
  const now = new Date().toISOString();
  const toolId = `tool_${input.runId}`;
  const evaluationId = `eval_${input.runId}`;
  const artifactId = `art_${input.runId}`;
  const planId = `plan_${input.runId}`;
  const manifestId = `pem_${input.runId}`;
  const steps = JSON.stringify(["read bounded context", "execute provider call", "verify evidence"]);
  await client.query(
    `INSERT INTO tasks(task_id,workspace_id,owner_agent_id,collaborator_agent_ids,status,updated_at)
    VALUES($1,$2,$3,'[]',$4,$5)`,
    [input.taskId, workspaceId, agentId, input.taskStatus || "completed", now],
  );
  await client.query(
    `INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,model_provider,status)
    VALUES($1,$2,$3,$4,$5,$5,$6)`,
    [input.runId, workspaceId, input.taskId, agentId, runtimeType, input.runStatus || "completed"],
  );
  await client.query(
    `INSERT INTO agent_plans(
      plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,referenced_specs_json,
      referenced_memories_json,referenced_bases_json,proposed_files_to_change_json,risk_level,
      approval_required,execution_steps_json,verification_plan,rollback_plan,status,created_at,updated_at
    ) VALUES($1,$2,$3,$4,$5,'Produce bounded customer delivery evidence','["spec"]','["memory"]',
      '["base"]','[]','low',0,$6,'Verify the provider evidence.','Create a new run.','submitted',$7,$7)`,
    [planId, workspaceId, input.taskId, input.runId, agentId, steps, now],
  );
  await client.query(
    `INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,normalized_args_json,status,created_at)
    VALUES($1,$2,$3,$4,$5,'completed',$6)`,
    [
      toolId,
      input.runId,
      agentId,
      `agent_worker.${runtimeType}`,
      JSON.stringify({
        adapter: runtimeType,
        provider_call_performed: runtimeType !== "mock",
        dry_run: runtimeType === "mock",
      }),
      now,
    ],
  );
  await client.query(
    `INSERT INTO evaluations(
      evaluation_id,task_id,run_id,agent_id,evaluator_type,rubric_json,pass_fail,created_at
    ) VALUES($1,$2,$3,$4,'rule',$5,'pass',$6)`,
    [
      evaluationId,
      input.taskId,
      input.runId,
      agentId,
      JSON.stringify({
        adapter: runtimeType,
        provider_call_performed: runtimeType !== "mock",
        dry_run: runtimeType === "mock",
      }),
      now,
    ],
  );
  await client.query(
    "INSERT INTO artifacts(artifact_id,task_id,run_id,created_at) VALUES($1,$2,$3,$4)",
    [artifactId, input.taskId, input.runId, now],
  );

  const audits: Array<[string, string, string, string, JsonObject]> = [
    [`aud_plan_${input.runId}`, "agent_gateway.agent_plan_create", "agent_plans", planId, {}],
    [`aud_tool_${input.runId}`, "tool_call.create", "tool_calls", toolId, {}],
    [`aud_eval_${input.runId}`, "evaluation.create", "evaluations", evaluationId, {}],
    [
      `aud_art_${input.runId}`,
      "agent_gateway.artifact_record",
      "artifacts",
      artifactId,
      { content_hash: sha256(`artifact:${input.runId}`) },
    ],
    [
      `aud_worker_${input.runId}`,
      "agent_worker.task_processed",
      "runs",
      input.runId,
      {
        adapter: runtimeType,
        provider_call_performed: runtimeType !== "mock",
        dry_run: runtimeType === "mock",
      },
    ],
  ];
  for (let index = 0; index < audits.length; index += 1) {
    const [auditId, action, entityType, entityId, metadata] = audits[index];
    await client.query(
      `INSERT INTO audit_logs(
        audit_id,workspace_id,actor_type,actor_id,action,entity_type,entity_id,
        metadata_json,tamper_chain_hash,created_at
      ) VALUES($1,$2,'agent',$3,$4,$5,$6,$7,$8,$9)`,
      [
        auditId,
        workspaceId,
        agentId,
        action,
        entityType,
        entityId,
        JSON.stringify({ ...metadata, workspace_id: workspaceId }),
        sha256(`chain:${input.runId}:${index}`),
        new Date(Date.parse(now) + index).toISOString(),
      ],
    );
  }
  await client.query(
    `INSERT INTO plan_evidence_manifests(
      manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,
      expected_steps_json,tool_call_ids_json,evaluation_ids_json,artifact_ids_json,audit_ids_json,
      status,verification_json,created_at,updated_at
    ) VALUES($1,$2,$3,$4,$5,$6,'block',$7,$8,$9,$10,'[]','verified','{}',$11,$11)`,
    [
      manifestId,
      workspaceId,
      planId,
      input.taskId,
      input.runId,
      agentId,
      steps,
      JSON.stringify([toolId]),
      JSON.stringify([evaluationId]),
      JSON.stringify([artifactId]),
      now,
    ],
  );
}

async function listen(server: http.Server) {
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve());
  });
  const address = server.address();
  assert.ok(address && typeof address === "object");
  return address.port;
}

async function close(server: http.Server) {
  await new Promise<void>((resolve, reject) => {
    server.close((error) => error ? reject(error) : resolve());
  });
}

async function main() {
  const baseDsn = String(
    process.env.AGENTOPS_POSTGRES_DSN || process.env.DATABASE_URL || "",
  ).trim();
  if (!baseDsn) throw new Error("postgres_dsn_required");
  const schema = `agentops_delivery_request_${randomBytes(8).toString("hex")}`;
  const quotedSchema = `"${schema}"`;
  const admin = new Client({
    connectionString: baseDsn,
    application_name: "agentops-customer-delivery-approval-contract",
  });
  let schemaCreated = false;
  let proxyCalls = 0;
  let proxyPath = "";
  const proxyServer = http.createServer((request, response) => {
    proxyCalls += 1;
    proxyPath = String(request.url || "");
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer | string) => {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    });
    request.on("end", () => {
      response.writeHead(202, { "content-type": "application/json" });
      response.end(JSON.stringify({
        ok: true,
        provider: "free-local-python-fixture",
        body_bytes: Buffer.concat(chunks).byteLength,
        token_omitted: true,
      }));
    });
  });
  let proxyListening = false;
  try {
    await admin.connect();
    await admin.query(`CREATE SCHEMA ${quotedSchema}`);
    schemaCreated = true;
    await admin.query(`SET search_path TO ${quotedSchema}`);
    await createBaseSchema(admin);

    await admin.query(
      `INSERT INTO agents(agent_id,runtime_type,model_provider,model_name)
      VALUES($1,'hermes','hermes','contract'),($2,'openclaw','openclaw','contract')`,
      [AGENT, OTHER_AGENT],
    );
    const tokenRows: Array<[string, string, string, string, string[]]> = [
      ["tok_delivery_a", TOKEN_A, WORKSPACE, AGENT, ["approvals:request"]],
      ["tok_delivery_b", TOKEN_B, WORKSPACE, AGENT, ["approvals:request"]],
      ["tok_delivery_no_scope", TOKEN_NO_SCOPE, WORKSPACE, AGENT, ["tasks:read"]],
      ["tok_delivery_other", TOKEN_OTHER, OTHER_WORKSPACE, OTHER_AGENT, ["approvals:request"]],
    ];
    for (const [tokenId, token, workspaceId, agentId, scopes] of tokenRows) {
      await admin.query(
        `INSERT INTO agent_gateway_tokens(
          token_id,token_hash,workspace_id,agent_id,scopes_json,status
        ) VALUES($1,$2,$3,$4,$5,'active')`,
        [tokenId, tokenHash(token), workspaceId, agentId, JSON.stringify(scopes)],
      );
    }

    const runs = [
      ["tsk_delivery_main", "run_delivery_main"],
      ["tsk_delivery_race", "run_delivery_race"],
      ["tsk_delivery_custom", "run_delivery_custom"],
      ["tsk_delivery_collision", "run_delivery_collision"],
    ] as const;
    for (const [taskId, runId] of runs) {
      await seedVerifiedRun(admin, { taskId, runId });
    }
    await seedVerifiedRun(admin, {
      taskId: "tsk_delivery_mock",
      runId: "run_delivery_mock",
      runtimeType: "mock",
    });
    await seedVerifiedRun(admin, {
      taskId: "tsk_delivery_running",
      runId: "run_delivery_running",
      runStatus: "running",
    });
    await seedVerifiedRun(admin, {
      taskId: "tsk_delivery_foreign",
      runId: "run_delivery_foreign",
      workspaceId: OTHER_WORKSPACE,
      agentId: OTHER_AGENT,
      runtimeType: "openclaw",
    });
    await admin.query(
      `INSERT INTO approvals(
        approval_id,approval_kind,task_id,run_id,tool_call_id,requested_by_agent_id,
        approver_user_id,decision,reason,expires_at,created_at,decided_at
      ) VALUES(
        'ap_foreign_hidden','customer_delivery','tsk_delivery_foreign','run_delivery_foreign',
        NULL,$1,NULL,'pending','Foreign pending delivery',$2,$3,NULL
      )`,
      [
        OTHER_AGENT,
        new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString(),
        new Date().toISOString(),
      ],
    );

    const proxyPort = await listen(proxyServer);
    proxyListening = true;
    process.env.AGENTOPS_POSTGRES_DSN = scopedDsn(baseDsn, schema);
    process.env.AGENTOPS_POSTGRES_SSL = "0";
    process.env.AGENTOPS_API_BASE = `http://127.0.0.1:${proxyPort}/api`;
    process.env.AGENTOPS_DEPLOYMENT_MODE = "production";
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "postgres";

    const mainBody = {
      workspace_id: WORKSPACE,
      agent_id: AGENT,
      requested_by_agent_id: AGENT,
      task_id: "tsk_delivery_main",
      run_id: "run_delivery_main",
      approval_kind: "customer_delivery",
      reason: `Release review Bearer ${SECRET_MARKER} raw_prompt=${SECRET_MARKER}`,
      decision: "pending",
    };
    const createdAtMs = Date.now();
    const createdResponse = await requestApprovalRoute(gatewayRequest({
      token: TOKEN_A,
      workspaceId: WORKSPACE,
      agentId: AGENT,
      body: mainBody,
    }));
    assert.equal(createdResponse.status, 201);
    const createdBody = await responseJson(createdResponse);
    assert.equal(createdBody.control_plane, "typescript_postgres");
    assert.equal(createdBody.outcome, "created");
    const approval = createdBody.approval as JsonObject;
    assert.equal(approval.approval_kind, "customer_delivery");
    assert.equal(approval.approver_user_id, null);
    assert.equal(approval.decision, "pending");
    assert.equal(approval.requested_by_agent_id, AGENT);
    assert.match(String(approval.reason), /\[REDACTED\]/);
    const expiresAtMs = Date.parse(String(approval.expires_at));
    assert.ok(expiresAtMs >= createdAtMs + (47 * 60 * 60 * 1000));
    assert.ok(expiresAtMs <= createdAtMs + (49 * 60 * 60 * 1000));
    assert.deepEqual(createdBody.linked_state, {
      task_status: "waiting_approval",
      run_status: "completed",
    });
    assert.equal(proxyCalls, 0, "Postgres owner must never call the Python upstream");

    const replayResponse = await requestApprovalRoute(gatewayRequest({
      token: TOKEN_A,
      workspaceId: WORKSPACE,
      agentId: AGENT,
      body: mainBody,
    }));
    assert.equal(replayResponse.status, 200);
    const replayBody = await responseJson(replayResponse);
    assert.equal(replayBody.outcome, "unchanged");
    assert.deepEqual(replayBody.approval, createdBody.approval);

    const evidenceAfterReplay = (await admin.query<{
      approvals: string;
      runtime_events: string;
      request_audits: string;
      task_audits: string;
    }>(`
      SELECT
        (SELECT COUNT(*)::text FROM approvals WHERE run_id='run_delivery_main') AS approvals,
        (SELECT COUNT(*)::text FROM runtime_events
          WHERE run_id='run_delivery_main' AND event_type='approval.customer_delivery.request') AS runtime_events,
        (SELECT COUNT(*)::text FROM audit_logs
          WHERE entity_id=(SELECT approval_id FROM approvals WHERE run_id='run_delivery_main')
            AND action='agent_gateway.customer_delivery_approval_request') AS request_audits,
        (SELECT COUNT(*)::text FROM audit_logs
          WHERE entity_id='tsk_delivery_main'
            AND action='agent_gateway.customer_delivery_task_waiting_approval') AS task_audits
    `)).rows[0];
    assert.deepEqual(evidenceAfterReplay, {
      approvals: "1",
      runtime_events: "1",
      request_audits: "1",
      task_audits: "1",
    });

    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: { ...mainBody, run_id: "run_delivery_custom", task_id: "tsk_delivery_custom" },
      })),
      401,
      "unauthorized",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_NO_SCOPE,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: { ...mainBody, run_id: "run_delivery_custom", task_id: "tsk_delivery_custom" },
      })),
      403,
      "forbidden",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: OTHER_WORKSPACE,
        agentId: AGENT,
        body: { ...mainBody, run_id: "run_delivery_custom", task_id: "tsk_delivery_custom" },
      })),
      403,
      "forbidden",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: {
          ...mainBody,
          workspace_id: { forged: WORKSPACE },
          run_id: "run_delivery_custom",
          task_id: "tsk_delivery_custom",
        },
      })),
      400,
      "workspace_id_invalid",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: OTHER_AGENT,
        body: { ...mainBody, run_id: "run_delivery_custom", task_id: "tsk_delivery_custom" },
      })),
      403,
      "forbidden",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: {
          ...mainBody,
          run_id: "run_delivery_custom",
          task_id: "tsk_delivery_custom",
          approval_kind: "run_execution",
        },
      })),
      409,
      "approval_kind_owner_unsupported",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: {
          ...mainBody,
          run_id: "run_delivery_custom",
          task_id: "tsk_delivery_custom",
          approver_user_id: "usr_forged",
        },
      })),
      403,
      "approval_approver_human_owned",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: {
          ...mainBody,
          run_id: "run_delivery_custom",
          task_id: "tsk_delivery_custom",
          expires_at: new Date(Date.now() + 1000).toISOString(),
        },
      })),
      400,
      "approval_expiry_server_owned",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: {
          workspace_id: WORKSPACE,
          run_id: "run_delivery_custom",
          approval_kind: "customer_delivery",
          padding: "x".repeat(20_000),
        },
      })),
      413,
      "request_too_large",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: {
          ...mainBody,
          task_id: "tsk_delivery_foreign",
          run_id: "run_delivery_foreign",
        },
      })),
      404,
      "run_not_found",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: {
          ...mainBody,
          task_id: "tsk_delivery_mock",
          run_id: "run_delivery_mock",
        },
      })),
      409,
      "verified_plan_evidence_manifest_required",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: {
          ...mainBody,
          task_id: "tsk_delivery_running",
          run_id: "run_delivery_running",
        },
      })),
      409,
      "customer_delivery_run_incomplete",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: { ...mainBody, reason: "Changed immutable reason" },
      })),
      409,
      "customer_delivery_approval_immutable_conflict",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: { ...mainBody, approval_id: "ap_other_safe_id" },
      })),
      409,
      "customer_delivery_approval_immutable_conflict",
    );
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: {
          ...mainBody,
          task_id: "tsk_delivery_custom",
          run_id: "run_delivery_custom",
          approval_id: "unsafe approval id",
        },
      })),
      400,
      "approval_id_invalid",
    );

    const customApprovalId = "ap_customer_delivery_contract";
    const customResponse = await requestApprovalRoute(gatewayRequest({
      token: TOKEN_A,
      workspaceId: WORKSPACE,
      agentId: AGENT,
      body: {
        ...mainBody,
        task_id: "tsk_delivery_custom",
        run_id: "run_delivery_custom",
        approval_id: customApprovalId,
        reason: "Customer delivery contract review.",
      },
    }));
    assert.equal(customResponse.status, 201);
    assert.equal(
      ((await responseJson(customResponse)).approval as JsonObject).approval_id,
      customApprovalId,
    );
    const customApproval = await admin.query<{ approval_id: string; approver_user_id: string | null }>(
      "SELECT approval_id,approver_user_id FROM approvals WHERE run_id='run_delivery_custom'",
    );
    assert.deepEqual(customApproval.rows[0], {
      approval_id: customApprovalId,
      approver_user_id: null,
    });

    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: {
          ...mainBody,
          task_id: "tsk_delivery_collision",
          run_id: "run_delivery_collision",
          approval_id: "ap_foreign_hidden",
          reason: "Customer delivery collision test.",
        },
      })),
      409,
      "approval_id_unavailable",
    );

    const raceBody = {
      workspace_id: WORKSPACE,
      agent_id: AGENT,
      task_id: "tsk_delivery_race",
      run_id: "run_delivery_race",
      approval_kind: "customer_delivery",
      reason: "Concurrent customer delivery review.",
    };
    const [raceA, raceB] = await Promise.all([
      captureFunction(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: raceBody,
      })),
      captureFunction(gatewayRequest({
        token: TOKEN_B,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: raceBody,
      })),
    ]);
    assert.deepEqual(
      [raceA.status, raceB.status].sort((left, right) => left - right),
      [200, 201],
    );
    assert.deepEqual(
      [String(raceA.body.outcome), String(raceB.body.outcome)].sort(),
      ["created", "unchanged"],
    );
    const raceCounts = (await admin.query<{
      approvals: string;
      events: string;
      audits: string;
    }>(`
      SELECT
        (SELECT COUNT(*)::text FROM approvals WHERE run_id='run_delivery_race') AS approvals,
        (SELECT COUNT(*)::text FROM runtime_events
          WHERE run_id='run_delivery_race' AND event_type='approval.customer_delivery.request') AS events,
        (SELECT COUNT(*)::text FROM audit_logs
          WHERE action='agent_gateway.customer_delivery_approval_request'
            AND entity_id=(SELECT approval_id FROM approvals WHERE run_id='run_delivery_race')) AS audits
    `)).rows[0];
    assert.deepEqual(raceCounts, { approvals: "1", events: "1", audits: "1" });

    const storedEvidence = JSON.stringify((await admin.query(
      `SELECT event_type,input_summary,output_summary,error_message,raw_payload_hash
      FROM runtime_events WHERE event_type='approval.customer_delivery.request'`,
    )).rows) + JSON.stringify((await admin.query(
      `SELECT actor_id,action,entity_id,metadata_json FROM audit_logs
      WHERE action LIKE 'agent_gateway.customer_delivery%'`,
    )).rows);
    for (const secret of [TOKEN_A, TOKEN_B, TOKEN_NO_SCOPE, TOKEN_OTHER, SECRET_MARKER]) {
      assert.equal(storedEvidence.includes(secret), false, "durable_evidence_must_omit_secrets");
    }
    assert.equal(storedEvidence.includes("raw_prompt="), false);
    assert.match(storedEvidence, /raw_body_omitted/);
    assert.match(storedEvidence, /token_omitted/);

    const v4Guards = await admin.query<{ trigger_name: string }>(
      `SELECT trigger_record.tgname AS trigger_name
      FROM pg_trigger trigger_record
      WHERE trigger_record.tgrelid IN (
        'approvals'::regclass,'tool_calls'::regclass,'evaluations'::regclass,
        'artifacts'::regclass,'plan_evidence_manifests'::regclass,'agent_plans'::regclass
      ) AND NOT trigger_record.tgisinternal
      ORDER BY trigger_record.tgname`,
    );
    const triggerNames = new Set(v4Guards.rows.map((row) => row.trigger_name));
    for (const required of [
      "approvals_kind_immutable",
      "approvals_kind_binding_enforced",
      "tool_calls_customer_delivery_evidence_sealed",
      "evaluations_customer_delivery_evidence_sealed",
      "artifacts_customer_delivery_evidence_sealed",
      "manifests_customer_delivery_evidence_sealed",
      "agent_plans_customer_delivery_evidence_sealed",
    ]) {
      assert.equal(triggerNames.has(required), true, `v4_guard_missing:${required}`);
    }
    const deliveryUniqueIndex = await admin.query<{
      is_unique: boolean;
      predicate: string | null;
    }>(
      `SELECT index_record.indisunique AS is_unique,
        pg_get_expr(index_record.indpred,index_record.indrelid,true) AS predicate
      FROM pg_index index_record
      JOIN pg_class index_relation ON index_relation.oid=index_record.indexrelid
      WHERE index_record.indrelid='approvals'::regclass
        AND index_relation.relname='idx_approvals_customer_delivery_run_unique'`,
    );
    assert.deepEqual(deliveryUniqueIndex.rows, [{
      is_unique: true,
      predicate: "approval_kind = 'customer_delivery'::text",
    }]);
    await assert.rejects(
      admin.query(
        `INSERT INTO approvals(
          approval_id,approval_kind,task_id,run_id,tool_call_id,requested_by_agent_id,
          approver_user_id,decision,reason,expires_at,created_at,decided_at
        ) VALUES(
          'ap_direct_sql_duplicate','customer_delivery','tsk_delivery_main',
          'run_delivery_main',NULL,$1,NULL,'pending','Direct SQL duplicate',
          $2,$3,NULL
        )`,
        [
          AGENT,
          new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString(),
          new Date().toISOString(),
        ],
      ),
      /idx_approvals_customer_delivery_run_unique/,
    );
    await assert.rejects(
      admin.query(
        "UPDATE approvals SET approval_kind='run_execution' WHERE run_id='run_delivery_main'",
      ),
      /approval_kind_immutable/,
    );

    process.env.AGENTOPS_DEPLOYMENT_MODE = "development";
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        token: TOKEN_A,
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: raceBody,
      })),
      503,
      "customer_delivery_approval_proxy_mode_required",
    );
    assert.equal(proxyCalls, 0);

    process.env.AGENTOPS_DEPLOYMENT_MODE = "free_local";
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    const proxied = await requestApprovalRoute(gatewayRequest({
      token: TOKEN_A,
      workspaceId: WORKSPACE,
      agentId: AGENT,
      body: raceBody,
    }));
    assert.equal(proxied.status, 202);
    assert.equal((await responseJson(proxied)).provider, "free-local-python-fixture");
    assert.equal(proxyCalls, 1);
    assert.equal(proxyPath, "/api/agent-gateway/approvals/request");

    process.env.AGENTOPS_DEPLOYMENT_MODE = "production";
    process.env.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
    await expectRouteError(
      await requestApprovalRoute(gatewayRequest({
        workspaceId: WORKSPACE,
        agentId: AGENT,
        body: raceBody,
      })),
      401,
      "unauthorized",
    );
    assert.equal(proxyCalls, 1, "production configured proxy must still use the direct owner");

    process.stdout.write(`${JSON.stringify({
      ok: true,
      contract: "nextjs_postgres_customer_delivery_approval_request_v1",
      checks: {
        explicit_free_local_proxy_only: true,
        postgres_python_proxy_not_used: true,
        approval_scope_workspace_agent_binding: true,
        bounded_json_and_server_owned_expiry: true,
        customer_delivery_owner_only: true,
        completed_real_runtime_evidence_required: true,
        completed_run_preserved_task_waiting: true,
        approver_attribution_rejected: true,
        idempotent_immutable_replay: true,
        cross_workspace_ids_hidden: true,
        concurrent_single_winner_no_duplicate_evidence: true,
        v5_database_unique_bypass_rejected: true,
        v4_schema_guards_preserved: true,
        audit_runtime_raw_token_omission: true,
      },
      credentials_omitted: true,
    })}\n`);
  } finally {
    const pool = (globalThis as typeof globalThis & { __agentOpsControlPlanePool?: Pool })
      .__agentOpsControlPlanePool;
    await pool?.end().catch(() => undefined);
    if (proxyListening) await close(proxyServer).catch(() => undefined);
    if (schemaCreated) {
      await admin.query("SET search_path TO public").catch(() => undefined);
      await admin.query(`DROP SCHEMA ${quotedSchema} CASCADE`).catch(() => undefined);
    }
    await admin.end().catch(() => undefined);
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  const safe = message
    .replace(/postgres(?:ql)?:\/\/[^\s'"}]+/gi, "postgresql://[REDACTED]")
    .replace(/(bearer\s+)[a-z0-9._-]+/gi, "$1[REDACTED]")
    .replaceAll(SECRET_MARKER, "[REDACTED]")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 240);
  process.stdout.write(`${JSON.stringify({
    ok: false,
    error: "customer_delivery_approval_request_contract_failed",
    detail: safe || "assertion_failed",
    credentials_omitted: true,
  })}\n`);
  process.exitCode = 1;
});
