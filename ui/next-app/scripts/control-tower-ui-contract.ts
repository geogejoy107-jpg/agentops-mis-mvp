import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { createControlTowerClient } from "../src/client/controlTowerApi";

type RecordedRequest = {
  path: string;
  init?: RequestInit;
};

const requests: RecordedRequest[] = [];
const session = {
  ok: true as const,
  authenticated: true as const,
  user: { user_id: "usr_owner", name: "Workspace Owner" },
  memberships: [{ workspace_id: "ws_commercial", role: "owner" }],
  csrf_token: "a".repeat(64),
  session_expires_at: "2026-08-11T00:00:00.000Z",
  idle_ttl_seconds: 1800,
};

const fetchStub = (async (input: string | URL | Request, init?: RequestInit) => {
  const path = String(input);
  requests.push({ path, init });
  if (path.includes("/dashboard/metrics")) {
    return Response.json({
      workspace_id: "ws_commercial",
      agents_total: 1,
      agents_running: 1,
      tasks_completed_total: 1,
      total_cost_usd: 0.25,
      pending_approvals: 0,
      failure_rate: 0,
      task_status_distribution: [{ status: "completed", count: 1 }],
      control_plane: "typescript_postgres",
    });
  }
  if (path.includes("/agents?")) {
    return Response.json([{
      agent_id: "agt_worker",
      name: "Commercial Worker",
      runtime_type: "hermes",
      status: "idle",
      permission_level: "workspace_write",
    }]);
  }
  if (path === "/api/mis/tasks" && init?.method === "POST") {
    return Response.json({
      ok: true,
      operation: "task_dispatch",
      outcome: "created",
      task_id: "tsk_human_contract",
      workspace_id: "ws_commercial",
      task: {
        task_id: "tsk_human_contract",
        title: "Bounded commercial task",
        status: "planned",
        priority: "high",
        risk_level: "medium",
        owner_agent_id: "agt_worker",
        updated_at: "2026-08-11T00:00:00.000Z",
      },
      token_omitted: true,
    }, { status: 201 });
  }
  if (path.endsWith("/approvals/apr_contract/approve")) {
    return Response.json({
      ok: true,
      operation: "customer_delivery_approval_decision",
      outcome: "updated",
      workspace_id: "ws_commercial",
      approval: {
        approval_id: "apr_contract",
        approval_kind: "customer_delivery",
        task_id: "tsk_contract",
        run_id: "run_contract",
        decision: "approved",
        runtime_type: "hermes",
        requested_by_agent_id: "agt_worker",
        created_at: "2026-08-11T00:00:00.000Z",
        expires_at: null,
        prepared_action: null,
      },
      token_omitted: true,
    });
  }
  if (path.includes("/tasks?")) return Response.json([]);
  if (path.includes("/runs?")) return Response.json([]);
  if (path.includes("/approvals?")) return Response.json([]);
  if (path.endsWith("/logout")) {
    return Response.json({ ok: true, authenticated: false });
  }
  return Response.json(session);
}) as typeof fetch;

