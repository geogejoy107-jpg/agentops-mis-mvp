import { NextRequest } from "next/server";

import { ownHumanReadGet } from "@/server/controlPlane/humanReadRoute";
import { readWorkspaceRunEvidenceGraph } from "@/server/controlPlane/workspaceRunEvidenceGraph";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ runId: string }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { runId } = await context.params;
  return ownHumanReadGet(request, {
    upstreamPath: `/runs/${encodeURIComponent(runId)}/evidence-graph`,
    handler: (ownedRequest) =>
      readWorkspaceRunEvidenceGraph(ownedRequest, runId),
  });
}
