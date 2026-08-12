import type { NextRequest } from "next/server";

import {
  parseBoundedJsonObject,
  readBoundedBody,
} from "./boundedJson";
import { ControlPlaneHttpError } from "./http";
import { proxyControlPlaneRequest } from "./proxy";

export function explicitFreeLocalProxyMode() {
  return String(process.env.AGENTOPS_DEPLOYMENT_MODE || "").trim().toLowerCase()
      === "free_local"
    && String(
      process.env.AGENTOPS_CONTROL_PLANE_MODE
      || process.env.AGENTOPS_TS_CONTROL_PLANE_MODE
      || "",
    ).trim().toLowerCase() === "proxy";
}

export function proxyFreeLocalRead(
  request: NextRequest,
  upstreamPath: string,
) {
  if (!explicitFreeLocalProxyMode()) {
    throw new ControlPlaneHttpError(
      503,
      "agent_gateway_proxy_mode_required",
      "Python proxying requires explicit free_local deployment and proxy modes.",
    );
  }
  return proxyControlPlaneRequest(request, upstreamPath);
}

export async function proxyFreeLocalMutation(
  request: NextRequest,
  upstreamPath: string,
  options: { maxBytes: number; label: string },
) {
  const body = await readBoundedBody(request, options);
  parseBoundedJsonObject(body, options);
  if (!explicitFreeLocalProxyMode()) {
    throw new ControlPlaneHttpError(
      503,
      "agent_gateway_proxy_mode_required",
      "Python proxying requires explicit free_local deployment and proxy modes.",
    );
  }
  return proxyControlPlaneRequest(request, upstreamPath, body);
}
