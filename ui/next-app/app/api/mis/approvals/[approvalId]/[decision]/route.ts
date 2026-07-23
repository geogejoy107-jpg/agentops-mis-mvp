import { NextRequest, NextResponse } from "next/server";

import { decideWorkspaceApproval } from "@/server/controlPlane/approvalDecisions";
import { parseBoundedJsonObject, readBoundedBody } from "@/server/controlPlane/boundedJson";
import { controlPlaneMode, isProductionDeployment } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ approvalId: string; decision: string }>;
};

const RESPONSE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, X-AgentOps-Workspace-Id, X-AgentOps-CSRF, Idempotency-Key",
};

function boundedFailureCode(error: unknown) {
  const record = error && typeof error === "object"
    ? error as { code?: unknown; message?: unknown }
    : {};
  for (const value of [record.code, record.message]) {
    if (typeof value === "string" && /^[A-Za-z0-9_]{2,64}$/.test(value)) return value;
  }
  return "unclassified";
}

async function freeLocalProxy(request: NextRequest, path: string, rawBody: Buffer) {
  const response = await proxyControlPlaneRequest(request, path, rawBody);
  response.headers.set("Cache-Control", RESPONSE_HEADERS["Cache-Control"]);
  response.headers.set("Vary", RESPONSE_HEADERS.Vary);
  return response;
}

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    const { approvalId, decision } = await context.params;
    if (decision !== "approve" && decision !== "reject") {
      return NextResponse.json(
        { ok: false, error: "approval_decision_not_found", message: "Approval decision route was not found.", token_omitted: true },
        { status: 404, headers: RESPONSE_HEADERS },
      );
    }
    const bodyOptions = { maxBytes: 8 * 1024, allowEmpty: true, label: "Approval decision" };
    const rawBody = await readBoundedBody(request, bodyOptions);
    const body = parseBoundedJsonObject(rawBody, bodyOptions);
    if (controlPlaneMode() === "proxy") {
      if (isProductionDeployment()) {
        return NextResponse.json(
          {
            ok: false,
            error: "human_session_direct_route_required",
            message: "Production approval decisions require the TypeScript Postgres Human Session route.",
            token_omitted: true,
          },
          { status: 503, headers: RESPONSE_HEADERS },
        );
      }
      return freeLocalProxy(
        request,
        `/approvals/${encodeURIComponent(approvalId)}/${decision}`,
        rawBody,
      );
    }
    const result = await decideWorkspaceApproval(request, body, approvalId, decision);
    return NextResponse.json(result.body, { status: result.status, headers: RESPONSE_HEADERS });
  } catch (error) {
    const failure = errorPayload(error);
    if (failure.status === 503 && failure.body.error === "typescript_control_plane_unavailable") {
      console.error(JSON.stringify({
        event: "agentops.approval_decision_unavailable",
        failure_code: boundedFailureCode(error),
        credentials_omitted: true,
        raw_body_omitted: true,
      }));
    }
    return NextResponse.json(failure.body, { status: failure.status, headers: RESPONSE_HEADERS });
  }
}
