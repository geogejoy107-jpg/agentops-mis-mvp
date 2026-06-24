import { NextResponse } from "next/server";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

function redirectBack(request: Request, params: Record<string, string>) {
  const url = new URL("/workspace/dispatch", request.url);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return NextResponse.redirect(url, 303);
}

function safeText(value: FormDataEntryValue | null, fallback: string) {
  const text = String(value || "").trim();
  return text || fallback;
}

function safeChoice(value: FormDataEntryValue | null, choices: string[], fallback: string) {
  const text = safeText(value, fallback);
  return choices.includes(text) ? text : fallback;
}

export async function POST(request: Request) {
  const form = await request.formData();
  const adapter = safeText(form.get("adapter"), "mock");
  if (!["mock", "hermes", "openclaw"].includes(adapter)) {
    return redirectBack(request, {
      customer_worker_status: "blocked",
      customer_worker_error: "adapter_invalid",
      customer_worker_adapter: adapter,
    });
  }
  const preparedActionId = safeText(form.get("prepared_action_id"), "");
  const requestHash = safeText(form.get("request_hash"), "");
  const isLiveAdapter = adapter === "hermes" || adapter === "openclaw";

  const payload = {
    adapter,
    confirm_run: isLiveAdapter,
    title: safeText(form.get("title"), "Next customer worker dispatch"),
    description: safeText(form.get("description"), "Next.js dispatches one safe mock customer-worker task."),
    acceptance_criteria: safeText(form.get("acceptance_criteria"), "Worker must write run, tool, evaluation, audit, artifact, memory, approval, and verified plan evidence."),
    priority: safeChoice(form.get("priority"), ["low", "medium", "high", "critical"], "high"),
    risk_level: safeChoice(form.get("risk_level"), ["low", "medium", "high", "critical"], "medium"),
    worker_agent_id: safeText(form.get("worker_agent_id"), "agt_next_customer_worker"),
    selected_agent_ids: [safeText(form.get("worker_agent_id"), "agt_next_customer_worker")],
    ...(preparedActionId ? { prepared_action_id: preparedActionId } : {}),
    ...(requestHash ? { request_hash: requestHash } : {}),
  };

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/workflows/customer-worker-task`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const result = await response.json().catch(() => ({}));

  if (response.status === 202 && result?.prepared_action_id) {
    return redirectBack(request, {
      customer_worker_status: "waiting_approval",
      customer_worker_adapter: adapter,
      customer_worker_prepared_action_id: String(result.prepared_action_id || ""),
      customer_worker_request_hash: String(result.request_hash || ""),
      customer_worker_approval_id: String(result.approval_id || ""),
      customer_worker_task_id: String(result.task_id || ""),
      customer_worker_run_id: String(result.run_id || ""),
    });
  }

  if (response.status === 428 && result?.error === "approval_required") {
    return redirectBack(request, {
      customer_worker_status: "waiting_approval",
      customer_worker_error: "approval_required",
      customer_worker_adapter: adapter,
      customer_worker_prepared_action_id: String(result.prepared_action_id || preparedActionId),
      customer_worker_request_hash: requestHash,
      customer_worker_approval_id: String(result.approval_id || ""),
    });
  }

  if (!response.ok || result?.ok === false) {
    return redirectBack(request, {
      customer_worker_status: "failed",
      customer_worker_error: String(result?.error || result?.reason || response.status),
      customer_worker_adapter: adapter,
      customer_worker_task_id: String(result?.task_id || ""),
      customer_worker_prepared_action_id: String(result?.prepared_action_id || preparedActionId),
      customer_worker_request_hash: String(result?.request_hash || requestHash),
      customer_worker_approval_id: String(result?.approval_id || ""),
    });
  }

  return redirectBack(request, {
    customer_worker_status: "started",
    customer_worker_adapter: adapter,
    customer_worker_task_id: String(result.task_id || ""),
    customer_worker_run_id: String(result.run_id || ""),
    customer_worker_artifact_id: String(result.artifact_id || ""),
    customer_worker_manifest_id: String(result.plan_evidence_manifest_id || ""),
    customer_worker_approval_id: String(result.approval_id || ""),
    customer_worker_prepared_action_id: String(result.prepared_action_id || preparedActionId),
    customer_worker_request_hash: String(result.request_hash || requestHash),
    customer_worker_prepared_status: String(result.prepared_action_status || ""),
  });
}
