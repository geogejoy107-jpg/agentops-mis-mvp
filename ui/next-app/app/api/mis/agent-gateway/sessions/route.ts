import { NextRequest, NextResponse } from "next/server";

import { proxyFreeLocalRead } from "@/server/controlPlane/agentGatewayRoute";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { listGatewaySessions } from "@/server/controlPlane/gatewayAdministration";
import { errorPayload } from "@/server/controlPlane/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, X-AgentOps-Workspace-Id",
};

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      return proxyFreeLocalRead(request, "/agent-gateway/sessions");
    }
    const result = await listGatewaySessions(request);
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
