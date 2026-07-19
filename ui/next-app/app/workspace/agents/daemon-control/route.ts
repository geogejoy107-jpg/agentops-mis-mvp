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

function boundedNumber(value: FormDataEntryValue | null, fallback: number, min: number, max: number) {
  const num = Number(value || fallback);
  if (!Number.isFinite(num) || num < min || num > max) {
    return null;
  }
  return num;
}

export async function POST(request: Request) {
  const guardResponse = legacyWorkspacePythonProxyGuard(request);
  if (guardResponse) return guardResponse;

  const form = await request.formData();
  const action = String(form.get("action") || "").trim();
  const adapter = String(form.get("adapter") || "mock").trim();
  if (!["start", "stop", "restart"].includes(action)) {
    return redirectBack(request, { daemon_status: "failed", error: "daemon_action_invalid" });
  }
  if (adapter !== "mock") {
    return redirectBack(request, { daemon_status: "failed", error: "mock_daemon_only_next_parity" });
  }

  const payload: Record<string, unknown> = { adapter: "mock" };
  if (action === "start" || action === "restart") {
    const pollInterval = boundedNumber(form.get("poll_interval"), 2, 1, 60);
    const maxTasks = boundedNumber(form.get("max_tasks"), 0, 0, 50);
    if (pollInterval === null) {
      return redirectBack(request, { daemon_status: "failed", error: "poll_interval_invalid" });
    }
    if (maxTasks === null) {
      return redirectBack(request, { daemon_status: "failed", error: "max_tasks_invalid" });
    }
    payload.confirm_run = false;
    payload.poll_interval = pollInterval;
    payload.max_tasks = maxTasks;
    payload.max_errors = 5;
    payload.status = ["planned"];
  }

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/workers/local/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || result?.ok === false) {
    return redirectBack(request, { daemon_status: "failed", action, error: String(result?.error || response.status) });
  }
  const daemon = result?.daemon || (Array.isArray(result?.daemons) ? result.daemons[0] : {});
  return redirectBack(request, {
    daemon_status: action === "stop" ? "stopped" : action === "restart" ? "restarted" : "started",
    action,
    adapter: "mock",
    pid: String(daemon?.pid || ""),
    running: String(Boolean(daemon?.running)),
  });
}
