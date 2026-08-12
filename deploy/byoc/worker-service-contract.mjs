#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const root = mkdtempSync(join(tmpdir(), "agentops-byoc-worker-contract-"));
const token = "contract-agent-token-fixture-0123456789abcdef";

function run(entrypoint, environment) {
  return spawnSync(process.execPath, [join(moduleDirectory, entrypoint)], {
    cwd: moduleDirectory,
    encoding: "utf8",
    env: { PATH: process.env.PATH, ...environment },
  });
}

try {
  const composeRelease = readFileSync(join(moduleDirectory, "compose.release.yaml"), "utf8");
  const composeSource = readFileSync(join(moduleDirectory, "compose.yaml"), "utf8");
  const dockerfile = readFileSync(join(moduleDirectory, "Dockerfile"), "utf8");
  for (const compose of [composeRelease, composeSource]) {
    for (const profile of ["worker-hermes", "worker-openclaw"]) {
      assert.match(compose, new RegExp(`profiles: \\[${profile}\\]`));
    }
    assert.equal((compose.match(/^\s{4}init: true$/gm) || []).length, 2);
    assert.match(compose, /restart: unless-stopped/);
    assert.equal((compose.match(/\n\s+init: true/g) || []).length, 2);
    assert.match(compose, /AGENTOPS_AGENT_TOKEN_SOURCE_FILE: \/run\/secrets\/agent_token/);
    assert.match(compose, /node, \/usr\/local\/lib\/agentops\/worker-entrypoint\.mjs/);
    assert.match(compose, /node, \/usr\/local\/lib\/agentops\/worker-healthcheck\.mjs/);
    assert.match(compose, /condition: service_healthy/);
    assert.match(compose, /read_only: true/);
    assert.match(compose, /cap_drop:\s*\n\s+- ALL/);
    assert.match(compose, /no-new-privileges:true/);
    assert.doesNotMatch(compose, /^\s+(?:AGENTOPS_API_KEY|AGENTOPS_AGENT_TOKEN):/m);
  }
  assert.match(dockerfile, /worker-entrypoint\.mjs/);
  assert.match(dockerfile, /worker-healthcheck\.mjs/);
  assert.match(dockerfile, /worker-service-contract\.mjs/);
  const entrypoint = readFileSync(join(moduleDirectory, "worker-entrypoint.mjs"), "utf8");
  assert.match(entrypoint, /detached: true/);
  assert.match(entrypoint, /process\.kill\(-child\.pid, signal\)/);
  assert.match(entrypoint, /signalChildGroup\(child, "SIGKILL"\)/);
  assert.match(entrypoint, /forcedStop = true/);
  assert.match(entrypoint, /stopping && !forcedStop && result\.code === 0/);
  assert.doesNotMatch(entrypoint, /result\.signal.*return 0/);
  assert.match(entrypoint, /stopping && !forcedStop/);

  const tokenPath = join(root, "agent-token");
  writeFileSync(tokenPath, `${token}\n`, { mode: 0o600 });
  assert.equal((await import("./worker-entrypoint.mjs")).readAgentToken(tokenPath), token);
  chmodSync(tokenPath, 0o600);

  const direct = run("worker-entrypoint.mjs", {
    NODE_ENV: "production",
    AGENTOPS_AGENT_TOKEN: token,
    AGENTOPS_AGENT_TOKEN_SOURCE_FILE: tokenPath,
    AGENTOPS_WORKER_ADAPTER: "hermes",
  });
  assert.equal(direct.status, 78);
  assert.match(direct.stderr, /direct_agent_token_environment_forbidden/);
  assert.doesNotMatch(direct.stdout + direct.stderr, new RegExp(token));

  const insecure = run("worker-entrypoint.mjs", {
    NODE_ENV: "production",
    AGENTOPS_AGENT_TOKEN_SOURCE_FILE: tokenPath,
    AGENTOPS_WORKER_ADAPTER: "hermes",
    AGENTOPS_BASE_URL: "http://control-plane:3001",
    AGENTOPS_WORKSPACE_ID: "ws_contract",
    AGENTOPS_AGENT_ID: "agt_contract",
    AGENTOPS_RUN_ESTIMATED_COST_USD: "1.000000",
    HERMES_GATEWAY_URL: "http://hermes:8642",
    HERMES_MODEL: "hermes-agent",
  });
  assert.equal(insecure.status, 78);
  assert.match(insecure.stderr, /agentops_base_url_https_required/);
  assert.doesNotMatch(insecure.stdout + insecure.stderr, new RegExp(token));

  const healthRoot = join(root, "health");
  mkdirSync(healthRoot);
  const healthSource = readFileSync(join(moduleDirectory, "worker-healthcheck.mjs"), "utf8")
    .replace('const statePath = "/run/agentops-worker/health.json";', `const statePath = ${JSON.stringify(join(healthRoot, "health.json"))};`);
  assert.match(healthSource, /payload\.pid < 1/);
  const healthScript = join(root, "worker-healthcheck.mjs");
  writeFileSync(healthScript, healthSource);
  writeFileSync(join(healthRoot, "health.json"), JSON.stringify({
    status: "ready",
    pid: process.pid,
    lease_seconds: 120,
    updated_at_ms: Date.now(),
  }));
  assert.equal(spawnSync(process.execPath, [healthScript]).status, 0);
  for (const invalidPid of [0, -1]) {
    writeFileSync(join(healthRoot, "health.json"), JSON.stringify({
      status: "ready",
      pid: invalidPid,
      lease_seconds: 120,
      updated_at_ms: Date.now(),
    }));
    assert.equal(spawnSync(process.execPath, [healthScript]).status, 1);
  }
  writeFileSync(join(healthRoot, "health.json"), JSON.stringify({
    status: "ready",
    pid: process.pid,
    lease_seconds: 120,
    updated_at_ms: Date.now() - 121_000,
  }));
  assert.equal(spawnSync(process.execPath, [healthScript]).status, 1);

  process.stdout.write(`${JSON.stringify({
    contract: "agentops_byoc_typescript_worker_service_v1",
    source_free_image_entrypoint: true,
    explicit_profiles_only: ["worker-hermes", "worker-openclaw"],
    file_agent_token: true,
    direct_token_environment_rejected: true,
    production_https_fail_closed: true,
    restart_policy: "unless-stopped",
    health_lease_verified: true,
    container_pid_one_supported: true,
    container_init_reaper_required: true,
    process_group_shutdown_bounded: true,
    forced_shutdown_reports_failure: true,
    signal_terminated_child_reports_failure: true,
    docker_init_reaper_enabled: true,
    real_provider_execution_performed: false,
    token_omitted: true,
  })}\n`);
} finally {
  rmSync(root, { recursive: true, force: true });
}
