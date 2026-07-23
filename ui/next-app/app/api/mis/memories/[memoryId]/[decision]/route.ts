import { NextRequest, NextResponse } from "next/server";

import { parseBoundedJsonObject, readBoundedBody } from "@/server/controlPlane/boundedJson";
import { controlPlaneMode, isProductionDeployment } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { reviewWorkspaceMemory } from "@/server/controlPlane/memoryReviews";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ memoryId: string; decision: string }>;
};

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    const bodyOptions = { maxBytes: 8 * 1024, allowEmpty: true, label: "Memory review" };
    const rawBody = await readBoundedBody(request, bodyOptions);
    const body = parseBoundedJsonObject(rawBody, bodyOptions);
    const { memoryId, decision } = await context.params;
    if (controlPlaneMode() === "proxy") {
      if (isProductionDeployment()) {
        return NextResponse.json(
          { ok: false, error: "human_session_direct_route_required", message: "Production Memory Review requires the TypeScript Postgres Human Session route.", token_omitted: true },
          { status: 409, headers: { "Cache-Control": "no-store" } },
        );
      }
      return await proxyControlPlaneRequest(
        request,
        `/memories/${encodeURIComponent(memoryId)}/${encodeURIComponent(decision)}`,
        rawBody,
      );
    }
    const result = await reviewWorkspaceMemory(request, body, memoryId, decision);
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
