import { NextRequest, NextResponse } from "next/server";

import { readAgentGatewayRun } from "@/server/controlPlane/agentGatewayReadModels";
import { proxyFreeLocalRead } from "@/server/controlPlane/agentGatewayRoute";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ runId: string }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  try {
    const { runId } = await context.params;
    if (controlPlaneMode() === "proxy") {
      return proxyFreeLocalRead(
        request,
        `/agent-gateway/runs/${encodeURIComponent(runId)}`,
      );
    }
    const result = await readAgentGatewayRun(request, runId);
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
