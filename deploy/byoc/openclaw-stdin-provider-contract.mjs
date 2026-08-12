#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  chmodSync,
  linkSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  createEphemeralStateRoot,
  executeCanonicalProviderRequest,
  removeEphemeralStateRoot,
} from "./openclaw-stdin-provider.mjs";

const sourcePath = fileURLToPath(new URL("./openclaw-stdin-provider.mjs", import.meta.url));
const sourceText = readFileSync(sourcePath, "utf8");
const rawPrompt = "adapter-contract-prompt-must-not-escape";
const rawResponse = "adapter-contract-response-must-not-escape";

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function request(overrides = {}) {
  const prompt = overrides.prompt ?? rawPrompt;
  return {
    agent_name: "main",
    prompt,
    prompt_hash: digest(Buffer.from(prompt, "utf8")),
    schema: "agentops_openclaw_provider_request_v1",
    timeout_seconds: 30,
    ...overrides,
  };
}

function canonicalBytes(value) {
  return Buffer.from(JSON.stringify(Object.fromEntries(
    Object.keys(value).sort().map((name) => [name, value[name]]),
  )), "utf8");
}

function parseResponse(bytes) {
  const response = JSON.parse(bytes.toString("utf8"));
  assert.deepEqual([...Object.keys(response)].sort(), [
    "dry_run", "duration_ms", "error_message", "error_type", "model_name", "ok",
    "output_present", "output_tokens", "provider_call_performed", "raw_payload_hash",
    "raw_prompt_omitted", "raw_response_omitted", "retryable", "schema",
  ].sort());
  assert.deepEqual(bytes, canonicalBytes(response));
  assert.equal(bytes.includes(Buffer.from(rawPrompt)), false);
  assert.equal(bytes.includes(Buffer.from(rawResponse)), false);
  return response;
}

assert.match(sourceText, /import\("openclaw\/plugin-sdk\/agent-runtime"\)/);
assert.match(sourceText, /modelRun: true/);
assert.match(sourceText, /senderIsOwner: false/);
assert.match(sourceText, /allowModelOverride: false/);
assert.match(sourceText, /deliver: false/);
assert.match(sourceText, /transcriptMessage: "\[omitted\]"/);
assert.match(sourceText, /removeEphemeralStateRoot\(baseStateRoot, stateRoot\)/);
assert.doesNotMatch(sourceText, /--message|--prompt|-m,/);

const root = mkdtempSync(join(tmpdir(), "agentops-stdin-provider-contract-"));
const stateBase = join(root, "state");
const workspace = join(root, "workspace");
mkdirSync(stateBase, { mode: 0o700 });
mkdirSync(workspace, { mode: 0o700 });

