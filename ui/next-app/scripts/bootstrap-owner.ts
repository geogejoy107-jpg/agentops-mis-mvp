import { randomBytes, randomUUID, scrypt as scryptCallback } from "node:crypto";
import process from "node:process";
import { Client } from "pg";
import type { PoolClient } from "pg";

import {
  HUMAN_PASSWORD_MAX_LENGTH,
  HUMAN_PASSWORD_MIN_LENGTH,
  HUMAN_SCRYPT_PARAMS,
} from "../src/server/controlPlane/humanPasswordPolicy";
import { appendAudit } from "../src/server/controlPlane/ledger";
import {
  assertHumanMemorySchemaReady,
  SchemaReadinessError,
} from "../src/server/controlPlane/schemaReadiness";

class BootstrapError extends Error {
  constructor(readonly code: string, message: string, readonly exitCode = 2) {
    super(message);
  }
}

function output(payload: Record<string, unknown>) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function parseArguments(argv: string[]) {
  const values = new Map<string, string>();
  let passwordStdin = false;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--password-stdin") {
      passwordStdin = true;
      continue;
    }
    if (argument.startsWith("--password") || argument.startsWith("--pass")) {
      throw new BootstrapError("password_argv_forbidden", "Password values are accepted only from a hidden prompt or --password-stdin.");
    }
    if (!["--workspace-id", "--username", "--display-name"].includes(argument)) {
      throw new BootstrapError("invalid_arguments", "Unknown or incomplete Owner bootstrap argument.");
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      throw new BootstrapError("invalid_arguments", "Owner bootstrap arguments require values.");
    }
    values.set(argument, value);
    index += 1;
  }
  const workspaceId = String(values.get("--workspace-id") || "").trim();
  const username = String(values.get("--username") || "").trim().toLowerCase();
  const displayName = String(values.get("--display-name") || username).trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(workspaceId)) {
    throw new BootstrapError("workspace_id_invalid", "--workspace-id must contain 1-128 safe identifier characters.");
  }
  if (!/^[a-z0-9][a-z0-9._-]{2,63}$/.test(username)) {
    throw new BootstrapError("username_invalid", "--username must contain 3-64 lowercase letters, digits, dot, underscore, or dash.");
  }
  if (!displayName || displayName.length > 80) {
    throw new BootstrapError("display_name_invalid", "--display-name must contain 1-80 characters.");
  }
  return { workspaceId, username, displayName, passwordStdin };
}

async function readPasswordFromStdin() {
  let raw = "";
  process.stdin.setEncoding("utf8");
  for await (const chunk of process.stdin) {
    raw += chunk;
    if (Buffer.byteLength(raw, "utf8") > 1024) {
      throw new BootstrapError("password_input_invalid", "Password input is too long.");
    }
  }
  const normalized = raw.replace(/\r\n/g, "\n");
  const lines = normalized.split("\n");
  if (lines.slice(1).some((line) => line.length > 0)) {
    throw new BootstrapError("password_input_invalid", "--password-stdin accepts exactly one line.");
  }
  return lines[0] || "";
}

function readHiddenPassword(label: string) {
  if (!process.stdin.isTTY || typeof process.stdin.setRawMode !== "function") {
    throw new BootstrapError("interactive_tty_required", "Use --password-stdin when no interactive TTY is available.");
  }
  return new Promise<string>((resolve, reject) => {
    let value = "";
    const cleanup = () => {
      process.stdin.off("data", onData);
      process.stdin.setRawMode(false);
      process.stdin.pause();
      process.stderr.write("\n");
    };
    const onData = (chunk: Buffer | string) => {
      const text = Buffer.isBuffer(chunk) ? chunk.toString("utf8") : chunk;
      for (const character of text) {
        if (character === "\u0003") {
          cleanup();
          reject(new BootstrapError("bootstrap_cancelled", "Owner bootstrap was cancelled.", 130));
          return;
        }
        if (character === "\r" || character === "\n") {
          cleanup();
          resolve(value);
          return;
        }
        if (character === "\u007f" || character === "\b") {
          value = value.slice(0, -1);
        } else if (character >= " ") {
          value += character;
        }
      }
    };
    process.stderr.write(label);
    process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.on("data", onData);
  });
}

async function suppliedPassword(passwordStdin: boolean) {
  if (passwordStdin) return readPasswordFromStdin();
  const first = await readHiddenPassword("Owner password: ");
  const confirmation = await readHiddenPassword("Confirm password: ");
  if (first !== confirmation) {
    throw new BootstrapError("password_confirmation_mismatch", "Password confirmation does not match.");
  }
  return first;
}

function derivePassword(password: string, salt: Buffer) {
  return new Promise<Buffer>((resolve, reject) => {
    scryptCallback(password, salt, HUMAN_SCRYPT_PARAMS.keylen, {
      N: HUMAN_SCRYPT_PARAMS.n,
      r: HUMAN_SCRYPT_PARAMS.r,
      p: HUMAN_SCRYPT_PARAMS.p,
      maxmem: 128 * 1024 * 1024,
    }, (error, derived) => {
      if (error) reject(error);
      else resolve(derived as Buffer);
    });
  });
}

