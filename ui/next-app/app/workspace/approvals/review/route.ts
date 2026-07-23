import { NextResponse } from "next/server";

import { decideWorkspaceApproval } from "@/server/controlPlane/approvalDecisions";
import { readBoundedBody } from "@/server/controlPlane/boundedJson";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { legacyWorkspacePythonProxyGuard } from "@/server/controlPlane/legacyWorkspacePythonProxyGuard";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";
const FORM_OPTIONS = { maxBytes: 8 * 1024, label: "Approval review" };
const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, X-AgentOps-Workspace-Id",
};

function redirectBack(request: Request, params: Record<string, string>) {
  const url = new URL("/workspace/approvals", request.url);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  const response = NextResponse.redirect(url, 303);
  response.headers.set("Cache-Control", PRIVATE_HEADERS["Cache-Control"]);
  response.headers.set("Vary", PRIVATE_HEADERS.Vary);
  return response;
}

function singleValue(form: URLSearchParams, name: string) {
  const values = form.getAll(name);
  if (values.length !== 1) return "";
  return String(values[0] || "").trim();
}

async function boundedForm(request: Request) {
  const mediaType = String(request.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase();
  if (mediaType !== "application/x-www-form-urlencoded") {
    throw new Error("approval_review_content_type_invalid");
  }
  const raw = await readBoundedBody(request, FORM_OPTIONS);
  const form = new URLSearchParams(raw.toString("utf8"));
  const allowed = new Set(["approval_id", "decision", "workspace_id", "csrf_token", "idempotency_key"]);
  if ([...form.keys()].some((key) => !allowed.has(key))) throw new Error("approval_review_form_invalid");
  return form;
}

export async function POST(request: Request) {
  const proxyMode = controlPlaneMode() === "proxy";
  if (proxyMode) {
    const guardResponse = legacyWorkspacePythonProxyGuard(request);
    if (guardResponse) return guardResponse;
  }

  let form: URLSearchParams;
  try {
    form = await boundedForm(request);
  } catch (error) {
    const code = error instanceof Error && /^[a-z0-9_]+$/.test(error.message)
      ? error.message
      : "approval_review_form_invalid";
    return redirectBack(request, { review_error: code });
  }
  const approvalId = singleValue(form, "approval_id");
  const requestedDecision = singleValue(form, "decision");
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(approvalId)) {
    return redirectBack(request, { review_error: "missing_approval_id" });
  }
  if (requestedDecision !== "approve" && requestedDecision !== "reject") {
    return NextResponse.json(
      { ok: false, error: "decision_invalid", message: "Approval decision must be approve or reject.", token_omitted: true },
      { status: 400, headers: PRIVATE_HEADERS },
    );
  }

  if (proxyMode) {
    const response = await fetch(
      `${TARGET_BASE.replace(/\/$/, "")}/approvals/${encodeURIComponent(approvalId)}/${requestedDecision}`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", cache: "no-store" },
    );
    if (!response.ok) {
      return redirectBack(request, { review_error: String(response.status), approval_id: approvalId });
    }
    return redirectBack(request, {
      approval_id: approvalId,
      decision: requestedDecision === "approve" ? "approved" : "rejected",
    });
  }

  const workspaceId = singleValue(form, "workspace_id");
  const csrfToken = singleValue(form, "csrf_token");
  const replayKey = singleValue(form, "idempotency_key");
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(workspaceId)
    || !/^[A-Fa-f0-9]{64}$/.test(csrfToken)
    || !/^[A-Za-z0-9._:-]{16,128}$/.test(replayKey)) {
    return redirectBack(request, { review_error: "human_approval_context_invalid", approval_id: approvalId });
  }
  const headers = new Headers(request.headers);
  headers.set("X-AgentOps-Workspace-Id", workspaceId);
  headers.set("X-AgentOps-CSRF", csrfToken);
  headers.set("Idempotency-Key", replayKey);
  const serviceRequest = new Request(request.url, { method: "POST", headers });
  try {
    const result = await decideWorkspaceApproval(
      serviceRequest,
      { workspace_id: workspaceId },
      approvalId,
      requestedDecision,
    );
    if (result.status !== 200) {
      return redirectBack(request, { review_error: String(result.status), approval_id: approvalId });
    }
    return redirectBack(request, {
      approval_id: approvalId,
      decision: requestedDecision === "approve" ? "approved" : "rejected",
    });
  } catch (error) {
    const failure = errorPayload(error);
    return redirectBack(request, {
      review_error: String((failure.body as { error?: string }).error || failure.status),
      approval_id: approvalId,
    });
  }
}
