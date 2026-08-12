import { NextRequest, NextResponse } from "next/server";

import { listAgentGatewayRuns } from "@/server/controlPlane/agentGatewayReadModels";
import { proxyFreeLocalRead } from "@/server/controlPlane/agentGatewayRoute";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      return proxyFreeLocalRead(request, "/agent-gateway/runs");
    }
    const result = await listAgentGatewayRuns(request);
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