async function bootstrap() {
  const args = parseArguments(process.argv.slice(2));
  const dsn = String(process.env.AGENTOPS_POSTGRES_DSN || process.env.DATABASE_URL || "").trim();
  if (!dsn) {
    throw new BootstrapError("postgres_dsn_required", "AGENTOPS_POSTGRES_DSN is required.");
  }
  const sslEnabled = ["1", "true", "require", "required", "on"]
    .includes(String(process.env.AGENTOPS_POSTGRES_SSL || "").trim().toLowerCase());
  const client = new Client({
    connectionString: dsn,
    ssl: sslEnabled ? { rejectUnauthorized: true } : undefined,
    application_name: "agentops-mis-owner-bootstrap",
  });
  let transactionStarted = false;
  let salt: Buffer | undefined;
  let derived: Buffer | undefined;
  try {
    await client.connect();
    const readiness = await assertHumanMemorySchemaReady(client as unknown as PoolClient);
    const password = await suppliedPassword(args.passwordStdin);
    if (password.length < HUMAN_PASSWORD_MIN_LENGTH || password.length > HUMAN_PASSWORD_MAX_LENGTH) {
      throw new BootstrapError("password_length_invalid", "Password must contain 12-256 characters.");
    }
    salt = randomBytes(16);
    derived = await derivePassword(password, salt);
    const params = JSON.stringify(HUMAN_SCRYPT_PARAMS);
    const userId = `husr_${randomUUID().replaceAll("-", "").slice(0, 12)}`;
    const credentialId = `hcred_${randomUUID().replaceAll("-", "").slice(0, 12)}`;
    const now = new Date().toISOString();
    await client.query("BEGIN");
    transactionStarted = true;
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", ["agentops-human-owner-bootstrap-v1"]);
    const existingOwner = await client.query(
      "SELECT 1 FROM workspace_memberships WHERE role='owner' LIMIT 1 FOR UPDATE",
    );
    if (existingOwner.rowCount) {
      throw new BootstrapError("owner_already_initialized", "An Owner membership already exists.");
    }
    const existingUsername = await client.query(
      "SELECT 1 FROM human_login_credentials WHERE username=$1 LIMIT 1 FOR UPDATE",
      [args.username],
    );
    if (existingUsername.rowCount) {
      throw new BootstrapError("username_already_initialized", "The username is already initialized.");
    }
    await client.query(
      "INSERT INTO users(user_id,name,email,role,created_at) VALUES($1,$2,$3,'customer',$4)",
      [userId, args.displayName, `${args.username}@local.invalid`, now],
    );
    await client.query(
      `INSERT INTO workspace_memberships(workspace_id,user_id,role,status,created_at,updated_at)
      VALUES($1,$2,'owner','active',$3,$3)`,
      [args.workspaceId, userId, now],
    );
    await client.query(
      `INSERT INTO human_login_credentials(
        credential_id,user_id,username,password_hash,password_salt,password_params_json,status,
        created_at,updated_at,last_login_at
      ) VALUES($1,$2,$3,$4,$5,$6,'active',$7,$7,NULL)`,
      [credentialId, userId, args.username, derived.toString("hex"), salt.toString("hex"), params, now],
    );
    await appendAudit(client as unknown as PoolClient, {
      workspaceId: args.workspaceId,
      actorType: "system",
      actorId: null,
      action: "human_auth.owner_bootstrap",
      entityType: "users",
      entityId: userId,
      after: {
        user_id: userId,
        workspace_id: args.workspaceId,
        membership_role: "owner",
        membership_status: "active",
      },
      metadata: {
        bootstrap_scope: "first_deployment",
        credential_omitted: true,
        password_omitted: true,
      },
    });
    await client.query("COMMIT");
    transactionStarted = false;
    output({
      ok: true,
      operation: "commercial_owner_bootstrap",
      schema_version: readiness.version,
      user: { user_id: userId, name: args.displayName },
      membership: { workspace_id: args.workspaceId, role: "owner", status: "active" },
      credential_omitted: true,
      password_omitted: true,
      session_created: false,
    });
  } catch (error) {
    if (transactionStarted) await client.query("ROLLBACK").catch(() => undefined);
    if (error instanceof BootstrapError) throw error;
    if (error instanceof SchemaReadinessError) {
      throw new BootstrapError(
        error.code,
        "Owner bootstrap requires the exact commercial Human Session migration version.",
        1,
      );
    }
    throw new BootstrapError("owner_bootstrap_failed", "Owner bootstrap failed closed; verify the migration and Postgres connectivity.", 1);
  } finally {
    await client.end().catch(() => undefined);
    derived?.fill(0);
    salt?.fill(0);
  }
}

bootstrap().catch((error: unknown) => {
  const failure = error instanceof BootstrapError
    ? error
    : new BootstrapError("owner_bootstrap_failed", "Owner bootstrap failed closed.", 1);
  output({
    ok: false,
    error: failure.code,
    message: failure.message,
    credential_omitted: true,
    password_omitted: true,
  });
  process.exitCode = failure.exitCode;
});
