import { NextRequest } from "next/server";

import { ownEvidenceGet } from "@/server/controlPlane/evidenceRouteOwner";
import { getOperatorLoopSupervision } from "@/server/controlPlane/loopSupervision";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return ownEvidenceGet(request, {
    upstreamPath: "/operator/loop-supervision",
    handler: getOperatorLoopSupervision,
  });
}
