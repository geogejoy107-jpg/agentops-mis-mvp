import type { PoolClient } from "pg";

import { stableHash } from "./ledger";

const SHA256_HEX = /^[a-f0-9]{64}$/;
const COMMERCIAL_RUNTIME_TYPES = new Set(["hermes", "openclaw"]);

type PlanRow = {
  plan_id: string;
  workspace_id: string;
  task_id: string | null;
  run_id: string | null;
  agent_id: string;
  task_understanding: string;
  referenced_specs_json: string;
  referenced_memories_json: string;
  referenced_bases_json: string;
  proposed_files_to_change_json: string;
  risk_level: string;
  approval_required: number;
  execution_steps_json: string;
  verification_plan: string | null;
  rollback_plan: string | null;
  status: string;
  plan_version: number;
  plan_hash: string | null;
  verified_at: string | null;
  verification_result_hash: string | null;
  created_at: string;
};

type ManifestRow = {
  manifest_id: string;
  workspace_id: string;
  plan_id: string;
  task_id: string | null;
  run_id: string;
  agent_id: string;
  mismatch_policy: string;
  expected_steps_json: string;
  tool_call_ids_json: string;
  evaluation_ids_json: string;
  artifact_ids_json: string;
  audit_ids_json: string;
  plan_hash: string | null;
  verification_result_hash: string | null;
  status: string;
  verification_json: string;
};

type RunRow = {
  run_id: string;
  workspace_id: string;
  task_id: string;
  agent_id: string;
  runtime_type: string;
  model_provider: string | null;
  status: string;
  agent_plan_id: string | null;
  plan_hash: string | null;
};

type ToolRow = {
  tool_call_id: string;
  run_id: string;
  agent_id: string;
  tool_name: string;
  normalized_args_json: string;
  status: string;
};

type EvaluationRow = {
  evaluation_id: string;
  run_id: string;
  agent_id: string;
  evaluator_type: string;
  rubric_json: string;
  pass_fail: string;
};

type ArtifactRow = {
  artifact_id: string;
  task_id: string | null;
  run_id: string | null;
  content_hash: string | null;
};

type AuditRow = {
  audit_id: string;
  actor_type: string;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  metadata_json: string;
  tamper_chain_hash: string | null;
};

