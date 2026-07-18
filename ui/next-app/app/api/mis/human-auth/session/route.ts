import { NextRequest, NextResponse } from "next/server";

import { controlPlaneMode } from "@/server/controlPlane/config";
import { humanSessionStatus } from "@/server/controlPlane/humanSession";
import { errorPayload } from "@/server/controlPlane/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() !== "postgres") {
      return NextResponse.json(
        { ok: false, error: "human_session_postgres_required", message: "Human Session validation requires the TypeScript Postgres control plane.", token_omitted: true },
        { status: 409, headers: { "Cache-Control": "no-store" } },
      );
    }
    const result = await humanSessionStatus(request.headers);
    return NextResponse.json(result.body, { status: result.status, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, { status: failure.status, headers: { "Cache-Control": "no-store" } });
  }
}
