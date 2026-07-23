import { createHash, randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { Client } from "pg";

import {
  requestCustomerDeliveryApproval,
  validateCustomerDeliveryApprovalInput,
} from "../src/server/controlPlane/agentGatewayApprovals";
import { closeControlPlanePoolForTests } from "../src/server/controlPlane/db";
import { ControlPlaneHttpError } from "../src/server/controlPlane/http";
import { stableHash } from "../src/server/controlPlane/ledger";
import { CUSTOMER_DELIVERY_SCHEMA_ASSUMPTIONS } from "../src/server/controlPlane/customerDeliverySchema";

function require(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function sha(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function planVerificationHash(
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

async function expectCode(
  expected: string,
  work: () => Promise<unknown> | unknown,
) {
  try {
    await work();
  } catch (error) {
    require(error instanceof ControlPlaneHttpError, `${expected}: wrong error type`);
    require(error.code === expected, `${expected}: received ${error.code}`);
    return;
  }
  throw new Error(`${expected}: request unexpectedly passed`);
}

function request(
  token: string | null,
  body: Record<string, unknown>,
  workspaceId = "ws_contract",
) {
  const headers = new Headers({
    "content-type": "application/json",
    "x-agentops-workspace-id": workspaceId,
    "x-agentops-agent-id": "agt_contract",
  });
  if (token) headers.set("authorization", `Bearer ${token}`);
  return new Request("http://agentops.test/api/mis/agent-gateway/approvals/request", {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

async function createContractSchema(client: Client) {
  await client.query(`
    CREATE TABLE agents(agent_id text PRIMARY KEY);
    CREATE TABLE agent_gateway_tokens(
      token_id text PRIMARY KEY,token_hash text UNIQUE NOT NULL,workspace_id text NOT NULL,
      agent_id text NOT NULL,scopes_json text NOT NULL,status text NOT NULL,
      expires_at text,last_used_at text
    );
    CREATE TABLE agent_gateway_sessions(
      session_id text PRIMARY KEY,session_hash text UNIQUE NOT NULL,parent_token_id text,
      workspace_id text NOT NULL,agent_id text NOT NULL,scopes_json text NOT NULL,
      status text NOT NULL,expires_at text NOT NULL,revoked_at text,last_used_at text
    );
    CREATE TABLE tasks(
      task_id text PRIMARY KEY,workspace_id text NOT NULL,owner_agent_id text,
      collaborator_agent_ids text NOT NULL,status text NOT NULL,updated_at text NOT NULL
    );
    CREATE TABLE agent_plans(
      plan_id text PRIMARY KEY,workspace_id text NOT NULL,task_id text,run_id text,
      agent_id text NOT NULL,task_understanding text NOT NULL,
      referenced_specs_json text NOT NULL,referenced_memories_json text NOT NULL,
      referenced_bases_json text NOT NULL,proposed_files_to_change_json text NOT NULL,
      risk_level text NOT NULL,approval_required integer NOT NULL,
      execution_steps_json text NOT NULL,verification_plan text,rollback_plan text,
      status text NOT NULL,plan_version integer NOT NULL,plan_hash text,verified_at text,
      verification_result_hash text,created_at text NOT NULL,updated_at text NOT NULL
    );
    CREATE TABLE runs(
      run_id text PRIMARY KEY,workspace_id text NOT NULL,task_id text NOT NULL,
      agent_id text NOT NULL,runtime_type text NOT NULL,model_provider text,status text NOT NULL,
      agent_plan_id text,plan_hash text,created_at text NOT NULL
    );
    CREATE TABLE tool_calls(
      tool_call_id text PRIMARY KEY,run_id text NOT NULL,agent_id text NOT NULL,
      tool_name text NOT NULL,normalized_args_json text NOT NULL,status text NOT NULL,
      created_at text NOT NULL
    );
    CREATE TABLE evaluations(
      evaluation_id text PRIMARY KEY,run_id text NOT NULL,agent_id text NOT NULL,
      evaluator_type text NOT NULL,rubric_json text NOT NULL,pass_fail text NOT NULL,
      created_at text NOT NULL
    );
    CREATE TABLE artifacts(
      artifact_id text PRIMARY KEY,task_id text,run_id text,content_hash text,
      created_at text NOT NULL
    );
    CREATE TABLE audit_logs(
      audit_id text PRIMARY KEY,workspace_id text,actor_type text NOT NULL,actor_id text,
      action text NOT NULL,entity_type text NOT NULL,entity_id text NOT NULL,
      before_hash text,after_hash text,metadata_json text NOT NULL,
      tamper_chain_hash text,created_at text NOT NULL
    );
    CREATE TABLE runtime_events(
      runtime_event_id text PRIMARY KEY,runtime_connector_id text,event_type text NOT NULL,
      status text NOT NULL,run_id text,task_id text,agent_id text,model_name text,
      latency_ms integer,prompt_hash text,input_summary text,output_summary text,
      error_message text,raw_payload_hash text,created_at text NOT NULL
    );
    CREATE TABLE plan_evidence_manifests(
      manifest_id text PRIMARY KEY,workspace_id text NOT NULL,plan_id text NOT NULL,
      task_id text,run_id text NOT NULL,agent_id text NOT NULL,mismatch_policy text NOT NULL,
      expected_steps_json text NOT NULL,tool_call_ids_json text NOT NULL,
      evaluation_ids_json text NOT NULL,artifact_ids_json text NOT NULL,
      audit_ids_json text NOT NULL,plan_hash text,verification_result_hash text,
      status text NOT NULL,verification_json text NOT NULL,
      created_at text NOT NULL,updated_at text NOT NULL
    );
    CREATE TABLE approvals(
      approval_id text PRIMARY KEY,approval_kind text NOT NULL,task_id text NOT NULL,
      run_id text NOT NULL,tool_call_id text,requested_by_agent_id text,
      approver_user_id text,decision text NOT NULL,reason text,expires_at text,
      created_at text NOT NULL,decided_at text
    );
    CREATE UNIQUE INDEX idx_approvals_customer_delivery_run_unique
      ON approvals(run_id) WHERE approval_kind='customer_delivery';

    CREATE FUNCTION contract_noop_trigger() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$;
    CREATE CONSTRAINT TRIGGER approvals_kind_binding_enforced
      AFTER INSERT OR UPDATE OR DELETE ON approvals
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION contract_noop_trigger();
    CREATE TRIGGER tool_calls_customer_delivery_evidence_sealed
      BEFORE INSERT OR UPDATE OR DELETE ON tool_calls
      FOR EACH ROW EXECUTE FUNCTION contract_noop_trigger();
    CREATE TRIGGER evaluations_customer_delivery_evidence_sealed
      BEFORE INSERT OR UPDATE OR DELETE ON evaluations
      FOR EACH ROW EXECUTE FUNCTION contract_noop_trigger();
    CREATE TRIGGER artifacts_customer_delivery_evidence_sealed
      BEFORE INSERT OR UPDATE OR DELETE ON artifacts
      FOR EACH ROW EXECUTE FUNCTION contract_noop_trigger();
    CREATE TRIGGER manifests_customer_delivery_evidence_sealed
      BEFORE INSERT OR UPDATE OR DELETE ON plan_evidence_manifests
      FOR EACH ROW EXECUTE FUNCTION contract_noop_trigger();
    CREATE TRIGGER agent_plans_customer_delivery_evidence_sealed
      BEFORE INSERT OR UPDATE OR DELETE ON agent_plans
      FOR EACH ROW EXECUTE FUNCTION contract_noop_trigger();
  `);
}

async function seedEvidence(
  client: Client,
  token: string,
  session: string,
) {
  const workspaceId = "ws_contract";
  const agentId = "agt_contract";
  const taskId = "tsk_contract";
  const runId = "run_contract";
  const planId = "plan_contract";
  const manifestId = "pem_contract";
  const toolId = "tc_contract";
  const evaluationId = "eval_contract";
  const artifactId = "art_contract";
  const now = new Date();
  const createdAt = new Date(now.getTime() - 10_000).toISOString();
  const verifiedAt = new Date(now.getTime() - 5_000).toISOString();
  const steps = ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"];
  const planContract = {
    workspace_id: workspaceId,
    task_id: taskId,
    run_id: runId,
    agent_id: agentId,
    task_understanding: "Prepare a verified Hermes customer delivery.",
    referenced_specs: ["PROJECT_SPEC.md"],
    referenced_memories: ["project-memory:928"],
    referenced_bases: ["base_local_tasks"],
    proposed_files_to_change: [],
    risk_level: "medium",
    approval_required: false,
    execution_steps: steps,
    verification_plan: "Verify evidence.",
    rollback_plan: "Keep delivery blocked.",
    plan_version: 3,
  };
  const planHash = stableHash(planContract);
  require(
    planHash === "64cd02cfc2b263deb29a9030930609603a11f50282ac529ef5af8e373e29882f",
    "TypeScript plan hash no longer matches current-main Python canonical JSON",
  );
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
  const verificationResultHash = planVerificationHash(planId, planVerification);
  require(
    verificationResultHash
      === "7cc45901c03a0caf4cf3ea75a7f889f23dea06a553d605833fc577dde0dabdd3",
    "TypeScript verification hash no longer matches current-main Python canonical JSON",
  );
  const auditRows = [
    ["aud_plan", "agent_gateway.agent_plan_create", "agent_plans", planId, {}],
    ["aud_tool", "tool_call.create", "tool_calls", toolId, {}],
    ["aud_eval", "evaluation.create", "evaluations", evaluationId, {}],
    ["aud_art", "agent_gateway.artifact_record", "artifacts", artifactId, {
      content_hash: sha("artifact"),
    }],
    ["aud_worker", "agent_worker.task_processed", "runs", runId, {
      adapter: "hermes",
      provider_call_performed: true,
      dry_run: false,
    }],
  ] as const;

  await client.query("INSERT INTO agents(agent_id) VALUES($1)", [agentId]);
  await client.query(
    `INSERT INTO agent_gateway_tokens(
      token_id,token_hash,workspace_id,agent_id,scopes_json,status,expires_at,last_used_at
    ) VALUES($1,$2,$3,$4,$5,'active',$6,NULL)`,
    [
      "tok_contract",
      sha(token),
      workspaceId,
      agentId,
      JSON.stringify(["approvals:request"]),
      new Date(now.getTime() + 3_600_000).toISOString(),
    ],
  );
  await client.query(
    `INSERT INTO agent_gateway_sessions(
      session_id,session_hash,parent_token_id,workspace_id,agent_id,scopes_json,
      status,expires_at,revoked_at,last_used_at
    ) VALUES($1,$2,'tok_contract',$3,$4,$5,'active',$6,NULL,NULL)`,
    [
      "sess_contract",
      sha(session),
      workspaceId,
      agentId,
      JSON.stringify(["approvals:request"]),
      new Date(now.getTime() + 600_000).toISOString(),
    ],
  );
  await client.query(
    `INSERT INTO tasks VALUES($1,$2,$3,'[]','completed',$4)`,
    [taskId, workspaceId, agentId, createdAt],
  );
  await client.query(
    `INSERT INTO agent_plans VALUES(
      $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,0,$12,$13,$14,'submitted',
      3,$15,$16,$17,$18,$16
    )`,
    [
      planId,
      workspaceId,
      taskId,
      runId,
      agentId,
      planContract.task_understanding,
      JSON.stringify(planContract.referenced_specs),
      JSON.stringify(planContract.referenced_memories),
      JSON.stringify(planContract.referenced_bases),
      JSON.stringify(planContract.proposed_files_to_change),
      planContract.risk_level,
      JSON.stringify(steps),
      planContract.verification_plan,
      planContract.rollback_plan,
      planHash,
      verifiedAt,
      verificationResultHash,
      createdAt,
    ],
  );
  await client.query(
    `INSERT INTO runs VALUES($1,$2,$3,$4,'hermes','hermes','completed',$5,$6,$7)`,
    [runId, workspaceId, taskId, agentId, planId, planHash, createdAt],
  );
  await client.query(
    `INSERT INTO tool_calls VALUES($1,$2,$3,'agent_worker.hermes',$4,'completed',$5)`,
    [
      toolId,
      runId,
      agentId,
      JSON.stringify({
        adapter: "hermes",
        provider_call_performed: true,
        dry_run: false,
      }),
      createdAt,
    ],
  );
  await client.query(
    `INSERT INTO evaluations VALUES($1,$2,$3,'rule',$4,'pass',$5)`,
    [
      evaluationId,
      runId,
      agentId,
      JSON.stringify({
        adapter: "hermes",
        provider_call_performed: true,
        dry_run: false,
      }),
      createdAt,
    ],
  );
  await client.query(
    `INSERT INTO artifacts VALUES($1,$2,$3,$4,$5)`,
    [artifactId, taskId, runId, sha("artifact"), createdAt],
  );
  for (const [auditId, action, entityType, entityId, metadata] of auditRows) {
    await client.query(
      `INSERT INTO audit_logs VALUES(
        $1,$2,'agent',$3,$4,$5,$6,NULL,NULL,$7,$8,$9
      )`,
      [
        auditId,
        workspaceId,
        agentId,
        action,
        entityType,
        entityId,
        JSON.stringify({ ...metadata, workspace_id: workspaceId }),
        sha(`chain:${auditId}`),
        createdAt,
      ],
    );
  }
  await client.query(
    `INSERT INTO plan_evidence_manifests VALUES(
      $1,$2,$3,$4,$5,$6,'block',$7,$8,$9,$10,'[]',$11,$12,'verified',$13,$14,$15
    )`,
    [
      manifestId,
      workspaceId,
      planId,
      taskId,
      runId,
      agentId,
      JSON.stringify(steps),
      JSON.stringify([toolId]),
      JSON.stringify([evaluationId]),
      JSON.stringify([artifactId]),
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
  return { workspaceId, taskId, runId, planHash, verificationResultHash };
}

async function sourceContract() {
  const scriptPath = fileURLToPath(import.meta.url);
  const appRoot = path.resolve(path.dirname(scriptPath), "..");
  const route = await readFile(
    path.join(appRoot, "app/api/mis/agent-gateway/approvals/request/route.ts"),
    "utf8",
  );
  const catchAll = await readFile(
    path.join(appRoot, "app/api/mis/[...path]/route.ts"),
    "utf8",
  );
  require(
    route.includes("requestCustomerDeliveryApproval")
      && route.includes("explicitFreeLocalProxyMode")
      && route.includes('"/agent-gateway/approvals/request"'),
    "specific customer-delivery route is not wired",
  );
  require(
    catchAll.includes('error: "typescript_route_owner_required"'),
    "catch-all production fail-closed boundary was removed",
  );
  require(
    CUSTOMER_DELIVERY_SCHEMA_ASSUMPTIONS.uniqueIndex
      === "idx_approvals_customer_delivery_run_unique"
      && CUSTOMER_DELIVERY_SCHEMA_ASSUMPTIONS.requiredTriggers.length === 6,
    "schema v4/v5 assumptions are incomplete",
  );

  validateCustomerDeliveryApprovalInput({
    approval_kind: "customer_delivery",
    decision: "pending",
  });
  await expectCode("approval_decision_human_owned", () =>
    validateCustomerDeliveryApprovalInput({
      approval_kind: "customer_delivery",
      decision: "approved",
    }));
  await expectCode("approval_approver_human_owned", () =>
    validateCustomerDeliveryApprovalInput({
      approval_kind: "customer_delivery",
      approver_user_id: "usr_self",
    }));
}

async function main() {
  await sourceContract();
  const baseDsn = String(process.env.AGENTOPS_POSTGRES_DSN || "").trim();
  require(baseDsn, "AGENTOPS_POSTGRES_DSN is required for the contract");
  const schema = `customer_delivery_contract_${randomUUID().replaceAll("-", "")}`;
  const admin = new Client({ connectionString: baseDsn });
  await admin.connect();
  const token = `contract_token_${randomUUID()}`;
  const session = `contract_session_${randomUUID()}`;
  try {
    await admin.query(`CREATE SCHEMA "${schema}"`);
    await admin.query(`SET search_path TO "${schema}"`);
    await createContractSchema(admin);
    const fixture = await seedEvidence(admin, token, session);

    const scopedDsn = new URL(baseDsn);
    scopedDsn.searchParams.set("options", `-csearch_path=${schema}`);
    process.env.AGENTOPS_POSTGRES_DSN = scopedDsn.toString();
    process.env.AGENTOPS_POSTGRES_POOL_MAX = "12";

    const body = {
      workspace_id: fixture.workspaceId,
      task_id: fixture.taskId,
      run_id: fixture.runId,
      agent_id: "agt_contract",
      requested_by_agent_id: "agt_contract",
      approval_kind: "customer_delivery",
      decision: "pending",
      reason: "Verified customer delivery review.",
    };
    await expectCode("unauthorized", () =>
      requestCustomerDeliveryApproval(request(null, body)));
    await expectCode("forbidden", () =>
      requestCustomerDeliveryApproval(request(token, {
        ...body,
        workspace_id: "ws_other",
      }, "ws_other")));
    await expectCode("approval_decision_human_owned", () =>
      requestCustomerDeliveryApproval(request(token, {
        ...body,
        decision: "approved",
      })));

    await admin.query(
      "UPDATE runs SET plan_hash=$1 WHERE run_id=$2",
      [sha("stale"), fixture.runId],
    );
    await expectCode("verified_plan_evidence_manifest_required", () =>
      requestCustomerDeliveryApproval(request(token, body)));
    await admin.query(
      "UPDATE runs SET plan_hash=$1 WHERE run_id=$2",
      [fixture.planHash, fixture.runId],
    );

    const attempts = Array.from({ length: 8 }, (_, index) =>
      requestCustomerDeliveryApproval(
        request(index % 2 === 0 ? token : session, body),
      ));
    const responses = await Promise.all(attempts);
    require(
      responses.filter((result) => result.status === 201).length === 1,
      "concurrency must create exactly one approval",
    );
    require(
      responses.filter((result) => result.status === 200).length === 7,
      "concurrency replays must return unchanged",
    );
    for (const result of responses) {
      const planEvidence = result.body.plan_evidence as Record<string, unknown>;
      require(result.body.operation === "customer_delivery_approval_request", "operation mismatch");
      require(result.body.control_plane === "typescript_postgres", "control plane mismatch");
      require(planEvidence.pass === true, "Worker-compatible pass is missing");
      require(planEvidence.verification_pass === true, "verification_pass is missing");
      require(planEvidence.plan_version === 3, "plan version binding is missing");
      require(planEvidence.plan_hash === fixture.planHash, "plan hash binding is missing");
      require(
        planEvidence.verification_result_hash === fixture.verificationResultHash,
        "verification result hash binding is missing",
      );
    }

    const counts = await admin.query<{
      approvals: string;
      runtime_events: string;
      request_audits: string;
    }>(
      `SELECT
        (SELECT COUNT(*) FROM approvals WHERE run_id=$1
          AND approval_kind='customer_delivery') AS approvals,
        (SELECT COUNT(*) FROM runtime_events WHERE run_id=$1
          AND event_type='approval.customer_delivery.request') AS runtime_events,
        (SELECT COUNT(*) FROM audit_logs WHERE action=
          'agent_gateway.customer_delivery_approval_request') AS request_audits`,
      [fixture.runId],
    );
    require(Number(counts.rows[0].approvals) === 1, "approval uniqueness failed");
    require(Number(counts.rows[0].runtime_events) === 1, "runtime event duplicated");
    require(Number(counts.rows[0].request_audits) === 1, "request audit duplicated");

    console.log(JSON.stringify({
      contract: "customer_delivery_approval_request_v2",
      ok: true,
      control_plane: "typescript_postgres",
      bearer_token_verified: true,
      bearer_session_verified: true,
      plan_version_bound: true,
      plan_hash_bound: true,
      verification_result_hash_bound: true,
      manifest_verification_pass: true,
      concurrent_attempts: attempts.length,
      created: 1,
      unchanged: attempts.length - 1,
      approval_rows: 1,
      python_api_started: false,
      token_omitted: true,
    }, null, 2));
  } finally {
    await closeControlPlanePoolForTests();
    await admin.query("RESET search_path").catch(() => undefined);
    await admin.query(`DROP SCHEMA IF EXISTS "${schema}" CASCADE`).catch(() => undefined);
    await admin.end();
  }
}

await main();
