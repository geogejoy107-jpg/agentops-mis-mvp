import { NextRequest, NextResponse } from "next/server";

import {
  heartbeatAgentGatewayRun,
  RUN_WRITE_MAX_BODY_BYTES,
} from "@/server/controlPlane/agentGatewayRuns";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyFreeLocalMutation } from "@/server/controlPlane/agentGatewayRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ runId: string }> },
) {
  try {
    const { runId } = await context.params;
    if (controlPlaneMode() === "proxy") {
      return await proxyFreeLocalMutation(
        request,
        `/agent-gateway/runs/${encodeURIComponent(runId)}/heartbeat`,
        { maxBytes: RUN_WRITE_MAX_BODY_BYTES, label: "Run heartbeat" },
      );
    }
    const result = await heartbeatAgentGatewayRun(request, runId);
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
