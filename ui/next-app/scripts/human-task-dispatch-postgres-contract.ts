import assert from "node:assert/strict";
import { randomBytes, randomUUID, scryptSync } from "node:crypto";

import { NextRequest } from "next/server";
import { Client } from "pg";

import { POST as dispatchTask } from "../app/api/mis/tasks/route";
import { closeControlPlanePoolForTests } from "../src/server/controlPlane/db";
import { establishHumanSession } from "../src/server/controlPlane/humanSession";
import { HUMAN_SCRYPT_PARAMS } from "../src/server/controlPlane/humanPasswordPolicy";
import {
  POSTGRES_MIGRATION_MANIFEST,
  SCHEMA_CONTRACT,
} from "../src/server/controlPlane/schemaReadiness";
import { createPostgresRoleBoundaryFixture } from "./postgres-role-boundary-test-helper";

const ORIGIN = "https://mis.example.test";
const HOST = "mis.example.test";
const WORKSPACE = "ws_human_task_dispatch";
const FOREIGN_WORKSPACE = "ws_human_task_dispatch_foreign";
const PASSWORD = `${randomBytes(24).toString("base64url")}Aa1!`;

type HumanRole =
  | "viewer"
  | "operator"
  | "workspace-admin"
  | "owner";

type HumanSession = Readonly<{
  cookie: string;
  csrf: string;
}>;

type RouteResult = Readonly<{
  response: Response;
  body: Record<string, unknown>;
}>;

function taskBody(
  ownerAgentId: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    workspace_id: WORKSPACE,
    title: "Dispatch governed commercial work",
    description: "Execute the requested work through the governed Worker.",
    owner_agent_id: ownerAgentId,
    priority: "high",
    risk_level: "medium",
    acceptance_criteria: "Write auditable task and runtime evidence.",
    budget_limit_usd: 12.5,
    ...overrides,
  };
}

