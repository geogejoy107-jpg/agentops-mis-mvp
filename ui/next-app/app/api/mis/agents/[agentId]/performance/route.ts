import { NextRequest } from "next/server";

import { readHumanAgentPerformance } from "@/server/controlPlane/humanReadModels";
import { ownHumanReadGet } from "@/server/controlPlane/humanReadRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ agentId: string }>;
};

export async function GET(request: NextRequest, context: RouteContext) {
  const { agentId } = await context.params;
  return ownHumanReadGet(request, {
    upstreamPath: `/agents/${encodeURIComponent(agentId)}/performance`,
    handler: (ownedRequest) =>
      readHumanAgentPerformance(ownedRequest, agentId),
  });
}
