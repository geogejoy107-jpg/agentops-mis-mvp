import { NextRequest } from "next/server";

import { ownHumanReadGet } from "@/server/controlPlane/humanReadRoute";
import { listWorkspaceTasks } from "@/server/controlPlane/workspaceTaskRunReads";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return ownHumanReadGet(request, {
    upstreamPath: "/tasks",
    handler: (ownedRequest) => {
      const searchParams = new URL(ownedRequest.url).searchParams;
      return listWorkspaceTasks(
        ownedRequest.headers,
        searchParams.get("workspace_id"),
        searchParams.getAll("status"),
        searchParams.get("limit"),
      );
    },
  });
}
