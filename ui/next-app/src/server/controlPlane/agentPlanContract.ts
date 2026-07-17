export type AgentPlanVerification = {
  pass: boolean;
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
  };
  token_omitted: true;
};

export type VerifiableAgentPlan = {
  referenced_specs_json: string;
  referenced_memories_json: string;
  referenced_bases_json: string;
  proposed_files_to_change_json: string;
  execution_steps_json: string;
  verification_plan: string | null;
  rollback_plan: string | null;
  risk_level: string;
  approval_required: number;
};

export function jsonList(value: string | null | undefined) {
  try {
    const parsed = JSON.parse(value || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
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
  return {
    pass: failed.length === 0,
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
    },
    token_omitted: true,
  };
}
