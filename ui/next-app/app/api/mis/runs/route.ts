import { NextRequest, NextResponse } from "next/server";

import { controlPlaneMode, isProductionDeployment } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";
import { listWorkspaceRuns } from "@/server/controlPlane/workspaceReadModels";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      if (isProductionDeployment()) {
        return NextResponse.json(
          { ok: false, error: "typescript_route_owner_required", message: "Production run reads require the TypeScript Postgres route." },
          { status: 503, headers: { "Cache-Control": "no-store", Vary: "Cookie, X-AgentOps-Workspace-Id" } },
        );
      }
      return proxyControlPlaneRequest(request, "/runs");
    }
    const result = await listWorkspaceRuns(
      request.headers,
      request.nextUrl.searchParams.get("workspace_id"),
      request.nextUrl.searchParams.get("limit"),
      {
        taskId: request.nextUrl.searchParams.get("task_id"),
        agentId: request.nextUrl.searchParams.get("agent_id"),
      },
    );
    return NextResponse.json(result.body, { status: result.status, headers: { "Cache-Control": "no-store", Vary: "Cookie, X-AgentOps-Workspace-Id" } });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, { status: failure.status, headers: { "Cache-Control": "no-store", Vary: "Cookie, X-AgentOps-Workspace-Id" } });
  }
}
