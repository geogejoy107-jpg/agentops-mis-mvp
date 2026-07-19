import { NextResponse } from "next/server";

import { legacyWorkspacePythonProxyGuard } from "@/server/controlPlane/legacyWorkspacePythonProxyGuard";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

function safeText(value: FormDataEntryValue | null, fallback: string) {
  const text = String(value || "").trim();
  return text || fallback;
}

function redirectBack(request: Request, params: Record<string, string>) {
  const url = new URL("/workspace/templates", request.url);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return NextResponse.redirect(url, 303);
}

export async function POST(request: Request) {
  const guardResponse = legacyWorkspacePythonProxyGuard(request);
  if (guardResponse) return guardResponse;

  const form = await request.formData();
  const templateId = safeText(form.get("template_id"), "tpl_ai_software_team");
  const fromBaseId = safeText(form.get("from_base_id"), "base_local_tasks");
  const toBaseId = safeText(form.get("to_base_id"), "base_notion_tasks");

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/migration/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      template_id: templateId,
      from_base_id: fromBaseId,
      to_base_id: toBaseId,
    }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok || payload?.error) {
    return redirectBack(request, {
      error: String(payload?.error || response.status),
      template_id: templateId,
      target_base_id: toBaseId,
    });
  }

  return redirectBack(request, {
    preview_status: "created",
    preview_template_id: String(payload.template_id || templateId),
    preview_from_base_id: String(payload.from_base?.base_id || fromBaseId),
    preview_to_base_id: String(payload.to_base?.base_id || toBaseId),
    template_id: templateId,
    target_base_id: toBaseId,
    migratable_count: String((payload.migratable_objects || []).length),
    protected_count: String((payload.non_migratable_objects || []).length),
  });
}
