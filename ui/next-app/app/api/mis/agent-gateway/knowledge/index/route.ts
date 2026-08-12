import { NextRequest } from "next/server";

import { indexGovernedKnowledge } from "@/server/controlPlane/agentGatewayEvidenceSupport";
import { ownEvidencePost } from "@/server/controlPlane/evidenceRouteOwner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  return ownEvidencePost(request, {
    upstreamPath: "/agent-gateway/knowledge/index",
    label: "Governed Knowledge index",
    handler: indexGovernedKnowledge,
  });
}
