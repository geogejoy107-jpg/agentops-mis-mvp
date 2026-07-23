import { NextRequest } from "next/server";

import { ownHumanReadGet } from "@/server/controlPlane/humanReadRoute";
import { listWorkspaceRuns } from "@/server/controlPlane/workspaceTaskRunReads";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return ownHumanReadGet(request, {
    upstreamPath: "/runs",
    handler: (ownedRequest) => {
      const searchParams = new URL(ownedRequest.url).searchParams;
      return listWorkspaceRuns(
        ownedRequest.headers,
        searchParams.get("workspace_id"),
        searchParams.getAll("status"),
        searchParams.get("limit"),
        searchParams.get("task_id"),
        searchParams.get("agent_id"),
        searchParams.get("offset"),
      );
    },
  });
}
