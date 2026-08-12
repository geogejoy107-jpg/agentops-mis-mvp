#!/usr/bin/env node

import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const SHA = "a".repeat(40);
const root = mkdtempSync(join(tmpdir(), "agentops-runtime-status-contract-"));
const receiptPath = join(root, "receipt.json");
const callsPath = join(root, "gh-calls.jsonl");
const fakeGh = join(root, "gh");
const script = new URL("./commercial-runtime-status.mjs", import.meta.url);

function receipt() {
  const worker = (runtime) => ({
    run_id: `run_gw_${runtime}`,
    manifest_id: `pem_${runtime}`,
    provider_call_performed: true,
    dry_run: false,
    cost_reservation_settled: true,
    delivery_approval_request_outcome: "created",
  });
  const review = {
    delivery_approval_first_outcome: "updated",
    delivery_approval_replay_outcome: "unchanged",
    delivery_manifest_gate_passed: true,
  };
  return {
    ok: true,
    contract: "nextjs_postgres_real_worker_human_review_v5",
    source_commit: SHA,
    tracked_worktree_clean: true,
    tracked_worktree_unchanged: true,
    next_artifact_identity_verified: true,
    worker_implementation: "typescript",
    typescript_worker_started: true,
    python_worker_started: false,
    python_api_started: false,
    real_runtime_execution_performed: true,
    manifest_authority_guards_passed: true,
    real_run_bound_delivery_decisions_completed: true,
    worker_created_delivery_approvals: true,
    run_cost_reservations_settled: true,
    fixture_cleanup_verified_before_success: true,
    adapters: ["hermes", "openclaw"],
    workers: { hermes: worker("hermes"), openclaw: worker("openclaw") },
    human_reviews: { hermes: review, openclaw: review },
  };
}

function run(arguments_, value = receipt(), environment = {}) {
  writeFileSync(receiptPath, JSON.stringify(value));
  const result = spawnSync(process.execPath, [script.pathname, ...arguments_], {
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${root}:${process.env.PATH}`,
      GH_CALLS: callsPath,
      ...environment,
    },
  });
  return { ...result, payload: JSON.parse(result.stdout) };
}

try {
  writeFileSync(fakeGh, `#!/bin/sh
printf '%s\\n' "$*" >> "$GH_CALLS"
case "$*" in
  *commits/*/statuses*)
    if [ "\${GH_STATUS_MODE:-success}" = missing ]; then
      printf '%s\\n' '[{"context":"agentops/real-hermes","state":"success"}]'
    else
      printf '%s\\n' '[{"context":"agentops/real-hermes","state":"success"},{"context":"agentops/real-openclaw","state":"success"}]'
    fi ;;
  *) printf '%s\\n' '{}' ;;
esac
`);
  chmodSync(fakeGh, 0o755);

  const valid = run(["validate", "--receipt", receiptPath, "--sha", SHA]);
  assert.equal(valid.status, 0);
  assert.equal(valid.payload.ok, true);
  assert.equal(valid.payload.evidence.hermes.provider_call_performed, true);

  const published = run(["publish", "--receipt", receiptPath, "--sha", SHA,
    "--repo", "owner/repo", "--target-url", "https://example.invalid/evidence"]);
  assert.equal(published.status, 0);
  assert.deepEqual(published.payload.contexts,
    ["agentops/real-hermes", "agentops/real-openclaw"]);
  const calls = readFileSync(callsPath, "utf8");
  assert.match(calls, new RegExp(`statuses/${SHA}`));
  assert.match(calls, /context=agentops\/real-hermes/);
  assert.match(calls, /context=agentops\/real-openclaw/);

  const verified = run(["verify", "--sha", SHA, "--repo", "owner/repo"]);
  assert.equal(verified.status, 0);
  assert.equal(verified.payload.contexts["agentops/real-hermes"], "success");

  const missing = run(
    ["verify", "--sha", SHA, "--repo", "owner/repo"],
    receipt(),
    { GH_STATUS_MODE: "missing" },
  );
  assert.equal(missing.status, 1);
  assert.equal(missing.payload.error, "runtime_status_exact_head_context_missing");

  const wrongSha = run(["validate", "--receipt", receiptPath, "--sha", "b".repeat(40)]);
  assert.equal(wrongSha.status, 1);
  assert.equal(wrongSha.payload.error, "runtime_status_receipt_shared_evidence_invalid");

  const dryRunReceipt = receipt();
  dryRunReceipt.workers.hermes.dry_run = true;
  const dryRun = run(["validate", "--receipt", receiptPath, "--sha", SHA], dryRunReceipt);
  assert.equal(dryRun.status, 1);
  assert.equal(dryRun.payload.error, "runtime_status_hermes_evidence_invalid");

  const pythonReceipt = receipt();
  pythonReceipt.python_worker_started = true;
  const python = run(["validate", "--receipt", receiptPath, "--sha", SHA], pythonReceipt);
  assert.equal(python.status, 1);
  assert.equal(python.payload.error, "runtime_status_receipt_shared_evidence_invalid");

  process.stdout.write(`${JSON.stringify({
    ok: true,
    contract: "agentops_commercial_runtime_exact_head_status_contract_v1",
    exact_sha_bound: true,
    real_provider_required: true,
    typescript_worker_required: true,
    hermes_openclaw_contexts_required: true,
    credentials_omitted: true,
  })}\n`);
} finally {
  rmSync(root, { recursive: true, force: true });
}
