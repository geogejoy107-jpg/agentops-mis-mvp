import { NextRequest, NextResponse } from "next/server";

import { controlPlaneMode, isProductionDeployment } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";
import { assertStrictReadQuery, listWorkspaceToolCalls } from "@/server/controlPlane/workspaceReadModels";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, X-AgentOps-Workspace-Id",
};

async function freeLocalProxy(request: NextRequest) {
  const response = await proxyControlPlaneRequest(request, "/tool-calls");
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Vary", PRIVATE_HEADERS.Vary);
  return response;
}

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      if (isProductionDeployment()) {
        return NextResponse.json(
          {
            ok: false,
            error: "typescript_route_owner_required",
            message: "Production tool-call reads require the TypeScript Postgres route.",
            token_omitted: true,
          },
          { status: 503, headers: PRIVATE_HEADERS },
        );
      }
      return freeLocalProxy(request);
    }
    assertStrictReadQuery(request.nextUrl.searchParams, ["run_id", "agent_id", "risk_level", "status"]);
    const result = await listWorkspaceToolCalls(
      request.headers,
      request.nextUrl.searchParams.get("workspace_id"),
      request.nextUrl.searchParams.get("limit"),
      {
        runId: request.nextUrl.searchParams.get("run_id"),
        agentId: request.nextUrl.searchParams.get("agent_id"),
        riskLevel: request.nextUrl.searchParams.get("risk_level"),
        status: request.nextUrl.searchParams.get("status"),
      },
    );
    return NextResponse.json(result.body, {
      status: result.status,
      headers: PRIVATE_HEADERS,
    });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: PRIVATE_HEADERS,
    });
  }
}
