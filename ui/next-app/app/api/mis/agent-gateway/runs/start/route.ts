import { NextRequest, NextResponse } from "next/server";

import {
  RUN_WRITE_MAX_BODY_BYTES,
  startAgentGatewayRun,
} from "@/server/controlPlane/agentGatewayRuns";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyFreeLocalMutation } from "@/server/controlPlane/agentGatewayRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      return await proxyFreeLocalMutation(
        request,
        "/agent-gateway/runs/start",
        { maxBytes: RUN_WRITE_MAX_BODY_BYTES, label: "Run start" },
      );
    }
    const result = await startAgentGatewayRun(request);
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
