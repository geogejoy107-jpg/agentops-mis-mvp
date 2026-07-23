import { NextRequest, NextResponse } from "next/server";

import { proxyFreeLocalMutation } from "@/server/controlPlane/agentGatewayRoute";
import { controlPlaneMode } from "@/server/controlPlane/config";
import {
  GATEWAY_LIFECYCLE_MAX_BODY_BYTES,
  recordGatewayHeartbeat,
} from "@/server/controlPlane/gatewayLifecycle";
import { errorPayload } from "@/server/controlPlane/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      return proxyFreeLocalMutation(request, "/agent-gateway/heartbeat", {
        maxBytes: GATEWAY_LIFECYCLE_MAX_BODY_BYTES,
        label: "Gateway heartbeat",
      });
    }
    const result = await recordGatewayHeartbeat(request);
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
