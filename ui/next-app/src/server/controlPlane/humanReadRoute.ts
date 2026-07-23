import { NextRequest, NextResponse } from "next/server";

import {
  controlPlaneMode,
  legacyPythonProxyAllowed,
} from "./config";
import { ControlPlaneHttpError, errorPayload } from "./http";
import { proxyControlPlaneRequest } from "./proxy";

export type HumanReadResult = Readonly<{
  status: number;
  body: Record<string, unknown> | Array<Record<string, unknown>>;
}>;

type HumanReadHandler = (request: Request) => Promise<HumanReadResult>;

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, X-AgentOps-Workspace-Id",
};

export async function ownHumanReadGet(
  request: NextRequest,
  options: Readonly<{
    upstreamPath: string;
    handler: HumanReadHandler;
  }>,
) {
  try {
    if (controlPlaneMode() === "proxy") {
      if (!legacyPythonProxyAllowed()) {
        throw new ControlPlaneHttpError(
          503,
          "human_read_route_owner_required",
          "Production Human reads require a TypeScript PostgreSQL owner.",
        );
      }
      const response = await proxyControlPlaneRequest(
        request,
        options.upstreamPath,
      );
      response.headers.set("Cache-Control", PRIVATE_HEADERS["Cache-Control"]);
      response.headers.set("Vary", PRIVATE_HEADERS.Vary);
      return response;
    }
    const result = await options.handler(request);
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
