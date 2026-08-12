#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const SHA = "a".repeat(40);
const CONTRACT = "agentops_commercial_runtime_exact_head_status_v1";
const REPOSITORY = "owner/repo";
const PUBLISHER = "owner";
const COMMENT_ID = "42";
const COMMENT_URL = `https://github.com/${REPOSITORY}/commit/${SHA}#commitcomment-${COMMENT_ID}`;
const CONTEXTS = ["agentops/real-hermes", "agentops/real-openclaw"];
const root = mkdtempSync(join(tmpdir(), "agentops-runtime-status-contract-"));
const receiptPath = join(root, "receipt.json");
const callsPath = join(root, "gh-calls.jsonl");
const fakeGh = join(root, "gh");
const script = new URL("./commercial-runtime-status.mjs", import.meta.url);
const ciWorkflow = readFileSync(
  new URL("../.github/workflows/ci.yml", import.meta.url),
  "utf8",
);

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
    contract: "nextjs_postgres_real_worker_human_review_v6",
    source_commit: SHA,
    tracked_worktree_clean: true,
    tracked_worktree_unchanged: true,
    next_artifact_identity_verified: true,
    worker_implementation: "typescript",
    typescript_worker_started: true,
    python_worker_started: false,
    python_api_started: false,
    postgres_dsn_source: "owner_only_file",
    postgres_dsn_argv_omitted: true,
    postgres_dsn_input_boundary_verified: true,
    postgres_dsn_loopback_required: true,
    postgres_dsn_source_unchanged: true,
    direct_database_credentials_in_child_environment_omitted: true,
    ephemeral_credential_files_removed: true,
    next_process_stop: {
      stopped: true,
      process_group_empty: true,
      errors: [],
    },
    database_role_credentials_distinct: true,
    credential_files_purpose_isolated: true,
    credential_files_stage_scoped: true,
    same_uid_os_credential_isolation_claimed: false,
    real_runtime_execution_performed: true,
    openclaw_provider_service_execution_verified: true,
    openclaw_provider_transport: "unix_socket",
    manifest_authority_guards_passed: true,
    real_run_bound_delivery_decisions_completed: true,
    worker_created_delivery_approvals: true,
    run_cost_reservations_settled: true,
    fixture_cleanup_verified_before_success: true,
    adapters: ["hermes", "openclaw"],
    workers: { hermes: worker("hermes"), openclaw: worker("openclaw") },
    human_reviews: { hermes: review, openclaw: review },
    runtime_dependency_identity: {
      openclaw_binary_sha256: "b".repeat(64),
      openclaw_provider_entrypoint_sha256: "c".repeat(64),
    },
    provider_services: {
      openclaw: {
        provider_process_started: true,
        provider_socket_ready: true,
        provider_process_stopped: true,
        provider_process_returncode: 0,
        provider_socket_removed: true,
        provider_temp_root_removed: true,
        provider_agent_token_environment_omitted: true,
        raw_provider_output_omitted: true,
      },
    },
  };
}

function digest(contents) {
  return createHash("sha256").update(contents).digest("hex");
}

function attestation(receiptDigest, overrides = {}) {
  return JSON.stringify({
    contract: CONTRACT,
    source_commit: SHA,
    receipt_sha256: receiptDigest,
    contexts: CONTEXTS,
    trust_model: "repository_owner_operator_attestation_v1",
    provider_signed: false,
    ...overrides,
  });
}

