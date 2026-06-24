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
  const ownerAgentId = safeText(form.get("owner_agent_id"), "agt_next_customer_owner");
  const confirmRun = safeText(form.get("confirm_run"), "false") === "true";
  const payload = {
    title: safeText(form.get("title"), "Next owner customer task"),
    description: safeText(form.get("description"), "Next.js creates a customer task from the owner dispatch composer."),
    acceptance_criteria: safeText(form.get("acceptance_criteria"), "MIS must record task, run-plan, audit, and safe evidence without raw prompt leakage."),
    priority: safeChoice(form.get("priority"), ["low", "medium", "high", "urgent"], "high"),
    risk_level: safeChoice(form.get("risk_level"), ["low", "medium", "high", "critical"], "medium"),
    template_id: safeText(form.get("template_id"), "tpl_customer_kb_qa_bot"),
    workflow_kind: safeText(form.get("workflow_kind"), "customer_task"),
    owner_agent_id: ownerAgentId,
    selected_agent_ids: selectedAgentIds(form, ownerAgentId),
    confirm_run: confirmRun,
  };

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/workflows/customer-task`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const result = await response.json().catch(() => ({}));

  if (!response.ok || result?.ok === false) {
    return redirectBack(request, {
      customer_task_status: "failed",
      customer_task_error: String(result?.error || result?.reason || response.status),
      customer_task_id: String(result?.task_id || ""),
    });
  }

  const dryRun = result?.dry_run !== false && !result?.run_id;
  return redirectBack(request, {
    customer_task_status: dryRun ? "dry_run" : "started",
    customer_task_id: String(result?.task_id || ""),
    customer_task_run_id: String(result?.run_id || ""),
    customer_task_prompt_hash: String(result?.prompt_hash || ""),
  });
}
