import { NextRequest, NextResponse } from "next/server";

import { pullAgentGatewayTasks } from "@/server/controlPlane/agentGatewayTasks";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      return await proxyControlPlaneRequest(request, "/agent-gateway/tasks/pull");
    }
    return NextResponse.json(await pullAgentGatewayTasks(request), {
      status: 200,
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
