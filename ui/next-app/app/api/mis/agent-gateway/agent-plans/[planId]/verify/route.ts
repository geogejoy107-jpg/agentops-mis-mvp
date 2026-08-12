import { NextRequest, NextResponse } from "next/server";

import { getAgentGatewayPlan } from "@/server/controlPlane/agentGatewayPlans";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyFreeLocalRead } from "@/server/controlPlane/agentGatewayRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ planId: string }> },
) {
  try {
    const { planId } = await context.params;
    if (controlPlaneMode() === "proxy") {
      return await proxyFreeLocalRead(
        request,
        `/agent-gateway/agent-plans/${encodeURIComponent(planId)}/verify`,
      );
    }
    return NextResponse.json(
      await getAgentGatewayPlan(request, planId, true),
      { status: 200, headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: { "Cache-Control": "no-store" },
    });
  }
}
