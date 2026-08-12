import { NextRequest, NextResponse } from "next/server";

import {
  controlPlaneMode,
  legacyPythonProxyAllowed,
} from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { exportWorkspaceMemories } from "@/server/controlPlane/memoryCandidates";
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
            message: "Production Memory exports require TypeScript PostgreSQL Human Session authority.",
            python_proxy_performed: false,
            token_omitted: true,
          },
          { status: 503, headers: PRIVATE_HEADERS },
        );
      }
      const proxied = await proxyControlPlaneRequest(request, "/memories/export");
      proxied.headers.set("Cache-Control", PRIVATE_HEADERS["Cache-Control"]);
      proxied.headers.set("Vary", PRIVATE_HEADERS.Vary);
      return proxied;
    }
    const keys = [...new Set(request.nextUrl.searchParams.keys())];
    if (keys.some((key) => !["workspace_id", "review_status", "limit"].includes(key))) {
      return NextResponse.json(
        {
          ok: false,
          error: "human_memory_query_unsupported",
          message: "Memory exports received an unsupported query parameter.",
          token_omitted: true,
        },
        { status: 400, headers: PRIVATE_HEADERS },
      );
    }
    for (const key of ["workspace_id", "review_status", "limit"]) {
      if (request.nextUrl.searchParams.getAll(key).length > 1) {
        return NextResponse.json(
          {
            ok: false,
            error: "human_memory_query_ambiguous",
            message: "Memory export query parameters must have one value.",
            token_omitted: true,
          },
          { status: 400, headers: PRIVATE_HEADERS },
        );
      }
    }
    const result = await exportWorkspaceMemories(
      request.headers,
      request.nextUrl.searchParams.get("workspace_id"),
      request.nextUrl.searchParams.get("review_status"),
      request.nextUrl.searchParams.get("limit"),
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
