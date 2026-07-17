import { NextRequest, NextResponse } from "next/server";

import { recordAgentGatewayToolCall } from "@/server/controlPlane/agentGatewayEvidence";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") return await proxyControlPlaneRequest(request, "/agent-gateway/tool-calls");
    const result = await recordAgentGatewayToolCall(request);
    return NextResponse.json(result.body, { status: result.status, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, { status: failure.status, headers: { "Cache-Control": "no-store" } });
  }
}
