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

function selectedAgentIds(form: FormData, ownerAgentId: string) {
  const ids = form
    .getAll("selected_agent_ids")
    .flatMap((value) => String(value || "").split(","))
    .map((value) => value.trim())
    .filter(Boolean);
  return Array.from(new Set(ids.length ? ids : [ownerAgentId]));
}

export async function POST(request: Request) {
  const form = await request.formData();
  const templateId = safeText(form.get("template_id"), "tpl_customer_kb_qa_bot");
  const ownerAgentId = safeText(form.get("owner_agent_id"), "agt_next_template_owner");
  const adapter = safeText(form.get("adapter"), "mock");
  if (!["mock", "hermes", "openclaw"].includes(adapter)) {
    return redirectBack(request, {
      template_job_status: "blocked",
      template_job_error: "adapter_invalid",
      customer_worker_adapter: adapter,
    });
  }

  const payload = {
    template_id: templateId,
    adapter,
    confirm_run: safeText(form.get("confirm_run"), "true") === "true",
    title: safeText(form.get("title"), "Next async customer template job"),
    description: safeText(form.get("description"), "Next.js submits a customer template as an async workflow job."),
    acceptance_criteria: safeText(form.get("acceptance_criteria"), "Workflow job must produce task/run/delivery/report evidence or a fail-closed entitlement result."),
    priority: safeChoice(form.get("priority"), ["low", "medium", "high", "urgent"], "high"),
    risk_level: safeChoice(form.get("risk_level"), ["low", "medium", "high", "critical"], "medium"),
    owner_agent_id: ownerAgentId,
    selected_agent_ids: selectedAgentIds(form, ownerAgentId),
  };

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/workflows/customer-task-templates/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const result = await response.json().catch(() => ({}));

  if (response.status === 403 && result?.error === "entitlement_required") {
    return redirectBack(request, {
      template_job_status: "blocked",
      capability: String(result.capability || "report_templates"),
      required_edition: String(result.required_edition || "pro_workspace"),
      current_edition: String(result.current_edition || "free_local"),
    });
  }

  if (!response.ok || result?.ok === false) {
    return redirectBack(request, {
      template_job_status: "failed",
      template_job_error: String(result?.error || result?.reason || response.status),
      template_job_id: String(result?.job_id || result?.job?.job_id || ""),
    });
  }

  return redirectBack(request, {
    template_job_status: "submitted",
    template_job_id: String(result.job_id || result?.job?.job_id || ""),
  });
}
