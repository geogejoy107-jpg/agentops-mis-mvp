import { NextRequest } from "next/server";

import { ownHumanReadGet } from "@/server/controlPlane/humanReadRoute";
import { readWorkspaceTaskDetail } from "@/server/controlPlane/workspaceTaskRunReads";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ taskId: string }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { taskId } = await context.params;
  return ownHumanReadGet(request, {
    upstreamPath: `/tasks/${encodeURIComponent(taskId)}`,
    handler: (ownedRequest) =>
      readWorkspaceTaskDetail(
        ownedRequest.headers,
        new URL(ownedRequest.url).searchParams.get("workspace_id"),
        taskId,
      ),
  });
}
