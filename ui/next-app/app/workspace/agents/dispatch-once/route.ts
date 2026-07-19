import { NextResponse } from "next/server";

import { legacyWorkspacePythonProxyGuard } from "@/server/controlPlane/legacyWorkspacePythonProxyGuard";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

function redirectBack(request: Request, params: Record<string, string>) {
  const url = new URL("/workspace/agents", request.url);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return NextResponse.redirect(url, 303);
}

export async function POST(request: Request) {
  const guardResponse = legacyWorkspacePythonProxyGuard(request);
  if (guardResponse) return guardResponse;

  const form = await request.formData();
  const adapter = String(form.get("adapter") || "mock");
  if (adapter !== "mock") {
    return redirectBack(request, { dispatch_status: "failed", error: "mock_only_next_parity" });
  }

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/workers/local/dispatch-once`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      adapter: "mock",
      title: "Next form fallback mock worker dispatch task",
      description: "Triggered through the Next.js worker console form fallback.",
      acceptance_criteria: "Mock worker must complete and write run/tool/evaluation/audit plus plan evidence.",
    }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok || payload?.ok === false) {
    return redirectBack(request, { dispatch_status: "failed", error: String(payload?.error || response.status) });
  }
  const runId = payload?.worker_result?.results?.[0]?.run_id || "";
  return redirectBack(request, {
    dispatch_status: "started",
    task_id: String(payload.task_id || ""),
    run_id: String(runId),
  });
}
