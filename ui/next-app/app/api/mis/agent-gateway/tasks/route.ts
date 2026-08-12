import { NextRequest, NextResponse } from "next/server";

import {
  createAgentGatewayTask,
  listAgentGatewayTasks,
  TASK_WRITE_MAX_BODY_BYTES,
} from "@/server/controlPlane/agentGatewayTasks";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { errorPayload } from "@/server/controlPlane/http";
import {
  proxyFreeLocalMutation,
  proxyFreeLocalRead,
} from "@/server/controlPlane/agentGatewayRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Authorization, X-AgentOps-Workspace-Id, X-AgentOps-Agent-Id, Idempotency-Key",
};

export async function GET(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      return proxyFreeLocalRead(request, "/agent-gateway/tasks");
    }
    return NextResponse.json(await listAgentGatewayTasks(request), {
      status: 200,
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

export async function POST(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      return proxyFreeLocalMutation(request, "/agent-gateway/tasks", {
        maxBytes: TASK_WRITE_MAX_BODY_BYTES,
        label: "Task write",
      });
    }
    const result = await createAgentGatewayTask(request);
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
