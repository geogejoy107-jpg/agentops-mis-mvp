import { NextRequest } from "next/server";

import { proposeAgentMemory } from "@/server/controlPlane/agentGatewayEvidenceSupport";
import { ownEvidencePost } from "@/server/controlPlane/evidenceRouteOwner";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  return ownEvidencePost(request, {
    upstreamPath: "/agent-gateway/memories/propose",
    label: "Agent Memory proposal",
    handler: proposeAgentMemory,
  });
}
