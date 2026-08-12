import { NextRequest, NextResponse } from "next/server";

import {
  CUSTOMER_DELIVERY_APPROVAL_MAX_BODY_BYTES,
  requestCustomerDeliveryApproval,
} from "@/server/controlPlane/agentGatewayApprovals";
import {
  parseBoundedJsonObject,
  readBoundedBody,
} from "@/server/controlPlane/boundedJson";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { ControlPlaneHttpError, errorPayload } from "@/server/controlPlane/http";
import { proxyControlPlaneRequest } from "@/server/controlPlane/proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function explicitFreeLocalProxyMode() {
  return String(process.env.AGENTOPS_DEPLOYMENT_MODE || "").trim().toLowerCase()
      === "free_local"
    && String(
      process.env.AGENTOPS_CONTROL_PLANE_MODE
      || process.env.AGENTOPS_TS_CONTROL_PLANE_MODE
      || "",
    ).trim().toLowerCase() === "proxy";
}

export async function POST(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      const options = {
        maxBytes: CUSTOMER_DELIVERY_APPROVAL_MAX_BODY_BYTES,
        label: "Customer-delivery approval request",
      };
      const body = await readBoundedBody(request, options);
      parseBoundedJsonObject(body, options);
      if (!explicitFreeLocalProxyMode()) {
        throw new ControlPlaneHttpError(
          503,
          "customer_delivery_approval_proxy_mode_required",
          "Python proxying requires explicit free_local deployment and proxy modes.",
        );
      }
      return proxyControlPlaneRequest(
        request,
        "/agent-gateway/approvals/request",
        body,
      );
    }
    const result = await requestCustomerDeliveryApproval(request);
    return NextResponse.json(result.body, {
      status: result.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: { "Cache-Control": "no-store" },
    });
  }
}
