import { NextResponse } from "next/server";

import { legacyWorkspacePythonProxyGuard } from "@/server/controlPlane/legacyWorkspacePythonProxyGuard";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

function redirectBack(request: Request, params: Record<string, string>) {
  const url = new URL("/workspace/external-bases/notion", request.url);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return NextResponse.redirect(url, 303);
}

export async function POST(request: Request) {
  const guardResponse = legacyWorkspacePythonProxyGuard(request);
  if (guardResponse) return guardResponse;

  const form = await request.formData();
  const mode = String(form.get("mode") || "dry_run");
  const targetPath = mode === "confirmed" ? "/integrations/notion/export-confirmed" : "/integrations/notion/dry-run-export";
  const body = mode === "confirmed"
    ? { confirm_export: true, title: "AgentOps MIS Next parity export" }
    : {};

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}${targetPath}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  let payload: Record<string, unknown> = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }

  if (!response.ok) {
    return redirectBack(request, {
      notion_export: mode,
      export_error: String(response.status),
      capability: String(payload.capability || ""),
    });
  }

  return redirectBack(request, {
    notion_export: mode,
    status: payload.dry_run ? "dry_run" : payload.created ? "created" : "prepared",
    sync_event_id: String(payload.sync_event_id || ""),
  });
}
