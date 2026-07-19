import { NextResponse } from "next/server";

import { controlPlaneMode, isProductionDeployment } from "@/server/controlPlane/config";
import { legacyWorkspacePythonProxyGuard } from "@/server/controlPlane/legacyWorkspacePythonProxyGuard";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

function redirectBack(request: Request, params: Record<string, string>) {
  const url = new URL("/workspace/memory", request.url);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }
  return NextResponse.redirect(url, 303);
}

export async function POST(request: Request) {
  const guardResponse = legacyWorkspacePythonProxyGuard(request);
  if (guardResponse) return guardResponse;

  if (isProductionDeployment() || controlPlaneMode() === "postgres") {
    return NextResponse.json(
      {
        ok: false,
        error: "human_session_direct_route_required",
        message: "Commercial Memory Review requires the Human Session API route.",
        token_omitted: true,
      },
      { status: 409, headers: { "Cache-Control": "no-store" } },
    );
  }
  const form = await request.formData();
  const memoryId = String(form.get("memory_id") || "");
  const decision = String(form.get("decision") || "");

  if (!memoryId) {
    return redirectBack(request, { review_error: "missing_memory_id" });
  }
  if (decision !== "approve" && decision !== "reject") {
    return NextResponse.json(
      { ok: false, error: "decision_invalid", message: "Memory decision must be approve or reject." },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  const action = decision;

  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/memories/${encodeURIComponent(memoryId)}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    cache: "no-store",
  });

  if (!response.ok) {
    return redirectBack(request, { review_error: String(response.status), memory_id: memoryId });
  }

  return redirectBack(request, {
    memory_id: memoryId,
    decision: action === "approve" ? "approved" : "rejected",
  });
}
