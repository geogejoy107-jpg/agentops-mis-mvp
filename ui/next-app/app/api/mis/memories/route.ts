import { NextRequest, NextResponse } from "next/server";

import { controlPlaneMode, isProductionDeployment } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { listWorkspaceMemoryCandidates } from "@/server/controlPlane/memoryCandidates";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      if (isProductionDeployment()) {
        return NextResponse.json(
          { ok: false, error: "human_session_direct_route_required", message: "Production Memory Review requires the TypeScript Postgres Human Session route.", token_omitted: true },
          { status: 409, headers: { "Cache-Control": "no-store" } },
        );
      }
      return await proxyControlPlaneRequest(request, "/memories");
    }
    const result = await listWorkspaceMemoryCandidates(
      request.headers,
      request.nextUrl.searchParams.get("workspace_id"),
    );
    return NextResponse.json(result.body, {
      status: result.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: { "Cache-Control": "no-store" },
    });
  }
}
