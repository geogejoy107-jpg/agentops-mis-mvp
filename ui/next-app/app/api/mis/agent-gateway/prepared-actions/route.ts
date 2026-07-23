import { NextRequest, NextResponse } from "next/server";

import {
  parseBoundedJsonObject,
  readBoundedBody,
} from "@/server/controlPlane/boundedJson";
import {
  controlPlaneMode,
  legacyPythonProxyAllowed,
} from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import { preparePreparedAction } from "@/server/controlPlane/preparedActions";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Authorization, X-AgentOps-Workspace-Id, X-AgentOps-Agent-Id, Idempotency-Key",
};

export async function POST(request: NextRequest) {
  try {
    const options = {
      maxBytes: 16 * 1024,
      label: "PreparedAction prepare",
    };
    const rawBody = await readBoundedBody(request, options);
    if (controlPlaneMode() === "proxy") {
      if (!legacyPythonProxyAllowed()) {
        return NextResponse.json(
          {
            ok: false,
            error: "prepared_action_postgres_owner_required",
            message:
              "Production PreparedAction authoring requires the TypeScript Postgres owner.",
            python_proxy_performed: false,
            token_omitted: true,
          },
          { status: 503, headers: PRIVATE_HEADERS },
        );
      }
      const proxied = await proxyControlPlaneRequest(
        request,
        "/agent-gateway/prepared-actions",
        rawBody,
      );
      proxied.headers.set("Cache-Control", PRIVATE_HEADERS["Cache-Control"]);
      proxied.headers.set("Vary", PRIVATE_HEADERS.Vary);
      return proxied;
    }
    const body = parseBoundedJsonObject(rawBody, options);
    const result = await preparePreparedAction(request, body);
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
