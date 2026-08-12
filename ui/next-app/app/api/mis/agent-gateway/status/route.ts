import { NextRequest, NextResponse } from "next/server";

import { controlPlaneMode } from "@/server/controlPlane/config";
import { getGatewayStatus } from "@/server/controlPlane/gatewayLifecycle";
import { proxyFreeLocalRead } from "@/server/controlPlane/agentGatewayRoute";
import { errorPayload } from "@/server/controlPlane/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      return proxyFreeLocalRead(request, "/agent-gateway/status");
    }
    const result = await getGatewayStatus(request);
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
