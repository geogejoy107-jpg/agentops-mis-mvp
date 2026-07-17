import type { PoolClient } from "pg";

import { jsonList, verifyAgentPlanRow } from "./agentPlanContract";
import { authenticateAgentGateway, enforceWorkspaceBinding } from "./auth";
import { withPostgresTransaction } from "./db";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, appendRuntimeEvent, newLedgerId, stableHash } from "./ledger";

const RISK_LEVELS = new Set(["low", "medium", "high", "critical"]);
const PLAN_AGENT_STATUSES = new Set(["draft", "submitted"]);
const MANIFEST_POLICIES = new Set(["block", "warn"]);
const SENSITIVE_KEY = /(authorization|credential|password|secret|token|api[_-]?key|raw[_-]?(prompt|response|transcript|content))/i;

type TaskRow = {
  task_id: string;
  workspace_id: string;
  owner_agent_id: string | null;
  collaborator_agent_ids: string;
  status: string;
};

type RunRow = {
  run_id: string;
  workspace_id: string;
  task_id: string;
  agent_id: string;
  status: string;
};

export type AgentPlanRow = {
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
  created_at: string;
  updated_at: string;
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
  status: string;
  verification_json: string;
  created_at: string;
  updated_at: string;
};

type ToolEvidence = { tool_call_id: string; run_id: string; agent_id: string; status: string };
type EvaluationEvidence = { evaluation_id: string; run_id: string; agent_id: string; pass_fail: string };
type ArtifactEvidence = { artifact_id: string; run_id: string | null; task_id: string | null };
type AuditEvidence = { audit_id: string; entity_id: string };

function text(value: unknown, limit: number) {
  return String(value ?? "")
    .replace(/(bearer\s+)[a-z0-9._-]+/gi, "$1[REDACTED]")
    .replace(/(token|secret|password|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,;]+/gi, "$1=[REDACTED]")
    .replace(/\b(?:sk-[a-z0-9._-]+|ntn_[a-z0-9._-]+)\b/gi, "[SECRET_REDACTED]")
    .replace(/\b(?:agtok|agtsess)_[A-Za-z0-9_-]+\b/g, "[AGENT_TOKEN_REF_REDACTED]")
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "[EMAIL_REDACTED]")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, limit);
}

function identifier(value: unknown, field: string) {
  const normalized = String(value ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(400, `${field}_invalid`, `${field} must use 1-128 safe identifier characters.`);
  }
  return normalized;
}

function optionalIdentifier(value: unknown, field: string) {
  return value === undefined || value === null || value === "" ? null : identifier(value, field);
}

function choice(value: unknown, allowed: Set<string>, fallback: string) {
  const normalized = String(value ?? "").trim().toLowerCase();
  return allowed.has(normalized) ? normalized : fallback;
}

function bool(value: unknown) {
  return value === true || value === 1 || ["1", "true", "yes", "on"].includes(String(value ?? "").trim().toLowerCase());
}

function safeJson(value: unknown, depth = 0): unknown {
  if (depth >= 8) return "[TRUNCATED]";
  if (Array.isArray(value)) return value.slice(0, 40).map((item) => safeJson(item, depth + 1));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .slice(0, 40)
        .map(([rawKey, item]) => {
          const key = text(rawKey, 80);
          return [key, SENSITIVE_KEY.test(key) ? "[REDACTED]" : safeJson(item, depth + 1)];
        }),
    );
  }
  if (typeof value === "number" || typeof value === "boolean" || value === null) return value;
  return text(value, 240);
}

function listInput(value: unknown, field: string) {
  if (value === undefined || value === null || value === "") return [];
  let parsed = value;
  if (typeof value === "string") {
    try {
      parsed = JSON.parse(value);
    } catch {
      parsed = value.split(",").map((item) => item.trim()).filter(Boolean);
    }
  }
  if (!Array.isArray(parsed)) throw new ControlPlaneHttpError(400, `${field}_invalid`, `${field} must be a list.`);
  return parsed.slice(0, 40).map((item) => safeJson(item));
}