function fixtures(receiptDigest, options = {}) {
  const statusDigest = options.statusDigest || receiptDigest;
  const firstTarget = options.firstTarget || COMMENT_URL;
  const secondTarget = options.secondTarget || firstTarget;
  const statusPublisher = options.statusPublisher || PUBLISHER;
  const commentPublisher = options.commentPublisher || PUBLISHER;
  const commentBody = options.commentBody || attestation(
    options.commentDigest || statusDigest,
    options.commentOverrides,
  );
  const statuses = CONTEXTS.map((context, index) => {
    const runtime = context.split("/")[1].replace(/^real-/, "");
    return {
      context,
      state: "success",
      creator: { login: statusPublisher },
      description: `Real ${runtime} runtime receipt sha256:${statusDigest}`,
      target_url: index === 0 ? firstTarget : secondTarget,
    };
  });
  const comment = {
    id: Number(COMMENT_ID),
    html_url: options.commentUrl || COMMENT_URL,
    commit_id: options.commentCommit || SHA,
    user: { login: commentPublisher },
    body: commentBody,
  };
  return {
    GH_USER_JSON: JSON.stringify({ login: options.authenticatedUser || PUBLISHER }),
    GH_PUBLISH_COMMENT_JSON: JSON.stringify(comment),
    GH_STATUSES_JSON: JSON.stringify(statuses),
    GH_COMMENT_JSON: JSON.stringify(comment),
  };
}

function run(arguments_, value = receipt(), options = {}) {
  const contents = JSON.stringify(value);
  writeFileSync(receiptPath, contents);
  writeFileSync(callsPath, "");
  const result = spawnSync(process.execPath, [script.pathname, ...arguments_], {
    encoding: "utf8",
    env: {
      ...process.env,
      PATH: `${root}:${process.env.PATH}`,
      GH_CALLS: callsPath,
      ...fixtures(digest(contents), options),
    },
  });
  return {
    ...result,
    payload: JSON.parse(result.stdout),
    calls: readFileSync(callsPath, "utf8").trim().split("\n")
      .filter(Boolean).map((line) => JSON.parse(line)),
  };
}

