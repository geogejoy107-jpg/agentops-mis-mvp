import { NextRequest } from "next/server";

import { emitAgentAudit } from "@/server/controlPlane/agentGatewayEvidenceSupport";
import { ownEvidencePost } from "@/server/controlPlane/evidenceRouteOwner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  return ownEvidencePost(request, {
    upstreamPath: "/agent-gateway/audit",
    label: "Agent audit",
    handler: emitAgentAudit,
  });
}