async function main() {
  const pageSource = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  const componentSource = await readFile(
    new URL("../src/client/ControlTower.tsx", import.meta.url),
    "utf8",
  );
  const clientSource = await readFile(
    new URL("../src/client/controlTowerApi.ts", import.meta.url),
    "utf8",
  );
  const cssSource = await readFile(
    new URL("../app/control-tower.module.css", import.meta.url),
    "utf8",
  );
  const tasksRouteSource = await readFile(
    new URL("../app/api/mis/tasks/route.ts", import.meta.url),
    "utf8",
  );

  assert.match(pageSource, /<ControlTower\s*\/>/);
  assert.match(componentSource, /Human Session/);
  assert.match(componentSource, /session\.user\.name/);
  assert.match(componentSource, /session\.memberships/);
  assert.match(componentSource, /handleLogout/);
  assert.match(componentSource, /snapshot\?\.metrics\.workspace_id === workspaceId/);
  assert.match(componentSource, /error\.status === 401[\s\S]*clearSession\(\)/);
  assert.match(componentSource, /Workspace ledger/);
  assert.match(componentSource, /handleTaskDispatch/);
  assert.match(componentSource, /handleApprovalDecision/);
  assert.match(componentSource, /创建并派发/);
  assert.match(componentSource, /批准/);
  assert.match(componentSource, /拒绝/);
  assert.doesNotMatch(componentSource, /prepared-actions/);
  assert.match(cssSource, /@media \(max-width: 640px\)/);
  assert.doesNotMatch(cssSource, /linear-gradient|radial-gradient/);
  assert.match(tasksRouteSource, /export async function POST/);
  assert.match(tasksRouteSource, /controlPlaneMode\(\) === "proxy"/);
  assert.match(tasksRouteSource, /authenticateHumanWriteMember/);
  assert.match(tasksRouteSource, /TASK_OPERATOR_ROLES/);
  assert.match(tasksRouteSource, /agent_gateway_tokens/);
  assert.match(tasksRouteSource, /Idempotency-Key/);
  assert.match(tasksRouteSource, /metadata_json::jsonb ->> 'request_hash'/);
  assert.match(tasksRouteSource, /outcome: "unchanged"/);
  assert.match(tasksRouteSource, /appendAudit/);
  assert.match(tasksRouteSource, /appendRuntimeEvent/);
  assert.doesNotMatch(tasksRouteSource, /agentGatewayTasks|createAgentGatewayTask/);

  for (const endpoint of [
    "/api/mis/human-auth/login",
    "/api/mis/human-auth/session",
    "/api/mis/human-auth/logout",
    "/api/mis/dashboard/metrics",
    "/api/mis/agents",
    "/api/mis/tasks",
    "/api/mis/runs",
    "/api/mis/approvals",
  ]) {
    assert.match(clientSource, new RegExp(endpoint.replaceAll("/", "\\/")));
  }

  const client = createControlTowerClient(fetchStub);
  const loggedIn = await client.login("owner", "bounded-password");
  assert.equal(loggedIn.user.user_id, "usr_owner");
  assert.equal((await client.session()).authenticated, true);
  const snapshot = await client.workspaceSnapshot("ws_commercial");
  assert.equal(snapshot.metrics.workspace_id, "ws_commercial");
  assert.deepEqual(snapshot.tasks, []);
  assert.equal(snapshot.agents[0]?.agent_id, "agt_worker");
  const dispatched = await client.dispatchTask(
    "ws_commercial",
    session.csrf_token,
    "human-task-contract-key",
    {
      title: "Bounded commercial task",
      description: "Safe summary only",
      owner_agent_id: "agt_worker",
      priority: "high",
      risk_level: "medium",
      acceptance_criteria: "Write governed evidence",
      budget_limit_usd: 2.5,
    },
  );
  assert.equal(dispatched.task_id, "tsk_human_contract");
  const approval = await client.decideApproval(
    "ws_commercial",
    session.csrf_token,
    "human-approval-contract-key",
    "apr_contract",
    "approve",
  );
  assert.equal(approval.approval.decision, "approved");
  await client.logout(session.csrf_token);

  assert.equal(requests.length, 10);
  assert.ok(
    requests.every((request) => request.init?.credentials === "same-origin"),
  );
  assert.ok(requests.every((request) => request.init?.cache === "no-store"));
  assert.equal(requests[0].init?.method, "POST");
  assert.deepEqual(JSON.parse(String(requests[0].init?.body)), {
    username: "owner",
    password: "bounded-password",
  });
  assert.equal(requests[9].init?.method, "POST");
  assert.equal(
    new Headers(requests[9].init?.headers).get("x-agentops-csrf"),
    session.csrf_token,
  );
  const writePaths = requests
    .filter((request) => request.init?.method === "POST")
    .map((request) => request.path);
  assert.deepEqual(writePaths, [
    "/api/mis/human-auth/login",
    "/api/mis/tasks",
    "/api/mis/approvals/apr_contract/approve",
    "/api/mis/human-auth/logout",
  ]);
  for (const request of requests.filter((item) => [
    "/api/mis/tasks",
    "/api/mis/approvals/apr_contract/approve",
  ].includes(item.path))) {
    const headers = new Headers(request.init?.headers);
    assert.equal(headers.get("x-agentops-workspace-id"), "ws_commercial");
    assert.equal(headers.get("x-agentops-csrf"), session.csrf_token);
    assert.match(String(headers.get("idempotency-key")), /^human-/);
  }

  process.stdout.write(`${JSON.stringify({
    ok: true,
    authenticated_workspace_reads: true,
    login_logout_contract: true,
    task_dispatch_present: true,
    approval_mutations_present: true,
    csrf_workspace_idempotency_bound: true,
    responsive_contract: true,
    workspace_snapshot_identity_bound: true,
    expired_session_cleared: true,
  })}\n`);
}

await main();