try {
  assert.match(
    ciWorkflow,
    /AGENTOPS_REAL_EVIDENCE_SHA: \$\{\{ github\.event_name == 'pull_request' && github\.event\.pull_request\.head\.sha \|\| github\.sha \}\}/,
  );
  assert.match(ciWorkflow, /test "\$\(git rev-parse HEAD\)" = "\$GITHUB_SHA"/);
  assert.match(ciWorkflow, /--sha "\$AGENTOPS_REAL_EVIDENCE_SHA"/);
  assert.doesNotMatch(
    ciWorkflow,
    /commercial-runtime-status\.mjs verify[\s\S]{0,220}--sha "\$GITHUB_SHA"/,
  );
  writeFileSync(fakeGh, `#!/usr/bin/env node
const fs = require("node:fs");
const args = process.argv.slice(2);
fs.appendFileSync(process.env.GH_CALLS, JSON.stringify(args) + "\\n");
const endpoint = args[1] || "";
let response = "{}";
if (args[0] === "api" && endpoint === "user") response = process.env.GH_USER_JSON;
else if (endpoint.includes("/statuses?per_page=100")) response = process.env.GH_STATUSES_JSON;
else if (endpoint.includes("/commits/") && endpoint.endsWith("/comments")) response = process.env.GH_PUBLISH_COMMENT_JSON;
else if (/\\/comments\\/[0-9]+$/.test(endpoint)) response = process.env.GH_COMMENT_JSON;
process.stdout.write(response + "\\n");
`);
  chmodSync(fakeGh, 0o755);

  const valid = run(["validate", "--receipt", receiptPath, "--sha", SHA]);
  assert.equal(valid.status, 0);
  assert.equal(valid.payload.ok, true);
  assert.equal(valid.payload.provider_signed_attestation, false);
  assert.equal(valid.payload.receipt_sha256,
    digest(JSON.stringify(receipt())));
  assert.equal(valid.payload.evidence.hermes.provider_call_performed, true);
  assert.equal(valid.payload.evidence.openclaw.provider_transport, "unix_socket");
  assert.equal(
    valid.payload.evidence.openclaw.provider_service_cleanup_verified,
    true,
  );

  const published = run([
    "publish", "--receipt", receiptPath, "--sha", SHA, "--repo", REPOSITORY,
  ]);
  assert.equal(published.status, 0);
  assert.equal(published.payload.publisher, PUBLISHER);
  assert.match(published.payload.receipt_sha256, /^[a-f0-9]{64}$/);
  assert.equal(published.payload.attestation_url, COMMENT_URL);
  const commentCall = published.calls.find((call) => call[1]?.endsWith("/comments"));
  assert.ok(commentCall);
  const bodyField = commentCall.find((field) => field.startsWith("body="));
  assert.equal(bodyField, `body=${attestation(published.payload.receipt_sha256)}`);
  assert.ok(!bodyField.includes("run_gw_"));
  const statusCalls = published.calls.filter((call) => call[1]?.includes(`/statuses/${SHA}`));
  assert.equal(statusCalls.length, 2);
  for (const call of statusCalls) {
    assert.ok(call.includes(`target_url=${COMMENT_URL}`));
    assert.ok(call.some((field) => field.endsWith(published.payload.receipt_sha256)));
  }

  const verified = run([
    "verify", "--sha", SHA, "--repo", REPOSITORY, "--publisher", PUBLISHER,
  ]);
  assert.equal(verified.status, 0);
  assert.equal(verified.payload.publisher, PUBLISHER);
  assert.equal(verified.payload.contexts["agentops/real-hermes"], "success");
  assert.equal(verified.payload.attestation_url, COMMENT_URL);

  const missingPublisher = run(["verify", "--sha", SHA, "--repo", REPOSITORY]);
  assert.equal(missingPublisher.status, 1);
  assert.equal(missingPublisher.payload.error, "runtime_status_publisher_required");

  const wrongPublisher = run(
    ["verify", "--sha", SHA, "--repo", REPOSITORY, "--publisher", PUBLISHER],
    receipt(),
    { statusPublisher: "attacker" },
  );
  assert.equal(wrongPublisher.status, 1);
  assert.equal(wrongPublisher.payload.error, "runtime_status_publisher_mismatch");

  const forgedTarget = run(
    ["verify", "--sha", SHA, "--repo", REPOSITORY, "--publisher", PUBLISHER],
    receipt(),
    { firstTarget: `https://github.com/attacker/repo/commit/${SHA}#commitcomment-42` },
  );
  assert.equal(forgedTarget.status, 1);
  assert.equal(forgedTarget.payload.error, "runtime_status_comment_target_invalid");

  const forgedComment = run(
    ["verify", "--sha", SHA, "--repo", REPOSITORY, "--publisher", PUBLISHER],
    receipt(),
    { commentOverrides: { contexts: [CONTEXTS[0], "agentops/forged"] } },
  );
  assert.equal(forgedComment.status, 1);
  assert.equal(forgedComment.payload.error, "runtime_status_comment_attestation_invalid");

  const forgedDigest = run(
    ["verify", "--sha", SHA, "--repo", REPOSITORY, "--publisher", PUBLISHER],
    receipt(),
    { commentDigest: "b".repeat(64) },
  );
  assert.equal(forgedDigest.status, 1);
  assert.equal(forgedDigest.payload.error, "runtime_status_comment_attestation_invalid");

  const wrongCommitComment = run(
    ["verify", "--sha", SHA, "--repo", REPOSITORY, "--publisher", PUBLISHER],
    receipt(),
    { commentCommit: "b".repeat(40) },
  );
  assert.equal(wrongCommitComment.status, 1);
  assert.equal(
    wrongCommitComment.payload.error,
    "runtime_status_comment_attestation_invalid",
  );

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

  const argvCredentialReceipt = receipt();
  argvCredentialReceipt.postgres_dsn_source = "argument";
  argvCredentialReceipt.postgres_dsn_argv_omitted = false;
  const argvCredential = run(
    ["validate", "--receipt", receiptPath, "--sha", SHA],
    argvCredentialReceipt,
  );
  assert.equal(argvCredential.status, 1);
  assert.equal(
    argvCredential.payload.error,
    "runtime_status_receipt_shared_evidence_invalid",
  );

  const retainedCredentialFilesReceipt = receipt();
  retainedCredentialFilesReceipt.ephemeral_credential_files_removed = false;
  const retainedCredentialFiles = run(
    ["validate", "--receipt", receiptPath, "--sha", SHA],
    retainedCredentialFilesReceipt,
  );
  assert.equal(retainedCredentialFiles.status, 1);
  assert.equal(
    retainedCredentialFiles.payload.error,
    "runtime_status_receipt_shared_evidence_invalid",
  );

  const overclaimedIsolationReceipt = receipt();
  overclaimedIsolationReceipt.same_uid_os_credential_isolation_claimed = true;
  const overclaimedIsolation = run(
    ["validate", "--receipt", receiptPath, "--sha", SHA],
    overclaimedIsolationReceipt,
  );
  assert.equal(overclaimedIsolation.status, 1);
  assert.equal(
    overclaimedIsolation.payload.error,
    "runtime_status_receipt_shared_evidence_invalid",
  );

  const descendantStillRunningReceipt = receipt();
  descendantStillRunningReceipt.next_process_stop.process_group_empty = false;
  const descendantStillRunning = run(
    ["validate", "--receipt", receiptPath, "--sha", SHA],
    descendantStillRunningReceipt,
  );
  assert.equal(descendantStillRunning.status, 1);
  assert.equal(
    descendantStillRunning.payload.error,
    "runtime_status_receipt_shared_evidence_invalid",
  );

  const directOpenClawReceipt = receipt();
  directOpenClawReceipt.openclaw_provider_transport = null;
  const directOpenClaw = run(
    ["validate", "--receipt", receiptPath, "--sha", SHA],
    directOpenClawReceipt,
  );
  assert.equal(directOpenClaw.status, 1);
  assert.equal(
    directOpenClaw.payload.error,
    "runtime_status_receipt_shared_evidence_invalid",
  );

  const uncleanProviderReceipt = receipt();
  uncleanProviderReceipt.provider_services.openclaw.provider_socket_removed = false;
  const uncleanProvider = run(
    ["validate", "--receipt", receiptPath, "--sha", SHA],
    uncleanProviderReceipt,
  );
  assert.equal(uncleanProvider.status, 1);
  assert.equal(
    uncleanProvider.payload.error,
    "runtime_status_receipt_shared_evidence_invalid",
  );

  const unboundRuntimeReceipt = receipt();
  delete unboundRuntimeReceipt.runtime_dependency_identity.openclaw_binary_sha256;
  const unboundRuntime = run(
    ["validate", "--receipt", receiptPath, "--sha", SHA],
    unboundRuntimeReceipt,
  );
  assert.equal(unboundRuntime.status, 1);
  assert.equal(
    unboundRuntime.payload.error,
    "runtime_status_receipt_shared_evidence_invalid",
  );

  process.stdout.write(`${JSON.stringify({
    ok: true,
    contract: "agentops_commercial_runtime_exact_head_status_contract_v3",
    exact_sha_bound: true,
    receipt_sha256_bound: true,
    publisher_bound: true,
    commit_comment_attestation_bound: true,
    repository_owner_trust_model_explicit: true,
    provider_signed_attestation_claimed: false,
    real_provider_required: true,
    openclaw_sidecar_receipt_required: true,
    openclaw_runtime_identity_required: true,
    typescript_worker_required: true,
    postgres_dsn_owner_only_file_required: true,
    postgres_dsn_argv_omission_required: true,
    direct_child_database_credentials_omitted: true,
    credential_file_cleanup_required: true,
    same_uid_isolation_overclaim_rejected: true,
    next_process_group_shutdown_required: true,
    hermes_openclaw_contexts_required: true,
    credentials_omitted: true,
  })}\n`);
} finally {
  rmSync(root, { recursive: true, force: true });
}
