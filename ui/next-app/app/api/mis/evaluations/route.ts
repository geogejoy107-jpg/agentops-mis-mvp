import { NextRequest } from "next/server";

import { listHumanEvaluations } from "@/server/controlPlane/humanReadModels";
import { ownHumanReadGet } from "@/server/controlPlane/humanReadRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return ownHumanReadGet(request, {
    upstreamPath: "/evaluations",
    handler: listHumanEvaluations,
  });
}