function jsonObject(value: string) {
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

function jsonList(value: string) {
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function identifierList(value: string) {
  return jsonList(value).map((item) => String(item)).filter(Boolean);
}

function exactOrServerDerived(authoritative: string[], declared: string[]) {
  if (!declared.length) return true;
  const left = [...new Set(authoritative)].sort();
  const right = [...new Set(declared)].sort();
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function planContract(plan: PlanRow) {
  return {
    workspace_id: plan.workspace_id,
    task_id: plan.task_id,
    run_id: plan.run_id,
    agent_id: plan.agent_id,
    task_understanding: plan.task_understanding || "",
    referenced_specs: jsonList(plan.referenced_specs_json),
    referenced_memories: jsonList(plan.referenced_memories_json),
    referenced_bases: jsonList(plan.referenced_bases_json),
    proposed_files_to_change: jsonList(plan.proposed_files_to_change_json),
    risk_level: plan.risk_level,
    approval_required: Boolean(plan.approval_required),
    execution_steps: jsonList(plan.execution_steps_json),
    verification_plan: plan.verification_plan || "",
    rollback_plan: plan.rollback_plan || "",
    plan_version: Number(plan.plan_version || 1),
  };
}

function verificationHash(planId: string, verification: Record<string, unknown>) {
  const quality = verification.quality && typeof verification.quality === "object"
    ? verification.quality as Record<string, unknown>
    : {};
  const failedChecks = Array.isArray(verification.failed_checks)
    ? verification.failed_checks
    : [];
  return stableHash({
    plan_id: planId,
    plan_hash: verification.plan_hash,
    pass: verification.pass,
    failed_checks: failedChecks.map((check) =>
      check && typeof check === "object"
        ? (check as Record<string, unknown>).id
        : undefined),
    summary: verification.summary || {},
    quality: {
      version: quality.version,
      score: quality.score,
      status: quality.status,
      failed_rubric_ids: quality.failed_rubric_ids || [],
    },
  });
}

export type CustomerDeliveryPlanEvidence = {
  required: true;
  pass: boolean;
  verification_pass: boolean;
  status: string;
  manifest_id: string | null;
  plan_id: string | null;
  plan_version: number | null;
  plan_hash: string | null;
  verification_result_hash: string | null;
  failed_checks: string[];
  evidence_counts: Record<string, number>;
  token_omitted: true;
};

function blocked(
  status: string,
  failedChecks: string[],
  input?: Partial<CustomerDeliveryPlanEvidence>,
): CustomerDeliveryPlanEvidence {
  return {
    required: true,
    pass: false,
    verification_pass: false,
    status,
    manifest_id: input?.manifest_id || null,
    plan_id: input?.plan_id || null,
    plan_version: input?.plan_version || null,
    plan_hash: input?.plan_hash || null,
    verification_result_hash: input?.verification_result_hash || null,
    failed_checks: failedChecks,
    evidence_counts: input?.evidence_counts || {},
    token_omitted: true,
  };
}

export async function verifyCurrentCustomerDeliveryPlanEvidence(
  client: PoolClient,
  workspaceId: string,
  taskId: string,
  run: RunRow,
  agentId: string,
): Promise<CustomerDeliveryPlanEvidence> {
  const manifestResult = await client.query<ManifestRow>(
    `SELECT manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,
      expected_steps_json,tool_call_ids_json,evaluation_ids_json,artifact_ids_json,
      audit_ids_json,plan_hash,verification_result_hash,status,verification_json
    FROM plan_evidence_manifests
    WHERE workspace_id=$1 AND task_id=$2 AND run_id=$3
    ORDER BY updated_at DESC,created_at DESC,manifest_id DESC
    LIMIT 1 FOR SHARE`,
    [workspaceId, taskId, run.run_id],
  );
  const manifest = manifestResult.rows[0];
  if (!manifest) {
    return blocked("blocked_missing_verified_manifest", ["manifest_exists"]);
  }

  const planResult = await client.query<PlanRow>(
    `SELECT plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,
      referenced_specs_json,referenced_memories_json,referenced_bases_json,
      proposed_files_to_change_json,risk_level,approval_required,
      execution_steps_json,verification_plan,rollback_plan,status,plan_version,
      plan_hash,verified_at,verification_result_hash,created_at
    FROM agent_plans
    WHERE plan_id=$1 AND workspace_id=$2 FOR SHARE`,
    [manifest.plan_id, workspaceId],
  );
  const plan = planResult.rows[0];
  if (!plan) {
    return blocked("blocked_manifest_binding_invalid", ["plan_exists"], {
      manifest_id: manifest.manifest_id,
      plan_id: manifest.plan_id,
    });
  }

  const storedVerification = jsonObject(manifest.verification_json);
  const planVerification = storedVerification.plan_verification
    && typeof storedVerification.plan_verification === "object"
    ? storedVerification.plan_verification as Record<string, unknown>
    : {};
  const planVersion = Number(plan.plan_version);
  const verifiedAt = Date.parse(String(plan.verified_at || ""));
  const createdAt = Date.parse(plan.created_at);
  const now = Date.now();
  const computedPlanHash = stableHash(planContract(plan));
  const failed: string[] = [];
  const check = (id: string, ok: boolean) => {
    if (!ok) failed.push(id);
  };

  check("manifest_status_verified", manifest.status === "verified");
  check("manifest_mismatch_policy_block", manifest.mismatch_policy === "block");
  check("manifest_verification_pass", storedVerification.pass === true);
  check(
    "manifest_verification_status",
    storedVerification.status === "verified",
  );
  check(
    "manifest_failed_checks_empty",
    Array.isArray(storedVerification.failed_checks)
      && storedVerification.failed_checks.length === 0,
  );
  check(
    "binding_workspace",
    manifest.workspace_id === workspaceId
      && plan.workspace_id === workspaceId
      && run.workspace_id === workspaceId,
  );
  check(
    "binding_task",
    manifest.task_id === taskId
      && run.task_id === taskId
      && (!plan.task_id || plan.task_id === taskId),
  );
  check(
    "binding_run",
    manifest.run_id === run.run_id
      && (!plan.run_id || plan.run_id === run.run_id),
  );
  check(
    "binding_agent",
    manifest.agent_id === agentId
      && plan.agent_id === agentId
      && run.agent_id === agentId,
  );
  check("plan_status", ["submitted", "approved"].includes(plan.status));
  check(
    "plan_approval_state",
    !plan.approval_required || plan.status === "approved",
  );
  check("plan_version_valid", Number.isInteger(planVersion) && planVersion >= 1);
  check("plan_hash_present", SHA256_HEX.test(String(plan.plan_hash || "")));
  check("plan_hash_current", plan.plan_hash === computedPlanHash);
  check(
    "plan_verified_at_valid",
    Number.isFinite(verifiedAt)
      && Number.isFinite(createdAt)
      && verifiedAt >= createdAt
      && verifiedAt <= now + 60_000,
  );
  check(
    "plan_verification_result_hash_present",
    SHA256_HEX.test(String(plan.verification_result_hash || "")),
  );
  check(
    "plan_verification_result_hash_current",
    planVerification.pass === true
      && planVerification.plan_hash === plan.plan_hash
      && verificationHash(plan.plan_id, planVerification)
        === plan.verification_result_hash,
  );
  check("run_plan_id_bound", run.agent_plan_id === plan.plan_id);
  check("run_plan_hash_bound", run.plan_hash === plan.plan_hash);
  check("manifest_plan_hash_bound", manifest.plan_hash === plan.plan_hash);
  check(
    "manifest_verification_hash_bound",
    manifest.verification_result_hash === plan.verification_result_hash,
  );
  check(
    "manifest_steps_bound",
    JSON.stringify(jsonList(manifest.expected_steps_json))
      === JSON.stringify(jsonList(plan.execution_steps_json)),
  );
  check(
    "commercial_run_completed",
    run.status === "completed",
  );
  const runtimeType = String(run.runtime_type || "").trim().toLowerCase();
  check("commercial_runtime_required", COMMERCIAL_RUNTIME_TYPES.has(runtimeType));
  check(
    "commercial_provider_bound",
    String(run.model_provider || "").trim().toLowerCase() === runtimeType,
  );

  const toolRows = (await client.query<ToolRow>(
    `SELECT tool_call_id,run_id,agent_id,tool_name,normalized_args_json,status
    FROM tool_calls WHERE run_id=$1 ORDER BY created_at,tool_call_id`,
    [run.run_id],
  )).rows;
  const evaluationRows = (await client.query<EvaluationRow>(
    `SELECT evaluation_id,run_id,agent_id,evaluator_type,rubric_json,pass_fail
    FROM evaluations WHERE run_id=$1 ORDER BY created_at,evaluation_id`,
    [run.run_id],
  )).rows;
  const artifactRows = (await client.query<ArtifactRow>(
    `SELECT artifact_id,task_id,run_id,content_hash
    FROM artifacts
    WHERE run_id=$1 OR (run_id IS NULL AND task_id=$2)
    ORDER BY created_at,artifact_id`,
    [run.run_id, taskId],
  )).rows;
  const entityIds = [
    plan.plan_id,
    run.run_id,
    taskId,
    ...toolRows.map((row) => row.tool_call_id),
    ...evaluationRows.map((row) => row.evaluation_id),
    ...artifactRows.map((row) => row.artifact_id),
  ];
  const auditRows = (await client.query<AuditRow>(
    `SELECT audit_id,actor_type,actor_id,action,entity_type,entity_id,
      metadata_json,tamper_chain_hash
    FROM audit_logs
    WHERE workspace_id=$1
      AND metadata_json::jsonb ->> 'workspace_id'=$1
      AND entity_id=ANY($2::text[])
    ORDER BY created_at,audit_id`,
    [workspaceId, entityIds],
  )).rows;

  const matchingTools = toolRows.filter((row) => {
    const args = jsonObject(row.normalized_args_json);
    return row.tool_name === `agent_worker.${runtimeType}`
      && row.run_id === run.run_id
      && row.agent_id === agentId
      && row.status === "completed"
      && args.adapter === runtimeType
      && args.provider_call_performed === true
      && args.dry_run === false;
  });
  const matchingEvaluations = evaluationRows.filter((row) => {
    const rubric = jsonObject(row.rubric_json);
    return row.run_id === run.run_id
      && row.agent_id === agentId
      && row.evaluator_type === "rule"
      && row.pass_fail === "pass"
      && rubric.adapter === runtimeType
      && rubric.provider_call_performed === true
      && rubric.dry_run === false;
  });
  const chainedAudit = (row: AuditRow) =>
    SHA256_HEX.test(String(row.tamper_chain_hash || ""));
  const matchingAudit = (
    entityType: string,
    entityId: string,
    actions: Set<string>,
  ) => auditRows.some((row) =>
    row.entity_type === entityType
      && row.entity_id === entityId
      && actions.has(row.action)
      && chainedAudit(row));
  const workerAudit = auditRows.some((row) => {
    const metadata = jsonObject(row.metadata_json);
    return row.actor_type === "agent"
      && row.actor_id === agentId
      && row.action === "agent_worker.task_processed"
      && row.entity_type === "runs"
      && row.entity_id === run.run_id
      && metadata.adapter === runtimeType
      && metadata.provider_call_performed === true
      && metadata.dry_run === false
      && chainedAudit(row);
  });

  check("tool_evidence_present", toolRows.length > 0);
  check(
    "tool_evidence_completed",
    toolRows.every((row) =>
      row.run_id === run.run_id
        && row.agent_id === agentId
        && row.status === "completed"),
  );
  check("commercial_worker_tool_provenance", matchingTools.length > 0);
  check("evaluation_evidence_present", evaluationRows.length > 0);
  check(
    "evaluation_evidence_passed",
    evaluationRows.every((row) =>
      row.run_id === run.run_id
        && row.agent_id === agentId
        && row.pass_fail === "pass"
        && row.evaluator_type !== "llm_mock"),
  );
  check("commercial_worker_evaluation_provenance", matchingEvaluations.length > 0);
  check("artifact_evidence_present", artifactRows.length > 0);
  check(
    "artifact_digest_provenance",
    artifactRows.every((row) =>
      SHA256_HEX.test(String(row.content_hash || ""))
        && (row.run_id === run.run_id || (row.run_id === null && row.task_id === taskId))),
  );
  check("audit_evidence_present", auditRows.length > 0);
  check("commercial_worker_audit_provenance", workerAudit);
  check(
    "plan_audit_coverage",
    matchingAudit(
      "agent_plans",
      plan.plan_id,
      new Set(["agent_gateway.agent_plan_create", "agent_gateway.agent_plan_update"]),
    ),
  );
  check(
    "tool_audit_coverage",
    toolRows.every((row) =>
      matchingAudit(
        "tool_calls",
        row.tool_call_id,
        new Set(["tool_call.create", "tool_call.update"]),
      )),
  );
  check(
    "evaluation_audit_coverage",
    evaluationRows.every((row) =>
      matchingAudit("evaluations", row.evaluation_id, new Set(["evaluation.create"]))),
  );
  check(
    "artifact_audit_coverage",
    artifactRows.every((row) => {
      const audit = auditRows.find((candidate) =>
        candidate.entity_type === "artifacts"
          && candidate.entity_id === row.artifact_id
          && candidate.action === "agent_gateway.artifact_record"
          && chainedAudit(candidate));
      const metadata = audit ? jsonObject(audit.metadata_json) : {};
      return metadata.content_hash === row.content_hash;
    }),
  );
  check(
    "declared_tool_evidence_complete",
    exactOrServerDerived(
      toolRows.map((row) => row.tool_call_id),
      identifierList(manifest.tool_call_ids_json),
    ),
  );
  check(
    "declared_evaluation_evidence_complete",
    exactOrServerDerived(
      evaluationRows.map((row) => row.evaluation_id),
      identifierList(manifest.evaluation_ids_json),
    ),
  );
  check(
    "declared_artifact_evidence_complete",
    exactOrServerDerived(
      artifactRows.map((row) => row.artifact_id),
      identifierList(manifest.artifact_ids_json),
    ),
  );
  check(
    "declared_audit_evidence_complete",
    exactOrServerDerived(
      auditRows.map((row) => row.audit_id),
      identifierList(manifest.audit_ids_json),
    ),
  );

  const evidenceCounts = {
    tool_calls: toolRows.length,
    evaluations: evaluationRows.length,
    artifacts: artifactRows.length,
    audit_logs: auditRows.length,
  };
  if (failed.length) {
    return blocked("blocked_manifest_verification_failed", failed, {
      manifest_id: manifest.manifest_id,
      plan_id: plan.plan_id,
      plan_version: planVersion,
      plan_hash: plan.plan_hash,
      verification_result_hash: plan.verification_result_hash,
      evidence_counts: evidenceCounts,
    });
  }
  return {
    required: true,
    pass: true,
    verification_pass: true,
    status: "verified",
    manifest_id: manifest.manifest_id,
    plan_id: plan.plan_id,
    plan_version: planVersion,
    plan_hash: plan.plan_hash,
    verification_result_hash: plan.verification_result_hash,
    failed_checks: [],
    evidence_counts: evidenceCounts,
    token_omitted: true,
  };
}
