import type {
  CommercialRuntime,
  GatewayTask,
  KnowledgeEvidence,
  PromptBundle,
} from "./contracts";
import { redactText, stableHash } from "./redaction";

const PROFILE_VERSION = "commercial_worker_prompt_profiles_v1" as const;

const PROFILES = Object.freeze({
  general_customer_delivery_summary: {
    objective: "Return a concise delivery summary with risks, evidence, and next actions.",
    outputContract: [
      "delivery_summary",
      "risks_or_blockers",
      "recommended_next_actions",
    ],
  },
  local_coding_project_summary: {
    objective: "Return implementation guidance and verification commands without editing files.",
    outputContract: [
      "implementation_plan",
      "affected_surfaces",
      "verification_commands",
      "risks_or_blockers",
    ],
  },
  knowledge_base_delivery_summary: {
    objective: "Return governed ingestion, retrieval, evaluation, and delivery guidance.",
    outputContract: [
      "source_preparation",
      "retrieval_design",
      "evaluation_questions",
      "delivery_report",
    ],
  },
  review_quality_gate_summary: {
    objective: "Assess acceptance gates and return missing evidence plus remediation.",
    outputContract: [
      "gate_assessment",
      "missing_evidence",
      "remediation_steps",
    ],
  },
});

function selectProfileId(task: GatewayTask): keyof typeof PROFILES {
  const combined = [
    task.title,
    task.description,
    task.acceptance_criteria,
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
  if (/(coding|code|repo|repository|worktree|branch|patch|test|tsx|typescript)/.test(combined)) {
    return "local_coding_project_summary";
  }
  if (/(knowledge|file search|q&a|dataset|retrieval)/.test(combined)) {
    return "knowledge_base_delivery_summary";
  }
  if (/(review|audit|evaluate|quality|acceptance)/.test(combined)) {
    return "review_quality_gate_summary";
  }
  return "general_customer_delivery_summary";
}

export function buildWorkerPrompt(
  task: GatewayTask,
  runtime: CommercialRuntime,
  knowledge: KnowledgeEvidence,
): PromptBundle {
  const profileId = selectProfileId(task);
  const selected = PROFILES[profileId];
  const profile = {
    profileId,
    version: PROFILE_VERSION,
    profileHash: stableHash({
      profile_id: profileId,
      version: PROFILE_VERSION,
      runtime,
      ...selected,
    }),
    ...selected,
  };
  const prompt = [
    "You are a governed AgentOps MIS commercial worker.",
    "This is a ledger-summary channel, not a tool-execution channel.",
    "Do not use shells, browsers, filesystems, external tools, APIs, publishing, uploads, or deployments.",
    "Do not claim those actions were performed. List them only as governed next actions.",
    "Never request or reveal credentials, hidden reasoning, raw prompts, raw responses, or private transcripts.",
    "Return 3-6 concise bullets.",
    `Runtime: ${runtime}`,
    `Task title: ${redactText(task.title, 180)}`,
    `Risk: ${redactText(task.risk_level || "medium", 40)}`,
    `Description: ${redactText(task.description, 900)}`,
    `Acceptance criteria: ${redactText(task.acceptance_criteria, 500)}`,
    `Profile: ${profile.profileId}@${profile.version}`,
    `Objective: ${profile.objective}`,
    `Output contract: ${profile.outputContract.join(", ")}`,
    `Knowledge status: ${redactText(knowledge.status, 60)}`,
    `Knowledge packet hash: ${redactText(knowledge.packetHash, 80)}`,
    `Knowledge paths: ${knowledge.paths.slice(0, 5).map((path) => redactText(path, 120)).join(", ") || "none"}`,
    "Knowledge snippets and raw content are omitted.",
  ].join("\n");
  return {
    prompt,
    promptHash: stableHash(prompt),
    profile,
  };
}

const EXTERNAL_WRITE_TERMS = Object.freeze([
  "publish",
  "upload",
  "deploy",
  "push",
  "send email",
  "webhook",
  "external write",
  "notion",
  "dataset",
  "file search",
  "customer portal",
]);

export function taskRequestsExternalWrite(task: GatewayTask) {
  const combined = [
    task.title,
    task.description,
    task.acceptance_criteria,
    task.target_resource,
    task.external_action_type,
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
  return EXTERNAL_WRITE_TERMS.some((term) => combined.includes(term));
}
