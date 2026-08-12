#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";

const CONTRACT = "agentops_commercial_runtime_exact_head_status_v1";
const CONTEXTS = Object.freeze({
  hermes: "agentops/real-hermes",
  openclaw: "agentops/real-openclaw",
});
const CONTEXT_VALUES = Object.freeze(Object.values(CONTEXTS));

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
  let contents;
  let receipt;
  try {
    contents = readFileSync(path);
    receipt = JSON.parse(contents.toString("utf8"));
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
  return {
    evidence,
    receipt_sha256: createHash("sha256").update(contents).digest("hex"),
  };
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

function login(value, error = "runtime_status_publisher_required") {
  const candidate = String(value || "").trim();
  if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/.test(candidate)) fail(error);
  return candidate;
}

function githubJson(arguments_, error = "runtime_status_github_response_invalid") {
  try {
    return JSON.parse(gh(arguments_));
  } catch {
    fail(error);
  }
}

function statusDescription(runtime, digest) {
  return `Real ${runtime} runtime receipt sha256:${digest}`;
}

function attestation(sha, digest) {
  return {
    contract: CONTRACT,
    source_commit: sha,
    receipt_sha256: digest,
    contexts: CONTEXT_VALUES,
  };
}

function attestationBody(sha, digest) {
  return JSON.stringify(attestation(sha, digest));
}

function commentTarget(repo, sha, value) {
  let url;
  try {
    url = new URL(String(value || ""));
  } catch {
    fail("runtime_status_comment_target_invalid");
  }
  const expectedPath = `/${repo}/commit/${sha}`.toLowerCase();
  const match = /^#commitcomment-([1-9][0-9]*)$/.exec(url.hash);
  if (
    url.protocol !== "https:"
    || url.hostname.toLowerCase() !== "github.com"
    || url.port !== ""
    || url.username !== ""
    || url.password !== ""
    || url.search !== ""
    || url.pathname.toLowerCase() !== expectedPath
    || !match
  ) {
    fail("runtime_status_comment_target_invalid");
  }
  return { id: match[1], url: url.toString() };
}

function publish(repo, sha, digest) {
  const authenticated = githubJson(["api", "user"], "runtime_status_github_user_invalid");
  const publisher = login(authenticated?.login, "runtime_status_github_user_invalid");
  const body = attestationBody(sha, digest);
  const comment = githubJson([
    "api", `repos/${repo}/commits/${sha}/comments`,
    "-f", `body=${body}`,
  ]);
  const target = commentTarget(repo, sha, comment?.html_url);
  if (
    String(comment?.commit_id || "").toLowerCase() !== sha
    || String(comment?.user?.login || "").toLowerCase() !== publisher.toLowerCase()
    || comment?.body !== body
  ) {
    fail("runtime_status_comment_publish_invalid");
  }
  for (const [runtime, context] of Object.entries(CONTEXTS)) {
    const fields = [
      "api", `repos/${repo}/statuses/${sha}`,
      "-f", "state=success",
      "-f", `context=${context}`,
      "-f", `description=${statusDescription(runtime, digest)}`,
      "-f", `target_url=${target.url}`,
    ];
    gh(fields);
  }
  return { digest, publisher, targetUrl: target.url };
}

function verify(repo, sha, expectedPublisher) {
  const publisher = login(expectedPublisher);
  const statuses = githubJson([
    "api", `repos/${repo}/commits/${sha}/statuses?per_page=100`,
  ]);
  if (!Array.isArray(statuses)) fail("runtime_status_github_response_invalid");
  const contexts = {};
  let sharedTarget;
  let sharedDigest;
  for (const [runtime, context] of Object.entries(CONTEXTS)) {
    const latest = statuses.find((status) => status?.context === context);
    if (latest?.state !== "success") fail("runtime_status_exact_head_context_missing");
    if (String(latest?.creator?.login || "").toLowerCase() !== publisher.toLowerCase()) {
      fail("runtime_status_publisher_mismatch");
    }
    if (String(latest?.sha || "").toLowerCase() !== sha) {
      fail("runtime_status_status_sha_mismatch");
    }
    const description = String(latest?.description || "");
    const digestMatch = /^Real (hermes|openclaw) runtime receipt sha256:([a-f0-9]{64})$/.exec(description);
    if (!digestMatch || digestMatch[1] !== runtime) {
      fail("runtime_status_description_invalid");
    }
    const target = commentTarget(repo, sha, latest?.target_url);
    if (sharedTarget && sharedTarget.id !== target.id) fail("runtime_status_comment_target_mismatch");
    if (sharedDigest && sharedDigest !== digestMatch[2]) fail("runtime_status_receipt_digest_mismatch");
    sharedTarget = target;
    sharedDigest = digestMatch[2];
    contexts[context] = "success";
  }
  const comment = githubJson(["api", `repos/${repo}/comments/${sharedTarget.id}`]);
  if (
    String(comment?.user?.login || "").toLowerCase() !== publisher.toLowerCase()
    || String(comment?.commit_id || "").toLowerCase() !== sha
    || comment?.html_url !== sharedTarget.url
    || comment?.body !== attestationBody(sha, sharedDigest)
  ) {
    fail("runtime_status_comment_attestation_invalid");
  }
  return { contexts, publisher, receipt_sha256: sharedDigest,
    attestation_url: sharedTarget.url };
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
    const validated = validateReceipt(args.receipt, sha);
    output({ ok: true, operation: "validate", source_commit: sha,
      receipt_sha256: validated.receipt_sha256, evidence: validated.evidence });
  } else if (args.command === "publish") {
    const validated = validateReceipt(args.receipt, sha);
    const repo = repository(args.repo);
    const published = publish(repo, sha, validated.receipt_sha256);
    output({ ok: true, operation: "publish", source_commit: sha, repository: repo,
      contexts: CONTEXT_VALUES, publisher: published.publisher,
      receipt_sha256: published.digest, attestation_url: published.targetUrl,
      evidence: validated.evidence });
  } else if (args.command === "verify") {
    const repo = repository(args.repo);
    const verified = verify(repo, sha, args.publisher);
    output({ ok: true, operation: "verify", source_commit: sha, repository: repo,
      ...verified });
  } else {
    fail("runtime_status_command_invalid");
  }
} catch (error) {
  output({ ok: false, error: typeof error?.code === "string"
    ? error.code : "runtime_status_unexpected_failure" });
  process.exitCode = 1;
}
