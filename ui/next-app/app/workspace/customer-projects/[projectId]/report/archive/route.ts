import { NextResponse } from "next/server";

import { legacyWorkspacePythonProxyGuard } from "@/server/controlPlane/legacyWorkspacePythonProxyGuard";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

type RouteContext = {
  params: Promise<{ projectId: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const guardResponse = legacyWorkspacePythonProxyGuard(request);
  if (guardResponse) return guardResponse;

  const { projectId } = await context.params;
  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}/workflows/customer-projects/${encodeURIComponent(projectId)}/report-artifact`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    cache: "no-store",
  });

  const url = new URL(`/workspace/customer-projects/${encodeURIComponent(projectId)}/report`, request.url);
  if (!response.ok) {
    url.searchParams.set("archive_error", String(response.status));
  } else {
    url.searchParams.set("archived", "true");
  }
  return NextResponse.redirect(url, 303);
}
