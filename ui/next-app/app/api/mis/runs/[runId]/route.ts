import { NextRequest } from "next/server";

import { ownHumanReadGet } from "@/server/controlPlane/humanReadRoute";
import { readWorkspaceRunDetail } from "@/server/controlPlane/workspaceTaskRunReads";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ runId: string }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { runId } = await context.params;
  return ownHumanReadGet(request, {
    upstreamPath: `/runs/${encodeURIComponent(runId)}`,
    handler: (ownedRequest) =>
      readWorkspaceRunDetail(
        ownedRequest.headers,
        new URL(ownedRequest.url).searchParams.get("workspace_id"),
        runId,
      ),
  });
}
