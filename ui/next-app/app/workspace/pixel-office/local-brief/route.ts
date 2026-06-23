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
  if (truthy(form.get("confirm_run"))) {
    return redirectBack(request, {
      local_brief_status: "blocked",
      local_brief_error: "local_brief_live_not_allowed_next_parity",
    });
  }

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/workflows/local-brief`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      confirm_run: false,
      source: "next_pixel_office_local_brief",
    }),
    cache: "no-store",
  });
  const result = await response.json().catch(() => ({}));

  if (!response.ok || result?.error) {
    return redirectBack(request, {
      local_brief_status: "failed",
      local_brief_error: String(result?.error || result?.reason || response.status),
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
