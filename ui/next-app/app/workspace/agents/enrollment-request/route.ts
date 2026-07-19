import { NextResponse } from "next/server";

import { legacyWorkspacePythonProxyGuard } from "@/server/controlPlane/legacyWorkspacePythonProxyGuard";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";
const DEFAULT_SCOPES = [
  "agents:heartbeat",
  "tasks:read",
  "tasks:claim",
  "runs:write",
  "toolcalls:write",
  "evaluations:submit",
  "audit:write",
];
const VALID_AGENT_GATEWAY_SCOPES = new Set([
  "agents:write",
  "agents:heartbeat",
  "agent_plans:read",
  "agent_plans:write",
  "plan_evidence:read",
  "plan_evidence:write",
  "knowledge:read",
  "knowledge:write",
  "tasks:create",
  "tasks:read",
  "tasks:claim",
  "runs:write",
  "toolcalls:write",
  "artifacts:write",
  "approvals:request",
  "memories:propose",
  "evaluations:submit",
  "audit:write",
]);
const VALID_RUNTIME_TYPES = new Set(["mock", "hermes", "openclaw"]);

function redirectBack(request: Request, params: Record<string, string>) {
  const url = new URL("/workspace/agents", request.url);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return NextResponse.redirect(url, 303);
}

function parseScopes(value: FormDataEntryValue | null) {
  const raw = String(value || "");
  const scopes = raw.split(/[\s,]+/).map((scope) => scope.trim()).filter(Boolean);
  return scopes.length ? scopes : DEFAULT_SCOPES;
}

function validId(value: string) {
  return Boolean(value && value.length <= 96 && /^[A-Za-z0-9_.:-]+$/.test(value));
}

export async function POST(request: Request) {
  const guardResponse = legacyWorkspacePythonProxyGuard(request);
  if (guardResponse) return guardResponse;

  const form = await request.formData();
  const agentId = String(form.get("agent_id") || "").trim();
  const name = String(form.get("name") || "").trim();
  const runtimeType = String(form.get("runtime_type") || "mock").trim();
  const workspaceId = String(form.get("workspace_id") || "local-demo").trim();
  const scopes = parseScopes(form.get("scopes"));
  const invalidScopes = scopes.filter((scope) => !VALID_AGENT_GATEWAY_SCOPES.has(scope));
  const ttlDays = Number(form.get("ttl_days") || 30);
  const heartbeatTimeoutSec = Number(form.get("heartbeat_timeout_sec") || 300);
  if (!validId(agentId)) {
    return redirectBack(request, { enrollment_status: "failed", error: "agent_id_invalid" });
  }
  if (!name) {
    return redirectBack(request, { enrollment_status: "failed", error: "name_required" });
  }
  if (!validId(workspaceId)) {
    return redirectBack(request, { enrollment_status: "failed", error: "workspace_id_invalid" });
  }
  if (!VALID_RUNTIME_TYPES.has(runtimeType)) {
    return redirectBack(request, { enrollment_status: "failed", error: "runtime_type_invalid" });
  }
  if (invalidScopes.length) {
    return redirectBack(request, { enrollment_status: "failed", error: "invalid_scopes" });
  }
  if (!Number.isFinite(ttlDays) || ttlDays < 1 || ttlDays > 365) {
    return redirectBack(request, { enrollment_status: "failed", error: "ttl_days_invalid" });
  }
  if (!Number.isFinite(heartbeatTimeoutSec) || heartbeatTimeoutSec < 30 || heartbeatTimeoutSec > 86400) {
    return redirectBack(request, { enrollment_status: "failed", error: "heartbeat_timeout_sec_invalid" });
  }

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/agent-gateway/enrollment/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: agentId,
      name,
      role: String(form.get("role") || "Remote AI Digital Employee"),
      runtime_type: runtimeType,
      workspace_id: workspaceId,
      label: String(form.get("label") || `${name} enrollment request`),
      scopes,
      ttl_days: ttlDays,
      heartbeat_timeout_sec: heartbeatTimeoutSec,
      reason: String(form.get("reason") || "Next worker console requested approval-gated remote agent enrollment."),
    }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok || payload?.token_issued === true) {
    return redirectBack(request, { enrollment_status: "failed", error: String(payload?.error || response.status) });
  }

  return redirectBack(request, {
    enrollment_status: "requested",
    request_id: String(payload?.request?.request_id || ""),
    approval_id: String(payload?.approval?.approval_id || payload?.request?.approval_id || ""),
    task_id: String(payload?.request?.task_id || ""),
  });
}
