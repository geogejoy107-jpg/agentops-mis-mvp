import { NextRequest, NextResponse } from "next/server";

import { createAgentGatewayTask, listAgentGatewayTasks } from "@/server/controlPlane/agentGatewayTasks";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") return await proxyControlPlaneRequest(request, "/agent-gateway/tasks");
    return NextResponse.json(await listAgentGatewayTasks(request), {
      status: 200,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, { status: failure.status, headers: { "Cache-Control": "no-store" } });
  }
}

export async function POST(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") return await proxyControlPlaneRequest(request, "/agent-gateway/tasks");
    const result = await createAgentGatewayTask(request);
    return NextResponse.json(result.body, {
      status: result.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, { status: failure.status, headers: { "Cache-Control": "no-store" } });
  }
}
