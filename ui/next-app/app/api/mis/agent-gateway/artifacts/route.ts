import { NextRequest, NextResponse } from "next/server";

import {
  EVIDENCE_MAX_BODY_BYTES,
  recordAgentGatewayArtifact,
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
        "/agent-gateway/artifacts",
        { maxBytes: EVIDENCE_MAX_BODY_BYTES, label: "Artifact evidence" },
      );
    }
    const result = await recordAgentGatewayArtifact(request);
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
