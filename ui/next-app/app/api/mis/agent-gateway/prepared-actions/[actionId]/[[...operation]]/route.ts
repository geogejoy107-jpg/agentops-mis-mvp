import { NextRequest, NextResponse } from "next/server";

import { controlPlaneMode } from "@/server/controlPlane/config";
import { ControlPlaneHttpError, errorPayload } from "@/server/controlPlane/http";
import {
  claimPreparedActionExecution,
  failPreparedActionExecution,
  getPreparedAction,
  resumePreparedActionExecution,
} from "@/server/controlPlane/preparedActions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ actionId: string; operation?: string[] }>;
};

function requirePostgresOwner() {
  if (controlPlaneMode() !== "postgres") {
    throw new ControlPlaneHttpError(
      503,
      "prepared_action_postgres_owner_required",
      "PreparedAction production routes require the TypeScript Postgres owner.",
    );
  }
}

function response(result: {
  status: number;
  body: Record<string, unknown>;
}) {
  return NextResponse.json(result.body, {
    status: result.status,
    headers: { "Cache-Control": "no-store" },
  });
}

function failure(error: unknown) {
  const result = errorPayload(error);
  return NextResponse.json(result.body, {
    status: result.status,
    headers: { "Cache-Control": "no-store" },
  });
}

export async function GET(request: NextRequest, context: RouteContext) {
  try {
    requirePostgresOwner();
    const { actionId, operation = [] } = await context.params;
    if (operation.length) {
      throw new ControlPlaneHttpError(
        404,
        "prepared_action_route_not_found",
        "PreparedAction GET route was not found.",
      );
    }
    return response(await getPreparedAction(request, actionId));
  } catch (error) {
    return failure(error);
  }
}

export async function POST(request: NextRequest, context: RouteContext) {
  try {
    requirePostgresOwner();
    const { actionId, operation = [] } = await context.params;
    if (operation.length !== 1) {
      throw new ControlPlaneHttpError(
        404,
        "prepared_action_route_not_found",
        "PreparedAction mutation route was not found.",
      );
    }
    if (operation[0] === "claim-execution") {
      return response(await claimPreparedActionExecution(request, actionId));
    }
    if (operation[0] === "fail-execution") {
      return response(await failPreparedActionExecution(request, actionId));
    }
    if (operation[0] === "resume") {
      return response(await resumePreparedActionExecution(request, actionId));
    }
    throw new ControlPlaneHttpError(
      404,
      "prepared_action_route_not_found",
      "PreparedAction mutation route was not found.",
    );
  } catch (error) {
    return failure(error);
  }
}
