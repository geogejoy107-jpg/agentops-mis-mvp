import { stableHash } from "./ledger";

export type AgentPlanVerification = {
  pass: boolean;
  plan_hash: string;
  checks: Array<{ id: string; ok: boolean; message: string }>;
  failed_checks: Array<{ id: string; ok: boolean; message: string }>;
  summary: {
    referenced_specs: number;
    referenced_memories: number;
    referenced_bases: number;
    proposed_files_to_change: number;
    execution_steps: number;
    risk_level: string;
    approval_required: boolean;
    quality_score: number;
    quality_status: string;
  };
  quality: {
    version: "agent_plan_quality_v1";
    score: number;
    status: "ready" | "blocked";
    failed_rubric_ids: string[];
  };
  token_omitted: true;
};

export type VerifiableAgentPlan = {
  workspace_id?: string;
  task_id?: string | null;
  run_id?: string | null;
  agent_id?: string;
  task_understanding?: string;
  referenced_specs_json: string;
  referenced_memories_json: string;
  referenced_bases_json: string;
  proposed_files_to_change_json: string;
  execution_steps_json: string;
  verification_plan: string | null;
  rollback_plan: string | null;
  risk_level: string;
  approval_required: number;
  plan_version?: number;
  plan_hash?: string | null;
};

export function jsonList(value: string | null | undefined) {
  try {
    const parsed = JSON.parse(value || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function computeAgentPlanHash(row: VerifiableAgentPlan) {
  return stableHash({
    workspace_id: row.workspace_id || null,
    task_id: row.task_id || null,
    run_id: row.run_id || null,
    agent_id: row.agent_id || null,
    task_understanding: row.task_understanding || "",
    referenced_specs: jsonList(row.referenced_specs_json),
    referenced_memories: jsonList(row.referenced_memories_json),
    referenced_bases: jsonList(row.referenced_bases_json),
    proposed_files_to_change: jsonList(row.proposed_files_to_change_json),
    risk_level: row.risk_level,
    approval_required: Boolean(row.approval_required),
    execution_steps: jsonList(row.execution_steps_json),
    verification_plan: row.verification_plan || "",
    rollback_plan: row.rollback_plan || "",
    plan_version: Number(row.plan_version || 1),
  });
}

export function agentPlanVerificationHash(
  planId: string,
  verification: {
    plan_hash: string;
    pass: boolean;
    failed_checks: Array<{ id: string }>;
    summary: object;
    quality: {
      version: string;
      score: number;
      status: string;
      failed_rubric_ids: string[];
    };
  },
) {
  return stableHash({
    plan_id: planId,
    plan_hash: verification.plan_hash,
    pass: verification.pass,
    failed_checks: verification.failed_checks.map((check) => check.id),
    summary: verification.summary,
    quality: {
      version: verification.quality.version,
      score: verification.quality.score,
      status: verification.quality.status,
      failed_rubric_ids: verification.quality.failed_rubric_ids,
    },
  });
}

export function verifyAgentPlanRow(row: VerifiableAgentPlan): AgentPlanVerification {
  const specs = jsonList(row.referenced_specs_json);
  const memories = jsonList(row.referenced_memories_json);
  const bases = jsonList(row.referenced_bases_json);
  const files = jsonList(row.proposed_files_to_change_json);
  const steps = jsonList(row.execution_steps_json);
  const approvalRequired = Boolean(row.approval_required);
  const checks = [
    { id: "read_specs", ok: specs.length > 0, message: "Plan references specs or workflow docs." },
    { id: "retrieve_memory", ok: memories.length > 0, message: "Plan references memory, knowledge, or failure-case context." },
    { id: "compare_bases", ok: bases.length > 0, message: "Plan references base constraints or reusable foundations." },
    { id: "execution_steps", ok: steps.length >= 3, message: "Plan includes concrete execution steps." },
    { id: "verification_plan", ok: Boolean(String(row.verification_plan || "").trim()), message: "Plan includes verification path." },
    { id: "rollback_plan", ok: Boolean(String(row.rollback_plan || "").trim()), message: "Plan includes rollback path." },
    { id: "risk_gate", ok: !["high", "critical"].includes(row.risk_level) || approvalRequired, message: "High/critical risk requires approval." },
    { id: "file_scope", ok: files.length > 0 || row.risk_level === "low", message: "Non-low work names proposed files or surfaces." },
  ];
  const failed = checks.filter((check) => !check.ok);
  const qualityScore = failed.length === 0
    ? 100
    : Math.max(0, 100 - failed.length * 15);
  const qualityStatus = failed.length === 0 ? "ready" : "blocked";
  return {
    pass: failed.length === 0,
    plan_hash: row.plan_hash || computeAgentPlanHash(row),
    checks,
    failed_checks: failed,
    summary: {
      referenced_specs: specs.length,
      referenced_memories: memories.length,
      referenced_bases: bases.length,
      proposed_files_to_change: files.length,
      execution_steps: steps.length,
      risk_level: row.risk_level,
      approval_required: approvalRequired,
      quality_score: qualityScore,
      quality_status: qualityStatus,
    },
    quality: {
      version: "agent_plan_quality_v1",
      score: qualityScore,
      status: qualityStatus,
      failed_rubric_ids: failed.map((check) => check.id),
    },
    token_omitted: true,
  };
}