function identifierList(value: unknown, field: string) {
  return [...new Set(listInput(value, field).map((item) => identifier(item, field)))];
}

function listJson(value: unknown, field: string) {
  return JSON.stringify(listInput(value, field));
}

function collaborators(task: TaskRow) {
  return jsonList(task.collaborator_agent_ids).map((item) => String(item));
}

async function bodyObject(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json() as Record<string, unknown>;
  } catch {
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  if (!body || Array.isArray(body) || typeof body !== "object") {
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  return body;
}

function samePlan(left: AgentPlanRow, right: AgentPlanRow) {
  const fields: Array<keyof AgentPlanRow> = [
    "workspace_id", "task_id", "run_id", "agent_id", "task_understanding", "referenced_specs_json",
    "referenced_memories_json", "referenced_bases_json", "proposed_files_to_change_json", "risk_level",
    "approval_required", "execution_steps_json", "verification_plan", "rollback_plan", "status",
  ];
  return fields.every((field) => String(left[field] ?? "") === String(right[field] ?? ""));
}

function planResponse(row: AgentPlanRow, outcome: "created" | "updated" | "unchanged") {
  return {
    status: outcome === "created" ? 201 : 200,
    body: {
      ok: true,
      provider: "agentops-agent-plan",
      control_plane: "typescript_postgres",
      operation: "agent_plan_create",
      outcome,
      agent_plan: row,
      verification: verifyAgentPlanRow(row),
      token_omitted: true,
    },
  };
}

export async function createAgentGatewayPlan(request: Request) {
  const body = await bodyObject(request);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(client, request.headers, "agent_plans:write");
    enforceWorkspaceBinding(identity, {
      header: request.headers.get("x-agentops-workspace-id"),
      body: body.workspace_id,
    });
    if (body.agent_id !== undefined && text(body.agent_id, 120) !== identity.agentId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Agent credential cannot write another agent's plan.");
    }
    const requestedRunId = optionalIdentifier(body.run_id, "run_id");
    let taskId = optionalIdentifier(body.task_id, "task_id");
    let runCandidate: Pick<RunRow, "task_id" | "agent_id"> | undefined;
    if (requestedRunId) {
      const candidateResult = await client.query<Pick<RunRow, "task_id" | "agent_id">>(
        "SELECT task_id,agent_id FROM runs WHERE run_id=$1 AND workspace_id=$2",
        [requestedRunId, identity.workspaceId],
      );
      runCandidate = candidateResult.rows[0];
      if (!runCandidate) throw new ControlPlaneHttpError(404, "run_not_found", "Run was not found in the credential workspace.");
      if (runCandidate.agent_id !== identity.agentId) throw new ControlPlaneHttpError(403, "forbidden", "Run belongs to another agent.");
      if (taskId && taskId !== runCandidate.task_id) {
        throw new ControlPlaneHttpError(403, "forbidden", "Agent Plan task_id must match the target run.");
      }
      taskId = runCandidate.task_id;
    }
    if (!taskId) throw new ControlPlaneHttpError(400, "task_binding_required", "Agent Plan requires task_id or run_id.");

    const taskResult = await client.query<TaskRow>(
      "SELECT task_id,workspace_id,owner_agent_id,collaborator_agent_ids,status FROM tasks WHERE task_id=$1 AND workspace_id=$2 FOR UPDATE",
      [taskId, identity.workspaceId],
    );
    const task = taskResult.rows[0];
    if (!task) throw new ControlPlaneHttpError(404, "task_not_found", "Task was not found in the credential workspace.");
    if (task.owner_agent_id && task.owner_agent_id !== identity.agentId && !collaborators(task).includes(identity.agentId)) {
      throw new ControlPlaneHttpError(403, "forbidden", "Task is assigned to another agent.");
    }
    if (requestedRunId) {
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-run:${requestedRunId}`]);
      const lockedRun = await client.query<RunRow>(
        "SELECT run_id,workspace_id,task_id,agent_id,status FROM runs WHERE run_id=$1 AND workspace_id=$2 FOR UPDATE",
        [requestedRunId, identity.workspaceId],
      );
      const run = lockedRun.rows[0];
      if (!run || run.task_id !== taskId || run.agent_id !== identity.agentId) {
        throw new ControlPlaneHttpError(409, "run_immutable_binding_conflict", "Run binding changed while Agent Plan was waiting.");
      }
    }

    const planId = body.plan_id ? identifier(body.plan_id, "plan_id") : newLedgerId("plan");
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-plan:${planId}`]);
    const existingResult = await client.query<AgentPlanRow>("SELECT * FROM agent_plans WHERE plan_id=$1 FOR UPDATE", [planId]);
    const existing = existingResult.rows[0];
    if (existing && (
      existing.workspace_id !== identity.workspaceId
      || existing.task_id !== taskId
      || existing.run_id !== requestedRunId
      || existing.agent_id !== identity.agentId
    )) {
      throw new ControlPlaneHttpError(409, "agent_plan_immutable_binding_conflict", "plan_id is already bound to another execution identity.");
    }
    const requestedStatus = body.status === undefined && existing
      ? existing.status
      : choice(body.status, new Set(["draft", "submitted", "approved", "rejected", "superseded"]), "submitted");
    if (!PLAN_AGENT_STATUSES.has(requestedStatus)) {
      throw new ControlPlaneHttpError(403, "agent_plan_human_status_required", "Agent credentials may only create draft or submitted plans.");
    }
    const understanding = body.task_understanding === undefined && body.understanding === undefined && existing
      ? existing.task_understanding
      : text(body.task_understanding ?? body.understanding, 800);
    if (!understanding) throw new ControlPlaneHttpError(400, "task_understanding_required", "task_understanding is required.");
    const risk = body.risk_level === undefined && existing
      ? existing.risk_level
      : choice(body.risk_level, RISK_LEVELS, "medium");
    const approvalRequired = ["high", "critical"].includes(risk)
      || (body.approval_required === undefined && existing ? Boolean(existing.approval_required) : bool(body.approval_required));
    const value = (field: string, existingField: keyof AgentPlanRow) => body[field] === undefined && existing
      ? String(existing[existingField] || "[]")
      : listJson(body[field], field);
    const now = new Date().toISOString();
    const row: AgentPlanRow = {
      plan_id: planId,
      workspace_id: identity.workspaceId,
      task_id: taskId,
      run_id: requestedRunId,
      agent_id: identity.agentId,
      task_understanding: understanding,
      referenced_specs_json: value("referenced_specs", "referenced_specs_json"),
      referenced_memories_json: value("referenced_memories", "referenced_memories_json"),
      referenced_bases_json: value("referenced_bases", "referenced_bases_json"),
      proposed_files_to_change_json: value("proposed_files_to_change", "proposed_files_to_change_json"),
      risk_level: risk,
      approval_required: approvalRequired ? 1 : 0,
      execution_steps_json: value("execution_steps", "execution_steps_json"),
      verification_plan: body.verification_plan === undefined && existing ? existing.verification_plan : text(body.verification_plan, 800) || null,
      rollback_plan: body.rollback_plan === undefined && existing ? existing.rollback_plan : text(body.rollback_plan, 800) || null,
      status: requestedStatus,
      created_at: existing?.created_at || now,
      updated_at: existing?.updated_at || now,
    };
    const verification = verifyAgentPlanRow(row);
    if (row.status === "submitted" && !verification.pass) {
      throw new ControlPlaneHttpError(422, "agent_plan_verification_failed", "Submitted Agent Plan must pass READ/PLAN/EXECUTE/VERIFY/RECORD checks.");
    }
    if (existing && existing.status !== "draft") {
      if (samePlan(existing, row)) return planResponse(existing, "unchanged");
      throw new ControlPlaneHttpError(409, "agent_plan_immutable_conflict", "Submitted Agent Plan is immutable; create a new plan ID for revisions.");
    }
    if (existing && samePlan(existing, row)) return planResponse(existing, "unchanged");
    row.updated_at = now;
    if (existing) {
      await client.query(
        `UPDATE agent_plans SET task_understanding=$1,referenced_specs_json=$2,referenced_memories_json=$3,
          referenced_bases_json=$4,proposed_files_to_change_json=$5,risk_level=$6,approval_required=$7,
          execution_steps_json=$8,verification_plan=$9,rollback_plan=$10,status=$11,updated_at=$12 WHERE plan_id=$13`,
        [row.task_understanding, row.referenced_specs_json, row.referenced_memories_json, row.referenced_bases_json,
          row.proposed_files_to_change_json, row.risk_level, row.approval_required, row.execution_steps_json,
          row.verification_plan, row.rollback_plan, row.status, row.updated_at, row.plan_id],
      );
    } else {
      await client.query(
        `INSERT INTO agent_plans(plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,referenced_specs_json,
          referenced_memories_json,referenced_bases_json,proposed_files_to_change_json,risk_level,approval_required,
          execution_steps_json,verification_plan,rollback_plan,status,created_at,updated_at)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)`,
        [row.plan_id, row.workspace_id, row.task_id, row.run_id, row.agent_id, row.task_understanding,
          row.referenced_specs_json, row.referenced_memories_json, row.referenced_bases_json,
          row.proposed_files_to_change_json, row.risk_level, row.approval_required, row.execution_steps_json,
          row.verification_plan, row.rollback_plan, row.status, row.created_at, row.updated_at],
      );
    }
    await appendAudit(client, {
      actorType: "agent",
      actorId: identity.agentId,
      action: existing ? "agent_gateway.agent_plan_update" : "agent_gateway.agent_plan_create",
      entityType: "agent_plans",
      entityId: planId,
      before: existing || undefined,
      after: row,
      metadata: { workspace_id: identity.workspaceId, raw_omitted: true },
    });
    await appendRuntimeEvent(client, {
      eventType: "agent_plan.create",
      status: "completed",
      runId: requestedRunId,
      taskId,
      agentId: identity.agentId,
      outputSummary: understanding,
    });
    return planResponse(row, existing ? "updated" : "created");
  });
}

