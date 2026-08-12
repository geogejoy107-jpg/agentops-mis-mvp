import { NextRequest } from "next/server";

import { ownHumanTaskOperation } from "@/server/controlPlane/humanTaskOperations";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ taskId: string }> };

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { taskId } = await context.params;
  return ownHumanTaskOperation(request, { operation: "status", taskId });
}
