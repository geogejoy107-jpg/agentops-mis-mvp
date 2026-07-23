import { NextRequest, NextResponse } from "next/server";

import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { readWorkspaceTaskDetail } from "@/server/controlPlane/workspaceTaskRunReads";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ taskId: string }> };

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, X-AgentOps-Workspace-Id",
};

export async function GET(request: NextRequest, context: RouteContext) {
  try {
    if (controlPlaneMode() !== "postgres") {
      return NextResponse.json(
        {
          ok: false,
          error: "human_session_direct_route_required",
          message: "Task detail reads require TypeScript Postgres Human Session authority.",
          python_proxy_performed: false,
          provider_call_performed: false,
          token_omitted: true,
        },
        { status: 503, headers: PRIVATE_HEADERS },
      );
    }
    const { taskId } = await context.params;
    const result = await readWorkspaceTaskDetail(
      request.headers,
      request.nextUrl.searchParams.get("workspace_id"),
      taskId,
    );
    return NextResponse.json(result.body, {
      status: result.status,
      headers: PRIVATE_HEADERS,
    });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: PRIVATE_HEADERS,
    });
  }
}
