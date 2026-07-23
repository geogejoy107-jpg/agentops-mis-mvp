import { NextRequest, NextResponse } from "next/server";

import { boundedJsonObject } from "@/server/controlPlane/boundedJson";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { establishHumanSession } from "@/server/controlPlane/humanSession";
import { errorPayload } from "@/server/controlPlane/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = { "Cache-Control": "no-store", Vary: "Origin" };

export async function POST(request: NextRequest) {
  try {
    const body = await boundedJsonObject(request, {
      maxBytes: 8 * 1024,
      label: "Human login",
    });
    if (controlPlaneMode() !== "postgres") {
      return NextResponse.json(
        {
          ok: false,
          error: "human_session_postgres_required",
          message: "Human Session login requires the TypeScript Postgres control plane.",
          token_omitted: true,
        },
        { status: 409, headers: PRIVATE_HEADERS },
      );
    }
    const result = await establishHumanSession(request.headers, body);
    return NextResponse.json(result.body, {
      status: result.status,
      headers: { ...PRIVATE_HEADERS, "Set-Cookie": result.setCookie },
    });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: PRIVATE_HEADERS,
    });
  }
}
