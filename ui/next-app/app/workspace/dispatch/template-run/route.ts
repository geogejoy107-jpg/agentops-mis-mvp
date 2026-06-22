import { NextResponse } from "next/server";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

function redirectBack(request: Request, params: Record<string, string>) {
  const url = new URL("/workspace/dispatch", request.url);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return NextResponse.redirect(url, 303);
}

export async function POST(request: Request) {
  const form = await request.formData();
  const templateId = String(form.get("template_id") || "");
  if (!templateId) {
    return redirectBack(request, { run_status: "failed", error: "missing_template_id" });
  }

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/workflows/customer-task-templates/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template_id: templateId }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));

  if (response.status === 403 && payload?.error === "entitlement_required") {
    return redirectBack(request, {
      run_status: "blocked",
      capability: String(payload.capability || "report_templates"),
      required_edition: String(payload.required_edition || "pro_workspace"),
      current_edition: String(payload.current_edition || "free_local"),
    });
  }
  if (!response.ok || payload?.ok === false) {
    return redirectBack(request, { run_status: "failed", error: String(payload?.error || response.status) });
  }
  return redirectBack(request, {
    run_status: "started",
    project_id: String(payload.project_id || ""),
  });
}
