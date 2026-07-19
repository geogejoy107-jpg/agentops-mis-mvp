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
  const taskId = String(form.get("task_id") || "");
  if (!taskId) {
    return redirectBack(request, { release_status: "failed", error: "task_id_required" });
  }

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/workers/tasks/release`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task_id: taskId,
      reason: "Next form fallback released stuck worker task",
    }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok || payload?.released === false) {
    return redirectBack(request, { release_status: "failed", task_id: taskId, error: String(payload?.error || response.status) });
  }
  return redirectBack(request, {
    release_status: "released",
    task_id: taskId,
    released_runs: String((payload?.released_runs || []).length),
  });
}
