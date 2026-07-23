import { NextRequest, NextResponse } from "next/server";

import {
  parseBoundedJsonObject,
  readBoundedBody,
} from "./boundedJson";
import { controlPlaneMode, legacyPythonProxyAllowed } from "./config";
import type { EvidenceRouteResult } from "./agentGatewayEvidenceSupport";
import { ControlPlaneHttpError, errorPayload } from "./http";
import { proxyControlPlaneRequest } from "./proxy";

type OwnedHandler = (request: Request) => Promise<EvidenceRouteResult>;

function ownedResponse(result: EvidenceRouteResult) {
  return NextResponse.json(result.body, {
    status: result.status,
    headers: { "Cache-Control": "no-store" },
  });
}

function failureResponse(error: unknown) {
  const failure = errorPayload(error);
  return NextResponse.json(failure.body, {
    status: failure.status,
    headers: { "Cache-Control": "no-store" },
  });
}

export async function ownEvidencePost(
  request: NextRequest,
  options: Readonly<{
    upstreamPath: string;
    label: string;
    handler: OwnedHandler;
    maxBytes?: number;
  }>,
) {
  try {
    if (controlPlaneMode() === "proxy") {
      const bodyOptions = {
        maxBytes: options.maxBytes || 32 * 1024,
        label: options.label,
      };
      const body = await readBoundedBody(request, bodyOptions);
      parseBoundedJsonObject(body, bodyOptions);
      if (!legacyPythonProxyAllowed()) {
        throw new ControlPlaneHttpError(
          503,
          "typescript_route_owner_required",
          "Python proxying is allowed only in explicit Free Local proxy mode.",
        );
      }
      return proxyControlPlaneRequest(request, options.upstreamPath, body);
    }
    return ownedResponse(await options.handler(request));
  } catch (error) {
    return failureResponse(error);
  }
}

export async function ownEvidenceGet(
  request: NextRequest,
  options: Readonly<{
    upstreamPath: string;
    handler: OwnedHandler;
  }>,
) {
  try {
    if (controlPlaneMode() === "proxy") {
      if (!legacyPythonProxyAllowed()) {
        throw new ControlPlaneHttpError(
          503,
          "typescript_route_owner_required",
          "Python proxying is allowed only in explicit Free Local proxy mode.",
        );
      }
      return proxyControlPlaneRequest(request, options.upstreamPath);
    }
    return ownedResponse(await options.handler(request));
  } catch (error) {
    return failureResponse(error);
  }
}