try {
  let observed = null;
  const response = parseResponse(await executeCanonicalProviderRequest(canonicalBytes(request()), {
    agentCommand: async (options, runtime) => {
      observed = options;
      assert.deepEqual(Object.keys(runtime).sort(), ["error", "exit", "log"]);
      assert.equal(options.message, rawPrompt);
      assert.equal(options.modelRun, true);
      assert.equal(options.senderIsOwner, false);
      assert.equal(options.allowModelOverride, false);
      assert.equal(options.deliver, false);
      assert.equal(options.transcriptMessage, "[omitted]");
      const sessions = join(stateBase, "agents", options.agentId, "sessions");
      mkdirSync(sessions, { recursive: true, mode: 0o700 });
      writeFileSync(join(sessions, `${options.sessionId}.jsonl`), rawPrompt, { mode: 0o600 });
      writeFileSync(join(sessions, `${options.sessionId}.trajectory.jsonl`), rawResponse, { mode: 0o600 });
      return {
        payloads: [{ text: rawResponse }],
        meta: { agentMeta: { model: "contract-model", provider: "contract-provider", usage: { output: 17 } } },
      };
    },
    now: (() => { let value = 1000; return () => (value += 25); })(),
    stateRoot: stateBase,
    workspaceDir: workspace,
  }));
  assert.ok(observed);
  assert.equal(response.ok, true);
  assert.equal(response.provider_call_performed, true);
  assert.equal(response.model_name, "contract-provider/contract-model");
  assert.equal(response.output_tokens, 17);
  assert.equal(response.raw_prompt_omitted, true);
  assert.equal(response.raw_response_omitted, true);
  assert.deepEqual(readdirSync(join(stateBase, "agents", "main", "sessions")), []);

  const failure = parseResponse(await executeCanonicalProviderRequest(canonicalBytes(request()), {
    agentCommand: async () => { throw new Error(`${rawPrompt}:${rawResponse}`); },
    now: () => 2000,
    stateRoot: stateBase,
    workspaceDir: workspace,
  }));
  assert.equal(failure.ok, false);
  assert.equal(failure.provider_call_performed, false);
  assert.equal(failure.error_type, "OpenClawExecutionFailed");
  assert.equal(failure.error_message, "Provider error detail omitted; OpenClaw execution failed.");

  const cleanupFailure = parseResponse(await executeCanonicalProviderRequest(canonicalBytes(request()), {
    agentCommand: async (options) => {
      const sessions = join(stateBase, "agents", options.agentId, "sessions");
      mkdirSync(sessions, { recursive: true, mode: 0o700 });
      const target = join(sessions, `${options.sessionId}.jsonl`);
      writeFileSync(target, rawPrompt, { mode: 0o600 });
      linkSync(target, `${target}.hardlink`);
      return { payloads: [{ text: rawResponse }], meta: {} };
    },
    now: () => 3000,
    stateRoot: stateBase,
    workspaceDir: workspace,
  }));
  assert.equal(cleanupFailure.ok, false);
  assert.equal(cleanupFailure.error_type, "AdapterCleanupFailed");
  assert.equal(cleanupFailure.provider_call_performed, false);
  rmSync(join(stateBase, "agents"), { recursive: true, force: true });

  await assert.rejects(
    () => executeCanonicalProviderRequest(Buffer.from(`${canonicalBytes(request()).toString("utf8")}\n`), {
      agentCommand: async () => assert.fail("noncanonical request dispatched"),
      stateRoot: stateBase,
      workspaceDir: workspace,
    }),
    /stdin_provider_request_invalid/,
  );
  await assert.rejects(
    () => executeCanonicalProviderRequest(canonicalBytes(request({ agent_name: ".." })), {
      agentCommand: async () => assert.fail("unsafe agent name dispatched"),
      stateRoot: stateBase,
      workspaceDir: workspace,
    }),
    /stdin_provider_request_invalid/,
  );
  await assert.rejects(
    () => executeCanonicalProviderRequest(canonicalBytes(request({ agent_name: "Main" })), {
      agentCommand: async () => assert.fail("normalizing agent name dispatched"),
      stateRoot: stateBase,
      workspaceDir: workspace,
    }),
    /stdin_provider_request_invalid/,
  );

  const ephemeral = createEphemeralStateRoot(stateBase);
  writeFileSync(join(ephemeral, "sensitive.jsonl"), rawPrompt, { mode: 0o600 });
  const renamedEphemeral = join(stateBase, "runtime-renamed-state");
  renameSync(ephemeral, renamedEphemeral);
  removeEphemeralStateRoot(stateBase, ephemeral);
  assert.deepEqual(readdirSync(stateBase), []);
  writeFileSync(join(stateBase, "stale-state"), rawPrompt, { mode: 0o600 });
  assert.throws(() => createEphemeralStateRoot(stateBase), /stdin_provider_state_root_not_empty/);
  rmSync(join(stateBase, "stale-state"));
  chmodSync(stateBase, 0o755);
  assert.throws(() => createEphemeralStateRoot(stateBase), /stdin_provider_state_root_metadata_invalid/);

  process.stdout.write(`${JSON.stringify({
    contract: "agentops_openclaw_stdin_provider_foundation_a07_v1",
    ok: true,
    exact_canonical_stdin_request_verified: true,
    official_agent_runtime_export_source_audited: true,
    prompt_argv_omitted: true,
    owner_and_model_override_disabled: true,
    model_run_no_tools_policy_requested: true,
    external_delivery_disabled: true,
    fixed_error_redaction_verified: true,
    one_shot_transcript_and_trajectory_cleanup_verified: true,
    isolated_ephemeral_state_tree_removed_before_stdout: true,
    real_openclaw_agent_command_executed: false,
    production_runtime_artifact_packaged: false,
    provider_call_verified: false,
    runtime_receipt_verified: false,
    hostile_runtime_isolation_verified: false,
  })}\n`);
} finally {
  rmSync(root, { recursive: true, force: true });
}
