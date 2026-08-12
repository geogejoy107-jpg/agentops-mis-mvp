import { NextRequest, NextResponse } from "next/server";

import { proxyFreeLocalMutation } from "@/server/controlPlane/agentGatewayRoute";
import { controlPlaneMode } from "@/server/controlPlane/config";
import {
  GATEWAY_ADMIN_MAX_BODY_BYTES,
  rotateGatewayEnrollment,
} from "@/server/controlPlane/gatewayAdministration";
import { errorPayload } from "@/server/controlPlane/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, Origin, X-AgentOps-Workspace-Id, X-AgentOps-CSRF, Idempotency-Key",
};

export async function POST(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      return proxyFreeLocalMutation(request, "/agent-gateway/enrollment/rotate", {
        maxBytes: GATEWAY_ADMIN_MAX_BODY_BYTES,
        label: "Gateway enrollment rotation",
      });
    }
    const result = await rotateGatewayEnrollment(request);
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
