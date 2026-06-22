import { NextResponse } from "next/server";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

function redirectBack(request: Request, params: Record<string, string>) {
  const url = new URL("/workspace/connectors", request.url);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return NextResponse.redirect(url, 303);
}

export async function POST(request: Request) {
  const form = await request.formData();
  const connectorId = String(form.get("connector_id") || "");
  const trustStatus = String(form.get("trust_status") || "");
  const allowed = new Set(["trusted", "review_required", "blocked"]);

  if (!connectorId) {
    return redirectBack(request, { trust_error: "missing_connector_id" });
  }
  if (!allowed.has(trustStatus)) {
    return redirectBack(request, { trust_error: "invalid_trust_status", connector_id: connectorId });
  }

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/runtime-connectors/${encodeURIComponent(connectorId)}/trust`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      trust_status: trustStatus,
      trust_note: `Next operator marked ${connectorId} as ${trustStatus}.`,
    }),
    cache: "no-store",
  });

  if (!response.ok) {
    return redirectBack(request, { trust_error: String(response.status), connector_id: connectorId });
  }

  return redirectBack(request, {
    connector_id: connectorId,
    trust_status: trustStatus,
  });
}
