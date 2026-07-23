import { NextRequest, NextResponse } from "next/server";

import { controlPlaneMode, isProductionDeployment } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";
import { assertStrictReadQuery, getWorkspaceRunDetail } from "@/server/controlPlane/workspaceReadModels";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, X-AgentOps-Workspace-Id",
};

type RouteContext = { params: Promise<{ runId: string }> };

async function freeLocalProxy(request: NextRequest, path: string) {
  const response = await proxyControlPlaneRequest(request, path);
  response.headers.set("Cache-Control", "no-store");
  response.headers.set("Vary", PRIVATE_HEADERS.Vary);
  return response;
}

export async function GET(request: NextRequest, context: RouteContext) {
  try {
    const { runId } = await context.params;
    if (controlPlaneMode() === "proxy") {
      if (isProductionDeployment()) {
        return NextResponse.json(
          {
            ok: false,
            error: "typescript_route_owner_required",
            message: "Production run detail reads require the TypeScript Postgres route.",
            token_omitted: true,
          },
          { status: 503, headers: PRIVATE_HEADERS },
        );
      }
      return freeLocalProxy(request, `/runs/${encodeURIComponent(runId)}`);
    }
    assertStrictReadQuery(request.nextUrl.searchParams, []);
    const result = await getWorkspaceRunDetail(
      request.headers,
      request.nextUrl.searchParams.get("workspace_id"),
      runId,
      request.nextUrl.searchParams.get("limit"),
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
