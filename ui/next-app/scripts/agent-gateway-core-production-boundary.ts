import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const routeFiles = [
  "app/api/mis/agent-gateway/tasks/pull/route.ts",
  "app/api/mis/agent-gateway/tasks/[taskId]/route.ts",
  "app/api/mis/agent-gateway/tasks/[taskId]/claim/route.ts",
  "app/api/mis/agent-gateway/agent-plans/route.ts",
  "app/api/mis/agent-gateway/agent-plans/[planId]/verify/route.ts",
  "app/api/mis/agent-gateway/runs/start/route.ts",
  "app/api/mis/agent-gateway/runs/[runId]/heartbeat/route.ts",
  "app/api/mis/agent-gateway/tool-calls/route.ts",
  "app/api/mis/agent-gateway/evaluations/submit/route.ts",
  "app/api/mis/agent-gateway/artifacts/route.ts",
  "app/api/mis/agent-gateway/plan-evidence-manifests/route.ts",
];
const ownerFiles = [
  "src/server/controlPlane/agentGatewayTasks.ts",
  "src/server/controlPlane/agentGatewayPlans.ts",
  "src/server/controlPlane/agentGatewayRuns.ts",
  "src/server/controlPlane/agentGatewayEvidence.ts",
];

for (const path of routeFiles) {
  const source = await readFile(new URL(`../${path}`, import.meta.url), "utf8");
  assert.match(source, /controlPlaneMode\(\) === "proxy"/);
  assert.match(source, /proxyFreeLocal(Read|Mutation)/);
  assert.doesNotMatch(source, /proxyControlPlaneRequest/);
  assert.doesNotMatch(
    source,
    /child_process|spawn\(|exec\(|\bpython(?:3)?\b|server\.py/i,
  );
}

for (const path of ownerFiles) {
  const source = await readFile(new URL(`../${path}`, import.meta.url), "utf8");
  assert.match(source, /boundedJsonObject|export async function (get|pull)/);
  assert.doesNotMatch(source, /request\.json\(\)/);
  assert.doesNotMatch(source, /AGENTOPS_API_BASE|proxyControlPlaneRequest/);
  assert.doesNotMatch(
    source,
    /child_process|spawn\(|exec\(|\bpython(?:3)?\b|server\.py/i,
  );
}

const proxyBoundary = await readFile(
  new URL("../src/server/controlPlane/agentGatewayRoute.ts", import.meta.url),
  "utf8",
);
assert.match(
  proxyBoundary,
  /AGENTOPS_DEPLOYMENT_MODE[\s\S]*=== "free_local"/,
);
assert.match(
  proxyBoundary,
  /AGENTOPS_CONTROL_PLANE_MODE[\s\S]*=== "proxy"/,
);
assert.match(proxyBoundary, /readBoundedBody/);

console.log(JSON.stringify({
  contract: "agent_gateway_core_production_boundary_v1",
  ok: true,
  specific_route_count: routeFiles.length,
  production_python_process_start: false,
  production_python_proxy: false,
  free_local_proxy_explicit: true,
  bounded_owner_body: true,
}));
