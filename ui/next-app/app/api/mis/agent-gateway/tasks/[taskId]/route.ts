import { NextRequest, NextResponse } from "next/server";

import { getAgentGatewayTask } from "@/server/controlPlane/agentGatewayTasks";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyFreeLocalRead } from "@/server/controlPlane/agentGatewayRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ taskId: string }> },
) {
  try {
    const { taskId } = await context.params;
    if (controlPlaneMode() === "proxy") {
      return await proxyFreeLocalRead(
        request,
        `/agent-gateway/tasks/${encodeURIComponent(taskId)}`,
      );
    }
    return NextResponse.json(await getAgentGatewayTask(request, taskId), {
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
