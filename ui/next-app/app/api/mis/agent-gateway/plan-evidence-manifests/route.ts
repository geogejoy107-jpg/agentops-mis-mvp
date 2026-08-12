import { NextRequest, NextResponse } from "next/server";

import {
  AGENT_PLAN_MAX_BODY_BYTES,
  createAgentGatewayPlanEvidenceManifest,
} from "@/server/controlPlane/agentGatewayPlans";
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
        "/agent-gateway/plan-evidence-manifests",
        { maxBytes: AGENT_PLAN_MAX_BODY_BYTES, label: "Plan evidence manifest" },
      );
    }
    const result = await createAgentGatewayPlanEvidenceManifest(request);
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