async function verifyManifest(
  client: PoolClient,
  manifest: ManifestRow,
  plan: AgentPlanRow,
  run: RunRow,
  task: TaskRow,
) {
  const expectedSteps = jsonList(manifest.expected_steps_json);
  const suppliedToolIds = jsonList(manifest.tool_call_ids_json).map(String);
  const suppliedEvaluationIds = jsonList(manifest.evaluation_ids_json).map(String);
  const suppliedArtifactIds = jsonList(manifest.artifact_ids_json).map(String);
  const suppliedAuditIds = jsonList(manifest.audit_ids_json).map(String);
  const toolRows = suppliedToolIds.length
    ? (await client.query<ToolEvidence>(
        `SELECT tool.* FROM tool_calls tool JOIN runs run ON run.run_id=tool.run_id
        WHERE tool.tool_call_id=ANY($1::text[]) AND run.workspace_id=$2`,
        [suppliedToolIds, manifest.workspace_id],
      )).rows
    : (await client.query<ToolEvidence>(
        `SELECT tool.* FROM tool_calls tool JOIN runs run ON run.run_id=tool.run_id
        WHERE tool.run_id=$1 AND run.workspace_id=$2 ORDER BY tool.created_at`,
        [manifest.run_id, manifest.workspace_id],
      )).rows;
  const evaluationRows = suppliedEvaluationIds.length
    ? (await client.query<EvaluationEvidence>(
        `SELECT evaluation.* FROM evaluations evaluation JOIN runs run ON run.run_id=evaluation.run_id
        WHERE evaluation.evaluation_id=ANY($1::text[]) AND run.workspace_id=$2`,
        [suppliedEvaluationIds, manifest.workspace_id],
      )).rows
    : (await client.query<EvaluationEvidence>(
        `SELECT evaluation.* FROM evaluations evaluation JOIN runs run ON run.run_id=evaluation.run_id
        WHERE evaluation.run_id=$1 AND run.workspace_id=$2 ORDER BY evaluation.created_at`,
        [manifest.run_id, manifest.workspace_id],
      )).rows;
  const artifactRows = suppliedArtifactIds.length
    ? (await client.query<ArtifactEvidence>(
        `SELECT DISTINCT artifact.* FROM artifacts artifact
        LEFT JOIN runs run ON run.run_id=artifact.run_id
        LEFT JOIN tasks task ON task.task_id=artifact.task_id
        WHERE artifact.artifact_id=ANY($1::text[])
          AND (artifact.run_id IS NULL OR run.workspace_id=$2)
          AND (artifact.task_id IS NULL OR task.workspace_id=$2)
          AND (run.workspace_id=$2 OR task.workspace_id=$2)`,
        [suppliedArtifactIds, manifest.workspace_id],
      )).rows
    : (await client.query<ArtifactEvidence>(
        `SELECT DISTINCT artifact.* FROM artifacts artifact
        LEFT JOIN runs run ON run.run_id=artifact.run_id
        LEFT JOIN tasks task ON task.task_id=artifact.task_id
        WHERE (artifact.run_id=$1 OR artifact.task_id=$2)
          AND (artifact.run_id IS NULL OR run.workspace_id=$3)
          AND (artifact.task_id IS NULL OR task.workspace_id=$3)
          AND (run.workspace_id=$3 OR task.workspace_id=$3)
        ORDER BY artifact.created_at`,
        [manifest.run_id, manifest.task_id, manifest.workspace_id],
      )).rows;
  const chainEntityIds = [
    manifest.plan_id,
    manifest.run_id,
    manifest.task_id,
    ...toolRows.map((row) => row.tool_call_id),
    ...evaluationRows.map((row) => row.evaluation_id),
    ...artifactRows.map((row) => row.artifact_id),
  ].filter((item): item is string => Boolean(item));
  const auditRows = suppliedAuditIds.length
    ? (await client.query<AuditEvidence>(
        "SELECT audit_id,entity_id FROM audit_logs WHERE audit_id=ANY($1::text[]) AND entity_id=ANY($2::text[])",
        [suppliedAuditIds, chainEntityIds],
      )).rows
    : (await client.query<AuditEvidence>("SELECT audit_id,entity_id FROM audit_logs WHERE entity_id=ANY($1::text[]) ORDER BY created_at", [chainEntityIds])).rows;
  const found = <T>(rows: T[], ids: string[], field: keyof T) => {
    if (!ids.length) return true;
    const values = new Set(rows.map((row) => String(row[field])));
    return ids.every((id) => values.has(id));
  };
  const planVerification = verifyAgentPlanRow(plan);
  const checks = [
    { id: "plan_exists", ok: Boolean(plan), message: "Manifest references an existing agent_plan." },
    { id: "plan_verifies", ok: planVerification.pass, message: "Referenced agent_plan passes method-block verification." },
    { id: "plan_status", ok: ["submitted", "approved"].includes(plan.status), message: "Referenced agent_plan is submitted or approved." },
    { id: "plan_approval_state", ok: !plan.approval_required || plan.status === "approved", message: "Approval-required plan has human-approved status." },
    { id: "run_exists", ok: Boolean(run), message: "Manifest references an existing run." },
    { id: "task_exists", ok: Boolean(task), message: "Manifest task exists." },
    { id: "workspace_match", ok: plan.workspace_id === manifest.workspace_id && run.workspace_id === manifest.workspace_id, message: "Plan, manifest and run are in the same workspace." },
    { id: "task_match", ok: (!plan.task_id || plan.task_id === manifest.task_id) && run.task_id === manifest.task_id, message: "Plan, manifest and run bind to the same task." },
    { id: "run_match", ok: !plan.run_id || plan.run_id === manifest.run_id, message: "Manifest run matches any run pinned by the plan." },
    { id: "agent_match", ok: plan.agent_id === manifest.agent_id && run.agent_id === manifest.agent_id, message: "Plan, manifest and run bind to the same agent." },
    { id: "expected_steps", ok: expectedSteps.length >= 3, message: "Manifest carries the approved execution steps." },
    { id: "tool_evidence_present", ok: toolRows.length >= 1, message: "Run has at least one tool_call evidence row." },
    { id: "tool_evidence_completed", ok: toolRows.length > 0 && toolRows.every((row) => row.run_id === manifest.run_id && row.agent_id === manifest.agent_id && row.status === "completed"), message: "Tool evidence belongs to the run and is completed." },
    { id: "tool_ids_found", ok: found(toolRows, suppliedToolIds, "tool_call_id"), message: "All declared tool_call_ids exist." },
    { id: "evaluation_evidence_present", ok: evaluationRows.length >= 1, message: "Run has at least one evaluation evidence row." },
    { id: "evaluation_evidence_passed", ok: evaluationRows.length > 0 && evaluationRows.every((row) => row.run_id === manifest.run_id && row.agent_id === manifest.agent_id && row.pass_fail === "pass"), message: "Evaluation evidence belongs to the run and passes." },
    { id: "evaluation_ids_found", ok: found(evaluationRows, suppliedEvaluationIds, "evaluation_id"), message: "All declared evaluation_ids exist." },
    { id: "artifact_evidence_present", ok: artifactRows.length >= 1, message: "Run or task has at least one artifact evidence row." },
    { id: "artifact_evidence_bound", ok: artifactRows.length > 0 && artifactRows.every((row) => row.run_id === manifest.run_id || row.task_id === manifest.task_id), message: "Artifact evidence is bound to the run or task." },
    { id: "artifact_ids_found", ok: found(artifactRows, suppliedArtifactIds, "artifact_id"), message: "All declared artifact_ids exist." },
    { id: "audit_evidence_present", ok: auditRows.length >= 1, message: "Ledger has audit evidence for the plan/run/tool/eval/artifact chain." },
    { id: "audit_ids_found", ok: found(auditRows, suppliedAuditIds, "audit_id"), message: "All declared audit_ids exist." },
    { id: "audit_evidence_bound", ok: auditRows.every((row) => chainEntityIds.includes(row.entity_id)), message: "Declared audit evidence belongs to the manifest chain." },
  ];
  const failed = checks.filter((check) => !check.ok);
  const status = failed.length === 0 ? "verified" : manifest.mismatch_policy === "block" ? "blocked" : "warning";
  return {
    pass: failed.length === 0,
    status,
    mismatch_policy: manifest.mismatch_policy,
    checks,
    failed_checks: failed,
    plan_verification: planVerification,
    evidence_counts: {
      tool_calls: toolRows.length,
      evaluations: evaluationRows.length,
      artifacts: artifactRows.length,
      audit_logs: auditRows.length,
    },
    declared_counts: {
      tool_call_ids: suppliedToolIds.length,
      evaluation_ids: suppliedEvaluationIds.length,
      artifact_ids: suppliedArtifactIds.length,
      audit_ids: suppliedAuditIds.length,
    },
    token_omitted: true,
  };
}

