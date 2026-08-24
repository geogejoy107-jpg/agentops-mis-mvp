import { NextRequest, NextResponse } from "next/server";

import { listWorkspaceApprovals } from "@/server/controlPlane/approvalQueue";
import { strictApprovalReadQuery } from "@/server/controlPlane/approvalReadBoundary";
import {
  controlPlaneMode,
  legacyPythonProxyAllowed,
} from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, X-AgentOps-Workspace-Id",
};

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      if (!legacyPythonProxyAllowed()) {
        return NextResponse.json(
          {
            ok: false,
            error: "human_session_direct_route_required",
            message: "Production approval queues require TypeScript Postgres Human Session authority.",
            python_proxy_performed: false,
            token_omitted: true,
          },
          { status: 503, headers: PRIVATE_HEADERS },
        );
      }
      const proxied = await proxyControlPlaneRequest(request, "/approvals");
      proxied.headers.set("Cache-Control", PRIVATE_HEADERS["Cache-Control"]);
      proxied.headers.set("Vary", PRIVATE_HEADERS.Vary);
      return proxied;
    }
    const query = strictApprovalReadQuery(request, [
      "workspace_id",
      "decision",
      "limit",
    ]);
    const result = await listWorkspaceApprovals(
      request.headers,
      query.workspace_id,
      query.decision,
      query.limit,
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