function dispatchRequest(
  body: Record<string, unknown>,
  input: Readonly<{
    session?: HumanSession;
    workspaceId?: string;
    idempotencyKey?: string;
    origin?: string;
    includeCsrf?: boolean;
  }> = {},
) {
  const headers = new Headers({
    "content-type": "application/json",
    host: HOST,
    origin: input.origin ?? ORIGIN,
    "x-agentops-workspace-id": input.workspaceId ?? WORKSPACE,
    "idempotency-key": input.idempotencyKey
      ?? `task-dispatch-${randomUUID()}`,
  });
  if (input.session) {
    headers.set("cookie", input.session.cookie);
    if (input.includeCsrf !== false) {
      headers.set("x-agentops-csrf", input.session.csrf);
    }
  }
  return new NextRequest(`${ORIGIN}/api/mis/tasks`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

async function callDispatch(
  body: Record<string, unknown>,
  input: Parameters<typeof dispatchRequest>[1] = {},
): Promise<RouteResult> {
  const response = await dispatchTask(dispatchRequest(body, input));
  return { response, body: await response.json() as Record<string, unknown> };
}

function assertDenied(
  result: RouteResult,
  status: number,
  error: string,
) {
  assert.equal(result.response.status, status);
  assert.equal(result.body.error, error);
  assert.equal(Object.hasOwn(result.body, "task"), false);
  assert.equal(Object.hasOwn(result.body, "task_id"), false);
}

async function seedHuman(
  client: Client,
  userId: string,
  username: string,
  role: HumanRole,
  workspaceId = WORKSPACE,
) {
  const now = new Date().toISOString();
  const salt = randomBytes(16);
  const passwordHash = scryptSync(
    PASSWORD,
    salt,
    HUMAN_SCRYPT_PARAMS.keylen,
    {
      N: HUMAN_SCRYPT_PARAMS.n,
      r: HUMAN_SCRYPT_PARAMS.r,
      p: HUMAN_SCRYPT_PARAMS.p,
      maxmem: 128 * 1024 * 1024,
    },
  ).toString("hex");
  await client.query(
    `INSERT INTO users(user_id,name,email,role,created_at)
    VALUES($1,$2,$3,$4,$5)`,
    [userId, username, `${username}@example.test`, role, now],
  );
  await client.query(
    `INSERT INTO workspace_memberships(
      workspace_id,user_id,role,status,created_at,updated_at
    ) VALUES($1,$2,$3,'active',$4,$4)`,
    [workspaceId, userId, role, now],
  );
  await client.query(
    `INSERT INTO human_login_credentials(
      credential_id,user_id,username,password_hash,password_salt,
      password_params_json,status,created_at,updated_at,last_login_at
    ) VALUES($1,$2,$3,$4,$5,$6,'active',$7,$7,NULL)`,
    [
      `cred_${username}`,
      userId,
      username,
      passwordHash,
      salt.toString("hex"),
      JSON.stringify(HUMAN_SCRYPT_PARAMS),
      now,
    ],
  );
}

async function login(username: string): Promise<HumanSession> {
  const result = await establishHumanSession(
    new Headers({ origin: ORIGIN, host: HOST }),
    { username, password: PASSWORD },
  );
  assert.equal(result.status, 200);
  assert.match(String(result.body.csrf_token), /^[a-f0-9]{64}$/);
  return {
    cookie: result.setCookie.split(";", 1)[0],
    csrf: String(result.body.csrf_token),
  };
}

async function seedAgent(
  client: Client,
  label: string,
  workspaceId = WORKSPACE,
  status = "idle",
) {
  const agentId = `agt_task_dispatch_${label}`;
  const now = new Date().toISOString();
  await client.query(
    `INSERT INTO agents(
      agent_id,name,role,description,runtime_type,model_provider,model_name,
      status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,
      created_at,updated_at
    ) VALUES(
      $1,$2,'worker',NULL,'hermes','hermes','contract-model',$3,
      'standard','[]',100,'usr_task_owner',$4,$4
    )`,
    [agentId, `Task dispatch ${label}`, status, now],
  );
  await client.query(
    `INSERT INTO agent_gateway_tokens(
      token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,
      heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,
      last_heartbeat_at
    ) VALUES(
      $1,$2,$3,$4,'["tasks:read"]','active','task dispatch fixture',
      300,$5,NULL,NULL,NULL,NULL
    )`,
    [
      `tok_task_dispatch_${label}`,
      randomBytes(32).toString("hex"),
      workspaceId,
      agentId,
      now,
    ],
  );
  return agentId;
}

async function taskEvidence(client: Client, taskId: string) {
  const task = await client.query<{
    task_id: string;
    workspace_id: string;
    requester_id: string;
    owner_agent_id: string;
    status: string;
  }>(
    `SELECT task_id,workspace_id,requester_id,owner_agent_id,status
    FROM tasks WHERE task_id=$1`,
    [taskId],
  );
  const audit = await client.query<{
    actor_type: string;
    actor_id: string;
    action: string;
    metadata_json: string;
  }>(
    `SELECT actor_type,actor_id,action,metadata_json
    FROM audit_logs
    WHERE workspace_id=$1 AND entity_type='tasks' AND entity_id=$2
      AND action='human.task_dispatch'`,
    [WORKSPACE, taskId],
  );
  const runtime = await client.query<{
    event_type: string;
    status: string;
    task_id: string;
    agent_id: string;
    raw_payload_hash: string;
  }>(
    `SELECT event_type,status,task_id,agent_id,raw_payload_hash
    FROM runtime_events
    WHERE workspace_id=$1 AND task_id=$2
      AND event_type='task.human_dispatch'`,
    [WORKSPACE, taskId],
  );
  return { task, audit, runtime };
}

async function run() {
  const baseDsn = String(process.env.AGENTOPS_POSTGRES_DSN || "").trim();
  assert.ok(baseDsn, "AGENTOPS_POSTGRES_DSN is required");
  const original = {
    origins: process.env.AGENTOPS_ALLOWED_ORIGINS,
    hmac: process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY,
    fetch: globalThis.fetch,
  };
  const fixture = await createPostgresRoleBoundaryFixture(
    baseDsn,
    "task_dispatch",
  );
  const restoreRuntimeEnvironment = fixture.activateRuntimeEnvironment();
  const admin = fixture.owner;
  let pythonObserverRequests = 0;
  process.env.AGENTOPS_ALLOWED_ORIGINS = ORIGIN;
  process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = randomBytes(48)
    .toString("base64url");
  globalThis.fetch = async () => {
    pythonObserverRequests += 1;
    throw new Error("Network and Python proxy requests are forbidden.");
  };

  try {
    const version = await admin.query<{ server_version: string }>(
      "SHOW server_version",
    );
    assert.match(version.rows[0]?.server_version || "", /^16\./);
    assert.equal(fixture.migration.schema_contract, SCHEMA_CONTRACT);
    assert.equal(
      fixture.migration.applied_count,
      POSTGRES_MIGRATION_MANIFEST.length,
    );
    assert.equal(fixture.migration.schema_fingerprint_verified, true);

    await seedHuman(admin, "usr_task_owner", "task-owner", "owner");
    await seedHuman(admin, "usr_task_admin", "task-admin", "workspace-admin");
    await seedHuman(admin, "usr_task_operator", "task-operator", "operator");
    await seedHuman(admin, "usr_task_viewer", "task-viewer", "viewer");
    await seedHuman(
      admin,
      "usr_task_foreign",
      "task-foreign",
      "owner",
      FOREIGN_WORKSPACE,
    );
    const localAgent = await seedAgent(admin, "local");
    const foreignAgent = await seedAgent(admin, "foreign", FOREIGN_WORKSPACE);
    const disabledAgent = await seedAgent(admin, "disabled", WORKSPACE, "disabled");

    const owner = await login("task-owner");
    const workspaceAdmin = await login("task-admin");
    const operator = await login("task-operator");
    const viewer = await login("task-viewer");
    const foreignOwner = await login("task-foreign");

    assertDenied(
      await callDispatch(taskBody(localAgent), {
        idempotencyKey: "task-dispatch-no-cookie-0001",
      }),
      401,
      "human_auth_required",
    );
    assertDenied(
      await callDispatch(taskBody(localAgent), {
        session: owner,
        origin: "https://attacker.example.test",
        idempotencyKey: "task-dispatch-bad-origin-0001",
      }),
      403,
      "origin_validation_failed",
    );
    assertDenied(
      await callDispatch(taskBody(localAgent), {
        session: owner,
        includeCsrf: false,
        idempotencyKey: "task-dispatch-no-csrf-0001",
      }),
      403,
      "csrf_validation_failed",
    );
    assertDenied(
      await callDispatch(taskBody(localAgent), {
        session: owner,
        workspaceId: FOREIGN_WORKSPACE,
        idempotencyKey: "task-dispatch-header-drift-0001",
      }),
      403,
      "forbidden",
    );
    assertDenied(
      await callDispatch(taskBody(localAgent), {
        session: foreignOwner,
        idempotencyKey: "task-dispatch-foreign-member-0001",
      }),
      403,
      "human_membership_forbidden",
    );
    assertDenied(
      await callDispatch(taskBody(localAgent), {
        session: viewer,
        idempotencyKey: "task-dispatch-viewer-0001",
      }),
      403,
      "human_task_role_forbidden",
    );
    assertDenied(
      await callDispatch(taskBody(foreignAgent), {
        session: owner,
        idempotencyKey: "task-dispatch-foreign-agent-0001",
      }),
      400,
      "human_task_owner_unavailable",
    );
    assertDenied(
      await callDispatch(taskBody(disabledAgent), {
        session: owner,
        idempotencyKey: "task-dispatch-disabled-agent-0001",
      }),
      400,
      "human_task_owner_unavailable",
    );

    const allowed = [
      ["owner", owner, "usr_task_owner"],
      ["workspace-admin", workspaceAdmin, "usr_task_admin"],
      ["operator", operator, "usr_task_operator"],
    ] as const;
    const taskIds: string[] = [];
    for (const [role, session, userId] of allowed) {
      const key = `task-dispatch-${role}-allowed-0001`;
      const body = taskBody(localAgent, { title: `Allowed ${role} dispatch` });
      const created = await callDispatch(body, {
        session,
        idempotencyKey: key,
      });
      assert.equal(created.response.status, 201);
      assert.equal(created.body.ok, true);
      assert.equal(created.body.provider, "agentops-human-session");
      assert.equal(created.body.control_plane, "typescript_postgres");
      assert.equal(created.body.operation, "task_dispatch");
      assert.equal(created.body.outcome, "created");
      assert.equal(created.body.workspace_id, WORKSPACE);
      assert.equal(created.body.token_omitted, true);
      const taskId = String(created.body.task_id);
      assert.match(taskId, /^tsk_human_[a-f0-9]{24}$/);
      taskIds.push(taskId);

      const evidence = await taskEvidence(admin, taskId);
      assert.equal(evidence.task.rowCount, 1);
      assert.deepEqual(evidence.task.rows[0], {
        task_id: taskId,
        workspace_id: WORKSPACE,
        requester_id: userId,
        owner_agent_id: localAgent,
        status: "planned",
      });
      assert.equal(evidence.audit.rowCount, 1);
      assert.equal(evidence.audit.rows[0].actor_type, "user");
      assert.equal(evidence.audit.rows[0].actor_id, userId);
      assert.equal(evidence.audit.rows[0].action, "human.task_dispatch");
      const metadata = JSON.parse(
        evidence.audit.rows[0].metadata_json,
      ) as Record<string, unknown>;
      assert.equal(metadata.membership_role, role);
      assert.equal(metadata.owner_agent_id, localAgent);
      assert.equal(metadata.raw_payload_omitted, true);
      assert.equal(metadata.token_omitted, true);
      assert.match(String(metadata.request_hash), /^[a-f0-9]{64}$/);
      assert.equal(evidence.runtime.rowCount, 1);
      assert.deepEqual(evidence.runtime.rows[0], {
        event_type: "task.human_dispatch",
        status: "planned",
        task_id: taskId,
        agent_id: localAgent,
        raw_payload_hash: metadata.request_hash,
      });

      const replay = await callDispatch(body, {
        session,
        idempotencyKey: key,
      });
      assert.equal(replay.response.status, 200);
      assert.equal(replay.body.outcome, "unchanged");
      assert.equal(replay.body.task_id, taskId);
      const replayEvidence = await taskEvidence(admin, taskId);
      assert.equal(replayEvidence.task.rowCount, 1);
      assert.equal(replayEvidence.audit.rowCount, 1);
      assert.equal(replayEvidence.runtime.rowCount, 1);

      assertDenied(
        await callDispatch(
          taskBody(localAgent, { title: `Conflicting ${role} dispatch` }),
          { session, idempotencyKey: key },
        ),
        409,
        "human_task_idempotency_conflict",
      );
    }

    const workspaceCounts = await admin.query<{
      tasks: string;
      audits: string;
      runtime_events: string;
    }>(
      `SELECT
        (SELECT count(*)::text FROM tasks WHERE workspace_id=$1) AS tasks,
        (SELECT count(*)::text FROM audit_logs
          WHERE workspace_id=$1 AND action='human.task_dispatch') AS audits,
        (SELECT count(*)::text FROM runtime_events
          WHERE workspace_id=$1 AND event_type='task.human_dispatch') AS runtime_events`,
      [WORKSPACE],
    );
    assert.deepEqual(workspaceCounts.rows[0], {
      tasks: "3",
      audits: "3",
      runtime_events: "3",
    });
    assert.equal(new Set(taskIds).size, allowed.length);
    assert.equal(pythonObserverRequests, 0);

    console.log(JSON.stringify({
      ok: true,
      contract: "human_task_dispatch_postgres_v1",
      postgres_major: 16,
      schema_contract: fixture.migration.schema_contract,
      migration_count: fixture.migration.applied_count,
      schema_fingerprint_verified:
        fixture.migration.schema_fingerprint_verified,
      human_session_cookie_origin_csrf_workspace_verified: true,
      allowed_roles: allowed.map(([role]) => role),
      low_privilege_denied: true,
      cross_workspace_denied: true,
      agent_workspace_binding_verified: true,
      disabled_agent_denied: true,
      idempotent_replay_verified: true,
      idempotency_conflict_verified: true,
      audit_runtime_evidence_verified: true,
      runtime_role_boundary_verified: true,
      python_observer_requests: pythonObserverRequests,
      sqlite_used: false,
    }));
  } finally {
    globalThis.fetch = original.fetch;
    if (original.origins === undefined) {
      delete process.env.AGENTOPS_ALLOWED_ORIGINS;
    } else {
      process.env.AGENTOPS_ALLOWED_ORIGINS = original.origins;
    }
    if (original.hmac === undefined) {
      delete process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY;
    } else {
      process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = original.hmac;
    }
    await closeControlPlanePoolForTests();
    restoreRuntimeEnvironment();
    await fixture.cleanup();
  }
}

run().catch((error) => {
  console.error(error instanceof Error ? error.stack : error);
  process.exitCode = 1;
});
