import { NextRequest } from "next/server";

import { getHumanWorkerFleetRead } from "@/server/controlPlane/humanWorkerFleetReads";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return getHumanWorkerFleetRead(request, "status");
}
