import { NextRequest } from "next/server";

import { ownHumanAgentDetailGet } from "@/server/controlPlane/humanAgentDetail";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ agentId: string }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { agentId } = await context.params;
  return ownHumanAgentDetailGet(request, agentId);
}
