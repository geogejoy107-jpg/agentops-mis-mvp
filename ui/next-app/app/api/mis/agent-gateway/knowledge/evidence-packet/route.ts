import { NextRequest } from "next/server";

import { getKnowledgeEvidencePacket } from "@/server/controlPlane/agentGatewayEvidenceSupport";
import { ownEvidenceGet } from "@/server/controlPlane/evidenceRouteOwner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return ownEvidenceGet(request, {
    upstreamPath: "/agent-gateway/knowledge/evidence-packet",
    handler: getKnowledgeEvidencePacket,
  });
}
