#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const CONTRACT = "agentops_commercial_runtime_exact_head_status_v1";
const CONTEXTS = Object.freeze({
  hermes: "agentops/real-hermes",
  openclaw: "agentops/real-openclaw",
});

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function argumentsMap(values) {
  const result = { command: values[0] || "" };
  for (let index = 1; index < values.length; index += 1) {
    const name = values[index];
    if (!name.startsWith("--") || index + 1 >= values.length) {
      fail("runtime_status_argument_invalid");
    }
    result[name.slice(2).replaceAll("-", "_")] = values[index + 1];
    index += 1;
  }
  return result;
}

function exactSha(value) {
  const sha = String(value || "").trim().toLowerCase();
  if (!/^[a-f0-9]{40}$/.test(sha)) fail("runtime_status_exact_sha_required");
  return sha;
}

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function validateReceipt(path, sha) {
  let receipt;
  try {
    receipt = JSON.parse(readFileSync(path, "utf8"));
  } catch {
    fail("runtime_status_receipt_invalid");
  }
  const workers = object(receipt.workers);
  const reviews = object(receipt.human_reviews);
  const adapters = Array.isArray(receipt.adapters) ? receipt.adapters : [];
  const sharedChecks = [
    receipt.ok === true,
    receipt.contract === "nextjs_postgres_real_worker_human_review_v5",
    String(receipt.source_commit || "").toLowerCase() === sha,
    receipt.tracked_worktree_clean === true,
    receipt.tracked_worktree_unchanged === true,
    receipt.next_artifact_identity_verified === true,
    receipt.worker_implementation === "typescript",
    receipt.typescript_worker_started === true,
    receipt.python_worker_started === false,
    receipt.python_api_started === false,
    receipt.real_runtime_execution_performed === true,
    receipt.manifest_authority_guards_passed === true,
    receipt.real_run_bound_delivery_decisions_completed === true,
    receipt.worker_created_delivery_approvals === true,
    receipt.run_cost_reservations_settled === true,
    receipt.fixture_cleanup_verified_before_success === true,
    Object.keys(CONTEXTS).every((runtime) => adapters.includes(runtime)),
  ];
  if (sharedChecks.some((passed) => !passed)) {
    fail("runtime_status_receipt_shared_evidence_invalid");
  }
  const evidence = {};
  for (const runtime of Object.keys(CONTEXTS)) {
    const worker = object(workers[runtime]);
    const review = object(reviews[runtime]);
    if (
      !String(worker.run_id || "").startsWith("run_gw_")
      || !String(worker.manifest_id || "").startsWith("pem_")
      || worker.provider_call_performed !== true
      || worker.dry_run !== false
      || worker.cost_reservation_settled !== true
      || worker.delivery_approval_request_outcome !== "created"
      || review.delivery_approval_first_outcome !== "updated"
      || review.delivery_approval_replay_outcome !== "unchanged"
      || review.delivery_manifest_gate_passed !== true
    ) {
      fail(`runtime_status_${runtime}_evidence_invalid`);
    }
    evidence[runtime] = {
      context: CONTEXTS[runtime],
      run_id: worker.run_id,
      manifest_id: worker.manifest_id,
      provider_call_performed: true,
      dry_run: false,
      delivery_review_completed: true,
      cost_reservation_settled: true,
    };
  }
  return evidence;
}

function gh(arguments_) {
  const result = spawnSync("gh", arguments_, { encoding: "utf8" });
  if (result.status !== 0) fail("runtime_status_github_request_failed");
  return result.stdout.trim();
}

function repository(value) {
  const candidate = String(value || "").trim()
    || gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]);
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(candidate)) {
    fail("runtime_status_repository_invalid");
  }
  return candidate;
}

function publish(repo, sha, targetUrl) {
  for (const [runtime, context] of Object.entries(CONTEXTS)) {
    const fields = [
      "api", `repos/${repo}/statuses/${sha}`,
      "-f", "state=success",
      "-f", `context=${context}`,
      "-f", `description=Real ${runtime} TypeScript/Postgres acceptance passed`,
    ];
    if (targetUrl) fields.push("-f", `target_url=${targetUrl}`);
    gh(fields);
  }
}

function verify(repo, sha) {
  let statuses;
  try {
    statuses = JSON.parse(gh([
      "api", `repos/${repo}/commits/${sha}/statuses?per_page=100`,
    ]));
  } catch {
    fail("runtime_status_github_response_invalid");
  }
  if (!Array.isArray(statuses)) fail("runtime_status_github_response_invalid");
  const contexts = {};
  for (const context of Object.values(CONTEXTS)) {
    const latest = statuses.find((status) => status?.context === context);
    contexts[context] = latest?.state || "missing";
    if (latest?.state !== "success") fail("runtime_status_exact_head_context_missing");
  }
  return contexts;
}

function output(value) {
  process.stdout.write(`${JSON.stringify({
    contract: CONTRACT,
    credentials_omitted: true,
    raw_runtime_output_omitted: true,
    ...value,
  })}\n`);
}

try {
  const args = argumentsMap(process.argv.slice(2));
  const sha = exactSha(args.sha);
  if (args.command === "validate") {
    output({ ok: true, operation: "validate", source_commit: sha,
      evidence: validateReceipt(args.receipt, sha) });
  } else if (args.command === "publish") {
    const evidence = validateReceipt(args.receipt, sha);
    const repo = repository(args.repo);
    publish(repo, sha, String(args.target_url || "").trim());
    output({ ok: true, operation: "publish", source_commit: sha, repository: repo,
      contexts: Object.values(CONTEXTS), evidence });
  } else if (args.command === "verify") {
    const repo = repository(args.repo);
    output({ ok: true, operation: "verify", source_commit: sha, repository: repo,
      contexts: verify(repo, sha) });
  } else {
    fail("runtime_status_command_invalid");
  }
} catch (error) {
  output({ ok: false, error: typeof error?.code === "string"
    ? error.code : "runtime_status_unexpected_failure" });
  process.exitCode = 1;
}