function sameManifestBinding(left: ManifestRow, right: ManifestRow) {
  const fields: Array<keyof ManifestRow> = [
    "workspace_id", "plan_id", "task_id", "run_id", "agent_id", "mismatch_policy", "expected_steps_json",
    "tool_call_ids_json", "evaluation_ids_json", "artifact_ids_json", "audit_ids_json",
  ];
  return fields.every((field) => String(left[field] ?? "") === String(right[field] ?? ""));
}

function manifestResponse(row: ManifestRow, verification: unknown, outcome: "created" | "updated" | "unchanged") {
  return {
    status: outcome === "created" ? 201 : 200,
    body: {
      ok: true,
      provider: "agentops-plan-evidence",
      control_plane: "typescript_postgres",
      operation: "plan_evidence_manifest_create",
      outcome,
      manifest: row,
      verification,
      token_omitted: true,
    },
  };
}

export async function createAgentGatewayPlanEvidenceManifest(request: Request) {
  const body = await bodyObject(request);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(client, request.headers, "plan_evidence:write");
    enforceWorkspaceBinding(identity, {
      header: request.headers.get("x-agentops-workspace-id"),
      body: body.workspace_id,
    });
    if (body.agent_id !== undefined && text(body.agent_id, 120) !== identity.agentId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Agent credential cannot write another agent's manifest.");
    }
    const planId = identifier(body.plan_id, "plan_id");
    const runId = identifier(body.run_id, "run_id");
    const planCandidateResult = await client.query<Pick<AgentPlanRow, "task_id" | "run_id" | "agent_id">>(
      "SELECT task_id,run_id,agent_id FROM agent_plans WHERE plan_id=$1 AND workspace_id=$2",
      [planId, identity.workspaceId],
    );
    const runCandidateResult = await client.query<Pick<RunRow, "task_id" | "agent_id">>(
      "SELECT task_id,agent_id FROM runs WHERE run_id=$1 AND workspace_id=$2",
      [runId, identity.workspaceId],
    );
    const planCandidate = planCandidateResult.rows[0];
    const runCandidate = runCandidateResult.rows[0];
    if (!planCandidate) throw new ControlPlaneHttpError(404, "agent_plan_not_found", "Agent Plan was not found in the credential workspace.");
    if (!runCandidate) throw new ControlPlaneHttpError(404, "run_not_found", "Run was not found in the credential workspace.");
    if (planCandidate.agent_id !== identity.agentId || runCandidate.agent_id !== identity.agentId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Plan and run must belong to the credential agent.");
    }
    const taskId = optionalIdentifier(body.task_id, "task_id") || runCandidate.task_id || planCandidate.task_id;
    if (!taskId || (planCandidate.task_id && planCandidate.task_id !== taskId) || runCandidate.task_id !== taskId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Manifest task_id must match the referenced plan and run.");
    }
    if (planCandidate.run_id && planCandidate.run_id !== runId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Manifest run_id must match the run pinned by the Agent Plan.");
    }
    const taskResult = await client.query<TaskRow>(
      "SELECT task_id,workspace_id,owner_agent_id,collaborator_agent_ids,status FROM tasks WHERE task_id=$1 AND workspace_id=$2 FOR UPDATE",
      [taskId, identity.workspaceId],
    );
    const task = taskResult.rows[0];
    if (!task) throw new ControlPlaneHttpError(404, "task_not_found", "Manifest task was not found in the credential workspace.");
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-run:${runId}`]);
    const runResult = await client.query<RunRow>(
      "SELECT run_id,workspace_id,task_id,agent_id,status FROM runs WHERE run_id=$1 AND workspace_id=$2 FOR UPDATE",
      [runId, identity.workspaceId],
    );
    const run = runResult.rows[0];
    if (!run || run.task_id !== taskId || run.agent_id !== identity.agentId) {
      throw new ControlPlaneHttpError(409, "run_immutable_binding_conflict", "Run binding changed while manifest was waiting.");
    }
    const planResult = await client.query<AgentPlanRow>(
      "SELECT * FROM agent_plans WHERE plan_id=$1 AND workspace_id=$2 FOR UPDATE",
      [planId, identity.workspaceId],
    );
    const plan = planResult.rows[0];
    if (!plan || plan.agent_id !== identity.agentId || (plan.task_id && plan.task_id !== taskId) || (plan.run_id && plan.run_id !== runId)) {
      throw new ControlPlaneHttpError(409, "agent_plan_immutable_binding_conflict", "Agent Plan binding changed while manifest was waiting.");
    }

    const manifestId = body.manifest_id ? identifier(body.manifest_id, "manifest_id") : newLedgerId("pem");
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-plan-evidence:${manifestId}`]);
    const existingResult = await client.query<ManifestRow>("SELECT * FROM plan_evidence_manifests WHERE manifest_id=$1 FOR UPDATE", [manifestId]);
    const existing = existingResult.rows[0];
    const expectedSteps = body.expected_steps === undefined
      ? plan.execution_steps_json
      : JSON.stringify(listInput(body.expected_steps, "expected_steps"));
    const now = new Date().toISOString();
    const candidate: ManifestRow = {
      manifest_id: manifestId,
      workspace_id: identity.workspaceId,
      plan_id: planId,
      task_id: taskId,
      run_id: runId,
      agent_id: identity.agentId,
      mismatch_policy: choice(body.mismatch_policy, MANIFEST_POLICIES, "block"),
      expected_steps_json: expectedSteps,
      tool_call_ids_json: JSON.stringify(identifierList(body.tool_call_ids, "tool_call_ids")),
      evaluation_ids_json: JSON.stringify(identifierList(body.evaluation_ids, "evaluation_ids")),
      artifact_ids_json: JSON.stringify(identifierList(body.artifact_ids, "artifact_ids")),
      audit_ids_json: JSON.stringify(identifierList(body.audit_ids, "audit_ids")),
      status: existing?.status || "submitted",
      verification_json: existing?.verification_json || "{}",
      created_at: existing?.created_at || now,
      updated_at: existing?.updated_at || now,
    };
    if (existing && !sameManifestBinding(existing, candidate)) {
      throw new ControlPlaneHttpError(409, "plan_evidence_immutable_conflict", "manifest_id is immutable; create a new manifest for revised evidence bindings.");
    }
    const verifyNow = body.verify_now !== false;
    const verification = verifyNow ? await verifyManifest(client, candidate, plan, run, task) : null;
    if (verification) {
      candidate.status = verification.status;
      candidate.verification_json = JSON.stringify(verification);
    }
    if (existing && existing.status === candidate.status && existing.verification_json === candidate.verification_json) {
      return manifestResponse(existing, verification || JSON.parse(existing.verification_json || "{}"), "unchanged");
    }
    candidate.updated_at = now;
    if (existing) {
      await client.query(
        "UPDATE plan_evidence_manifests SET status=$1,verification_json=$2,updated_at=$3 WHERE manifest_id=$4",
        [candidate.status, candidate.verification_json, candidate.updated_at, manifestId],
      );
    } else {
      await client.query(
        `INSERT INTO plan_evidence_manifests(manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,
          expected_steps_json,tool_call_ids_json,evaluation_ids_json,artifact_ids_json,audit_ids_json,status,
          verification_json,created_at,updated_at)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)`,
        [candidate.manifest_id, candidate.workspace_id, candidate.plan_id, candidate.task_id, candidate.run_id,
          candidate.agent_id, candidate.mismatch_policy, candidate.expected_steps_json, candidate.tool_call_ids_json,
          candidate.evaluation_ids_json, candidate.artifact_ids_json, candidate.audit_ids_json, candidate.status,
          candidate.verification_json, candidate.created_at, candidate.updated_at],
      );
    }
    await appendAudit(client, {
      actorType: "agent",
      actorId: identity.agentId,
      action: existing ? "agent_gateway.plan_evidence_manifest_verify" : "agent_gateway.plan_evidence_manifest_create",
      entityType: "plan_evidence_manifests",
      entityId: manifestId,
      before: existing || undefined,
      after: candidate,
      metadata: { workspace_id: identity.workspaceId, raw_omitted: true },
    });
    await appendRuntimeEvent(client, {
      eventType: existing ? "plan_evidence_manifest.verify" : "plan_evidence_manifest.create",
      status: candidate.status,
      runId,
      taskId,
      agentId: identity.agentId,
      outputSummary: `Plan evidence manifest ${manifestId} ${candidate.status}.`,
    });
    return manifestResponse(candidate, verification, existing ? "updated" : "created");
  });
}
