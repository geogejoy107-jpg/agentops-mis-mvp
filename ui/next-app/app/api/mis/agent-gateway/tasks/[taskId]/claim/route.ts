import { NextRequest, NextResponse } from "next/server";

import {
  claimAgentGatewayTask,
  TASK_CLAIM_MAX_BODY_BYTES,
} from "@/server/controlPlane/agentGatewayTasks";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyFreeLocalMutation } from "@/server/controlPlane/agentGatewayRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ taskId: string }> },
) {
  try {
    const { taskId } = await context.params;
    if (controlPlaneMode() === "proxy") {
      return await proxyFreeLocalMutation(
        request,
        `/agent-gateway/tasks/${encodeURIComponent(taskId)}/claim`,
        { maxBytes: TASK_CLAIM_MAX_BODY_BYTES, label: "Task claim" },
      );
    }
    const result = await claimAgentGatewayTask(request, taskId);
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
