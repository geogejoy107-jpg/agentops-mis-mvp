import { NextResponse } from "next/server";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

function redirectBack(request: Request, params: Record<string, string>) {
  const url = new URL("/workspace/pixel-office", request.url);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return NextResponse.redirect(url, 303);
}

function truthy(value: FormDataEntryValue | null) {
  const text = String(value || "").trim().toLowerCase();
  return ["1", "true", "yes", "on", "confirm"].includes(text);
}

export async function POST(request: Request) {
  const form = await request.formData();
  const confirmRun = truthy(form.get("confirm_run"));
  const preparedActionId = String(form.get("prepared_action_id") || "").trim();
  const promptHash = String(form.get("prompt_hash") || "").trim();
  const stateHash = String(form.get("state_hash") || "").trim();

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/workflows/local-brief`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      confirm_run: confirmRun,
      source: preparedActionId ? "next_pixel_office_local_brief_resume" : "next_pixel_office_local_brief",
      ...(preparedActionId ? { prepared_action_id: preparedActionId } : {}),
      ...(promptHash ? { prompt_hash: promptHash } : {}),
      ...(stateHash ? { state_hash: stateHash } : {}),
    }),
    cache: "no-store",
  });
  const result = await response.json().catch(() => ({}));

  if (response.status === 202 || result?.requires_approval) {
    return redirectBack(request, {
      local_brief_status: "waiting_approval",
      local_brief_prepared_action_id: String(result?.prepared_action_id || ""),
      local_brief_approval_id: String(result?.approval_id || ""),
      local_brief_prompt_hash: String(result?.prompt_hash || ""),
      local_brief_state_hash: String(result?.state_hash || ""),
      local_brief_prepared_status: String(result?.prepared_action_status || "waiting_approval"),
    });
  }

  if (response.status === 428 || result?.error === "approval_required") {
    return redirectBack(request, {
      local_brief_status: "waiting_approval",
      local_brief_error: "approval_required",
      local_brief_prepared_action_id: String(result?.prepared_action_id || preparedActionId),
      local_brief_approval_id: String(result?.approval_id || ""),
      local_brief_prompt_hash: promptHash,
      local_brief_state_hash: stateHash,
      local_brief_prepared_status: "waiting_approval",
    });
  }

  if (!response.ok || result?.error) {
    return redirectBack(request, {
      local_brief_status: "failed",
      local_brief_error: String(result?.error || result?.reason || response.status),
      local_brief_prepared_action_id: String(result?.prepared_action_id || preparedActionId),
      local_brief_prompt_hash: String(result?.prompt_hash || promptHash),
      local_brief_state_hash: String(result?.state_hash || stateHash),
    });
  }

  if (result?.dry_run === false && result?.ok === true) {
    return redirectBack(request, {
      local_brief_status: "live_run",
      local_brief_prepared_action_id: String(result?.prepared_action_id || preparedActionId),
      local_brief_prepared_status: String(result?.prepared_action_status || "consumed"),
      local_brief_run_id: String(result?.run_id || ""),
      local_brief_artifact_id: String(result?.artifact_id || ""),
      local_brief_prompt_hash: String(result?.prompt_hash || promptHash),
      local_brief_state_hash: String(result?.state_hash || stateHash),
    });
  }

  const preview = result?.state_preview || {};
  return redirectBack(request, {
    local_brief_status: "dry_run",
    local_brief_prompt_hash: String(result?.prompt_hash || ""),
    local_brief_state_hash: String(result?.state_hash || ""),
    local_brief_agents_total: String(preview?.agents_total ?? ""),
    local_brief_pending_approvals: String(preview?.pending_approvals ?? ""),
    local_brief_recent_real_runs: String(preview?.recent_real_runs ?? ""),
  });
}
