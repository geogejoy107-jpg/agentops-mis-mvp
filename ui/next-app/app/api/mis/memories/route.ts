import { NextRequest, NextResponse } from "next/server";

import {
  controlPlaneMode,
  legacyPythonProxyAllowed,
} from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { listWorkspaceMemoryCandidates } from "@/server/controlPlane/memoryCandidates";
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
            message: "Production Memory Review requires the TypeScript PostgreSQL Human Session route.",
            python_proxy_performed: false,
            token_omitted: true,
          },
          { status: 503, headers: PRIVATE_HEADERS },
        );
      }
      const proxied = await proxyControlPlaneRequest(request, "/memories");
      proxied.headers.set("Cache-Control", PRIVATE_HEADERS["Cache-Control"]);
      proxied.headers.set("Vary", PRIVATE_HEADERS.Vary);
      return proxied;
    }
    const keys = [...new Set(request.nextUrl.searchParams.keys())];
    if (keys.some((key) => key !== "workspace_id")) {
      return NextResponse.json(
        {
          ok: false,
          error: "human_memory_query_unsupported",
          message: "Memory candidate reads received an unsupported query parameter.",
          token_omitted: true,
        },
        { status: 400, headers: PRIVATE_HEADERS },
      );
    }
    if (request.nextUrl.searchParams.getAll("workspace_id").length > 1) {
      return NextResponse.json(
        {
          ok: false,
          error: "human_memory_query_ambiguous",
          message: "Memory candidate workspace_id must have one value.",
          token_omitted: true,
        },
        { status: 400, headers: PRIVATE_HEADERS },
      );
    }
    const result = await listWorkspaceMemoryCandidates(
      request.headers,
      request.nextUrl.searchParams.get("workspace_id"),
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
