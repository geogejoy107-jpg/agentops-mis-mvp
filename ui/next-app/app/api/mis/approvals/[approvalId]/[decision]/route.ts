import { NextRequest, NextResponse } from "next/server";

import { decideWorkspaceApproval } from "@/server/controlPlane/approvalDecisions";
import {
  parseBoundedJsonObject,
  readBoundedBody,
} from "@/server/controlPlane/boundedJson";
import {
  controlPlaneMode,
  legacyPythonProxyAllowed,
} from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ approvalId: string; decision: string }>;
};

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, Origin, X-AgentOps-Workspace-Id, X-AgentOps-CSRF, Idempotency-Key",
};

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    const { approvalId, decision } = await context.params;
    if (!["approve", "reject"].includes(decision)) {
      return NextResponse.json(
        {
          ok: false,
          error: "approval_decision_not_found",
          message: "Approval decision route was not found.",
          token_omitted: true,
        },
        { status: 404, headers: PRIVATE_HEADERS },
      );
    }
    const options = {
      maxBytes: 8 * 1024,
      allowEmpty: true,
      label: "Approval decision",
    };
    const rawBody = await readBoundedBody(request, options);
    const body = parseBoundedJsonObject(rawBody, options);
    if (controlPlaneMode() === "proxy") {
      if (!legacyPythonProxyAllowed()) {
        return NextResponse.json(
          {
            ok: false,
            error: "human_session_direct_route_required",
            message: "Production approval decisions require TypeScript Postgres Human Session authority.",
            python_proxy_performed: false,
            token_omitted: true,
          },
          { status: 503, headers: PRIVATE_HEADERS },
        );
      }
      const proxied = await proxyControlPlaneRequest(
        request,
        `/approvals/${encodeURIComponent(approvalId)}/${decision}`,
        rawBody,
      );
      proxied.headers.set("Cache-Control", PRIVATE_HEADERS["Cache-Control"]);
      proxied.headers.set("Vary", PRIVATE_HEADERS.Vary);
      return proxied;
    }
    const result = await decideWorkspaceApproval(
      request,
      body,
      approvalId,
      decision,
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
