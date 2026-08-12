import { NextRequest, NextResponse } from "next/server";

import { parseBoundedJsonObject, readBoundedBody } from "@/server/controlPlane/boundedJson";
import {
  controlPlaneMode,
  legacyPythonProxyAllowed,
} from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import {
  reviewWorkspaceMemory,
  validateMemoryReviewBody,
  validateMemoryReviewPath,
  validateMemoryReviewQuery,
} from "@/server/controlPlane/memoryReviews";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ memoryId: string; decision: string }>;
};

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, Origin, X-AgentOps-Workspace-Id, X-AgentOps-CSRF, Idempotency-Key",
};

function pythonProxyExplicitlyConfigured() {
  return String(
    process.env.AGENTOPS_CONTROL_PLANE_MODE
      || process.env.AGENTOPS_TS_CONTROL_PLANE_MODE
      || "",
  ).trim().toLowerCase() === "proxy";
}

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    const bodyOptions = {
      maxBytes: 8 * 1024,
      allowEmpty: true,
      label: "Memory review",
    };
    const rawBody = await readBoundedBody(request, bodyOptions);
    const body = parseBoundedJsonObject(rawBody, bodyOptions);
    const { memoryId, decision } = await context.params;
    validateMemoryReviewPath(memoryId, decision);
    validateMemoryReviewQuery(request.url);
    validateMemoryReviewBody(body);
    if (pythonProxyExplicitlyConfigured() || controlPlaneMode() === "proxy") {
      if (!legacyPythonProxyAllowed()) {
        return NextResponse.json(
          {
            ok: false,
            error: "human_session_direct_route_required",
            message: "Production Memory Review requires the TypeScript Postgres Human Session route.",
            python_proxy_performed: false,
            token_omitted: true,
          },
          { status: 503, headers: PRIVATE_HEADERS },
        );
      }
      const proxied = await proxyControlPlaneRequest(
        request,
        `/memories/${encodeURIComponent(memoryId)}/${encodeURIComponent(decision)}`,
        rawBody,
      );
      proxied.headers.set("Cache-Control", PRIVATE_HEADERS["Cache-Control"]);
      proxied.headers.set("Vary", PRIVATE_HEADERS.Vary);
      return proxied;
    }
    const result = await reviewWorkspaceMemory(request, body, memoryId, decision);
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
