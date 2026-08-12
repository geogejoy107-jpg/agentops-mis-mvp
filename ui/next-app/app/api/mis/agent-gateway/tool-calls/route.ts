import { NextRequest, NextResponse } from "next/server";

import {
  EVIDENCE_MAX_BODY_BYTES,
  recordAgentGatewayToolCall,
} from "@/server/controlPlane/agentGatewayEvidence";
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
        "/agent-gateway/tool-calls",
        { maxBytes: EVIDENCE_MAX_BODY_BYTES, label: "Tool-call evidence" },
      );
    }
    const result = await recordAgentGatewayToolCall(request);
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
