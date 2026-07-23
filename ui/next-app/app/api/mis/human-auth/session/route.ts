import { NextRequest, NextResponse } from "next/server";

import { controlPlaneMode } from "@/server/controlPlane/config";
import { humanSessionStatus } from "@/server/controlPlane/humanSession";
import { errorPayload } from "@/server/controlPlane/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = { "Cache-Control": "no-store", Vary: "Cookie" };

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() !== "postgres") {
      return NextResponse.json(
        {
          ok: false,
          error: "human_session_postgres_required",
          message: "Human Session validation requires the TypeScript Postgres control plane.",
          token_omitted: true,
        },
        { status: 409, headers: PRIVATE_HEADERS },
      );
    }
    const result = await humanSessionStatus(request.headers);
    return NextResponse.json(result.body, {
      status: result.status,
      headers: PRIVATE_HEADERS,
    });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: PRIVATE_HEADERS,
    });
  }
}
