#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile, link } from "node:fs/promises";
import { chmodSync, lstatSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  canonicalExecutorRequestBytes,
  EXECUTOR_REQUEST_SCHEMA,
  ExecutorReplayJournal,
  executorDispatchJournalPath,
  executorNonceJournalPath,
  executorRequestJournalPath,
  MAX_EXECUTOR_REQUEST_BYTES,
  parseCanonicalExecutorRequest,
  validateExecutorJournalEntryMetadata,
  validateExecutorJournalRootMetadata,
} from "./openclaw-executor-request.mjs";

const self = fileURLToPath(import.meta.url);
const digest = (character) => character.repeat(64);
const bootId = "123e4567-e89b-42d3-a456-426614174000";
const now = "1000000000";
const deadline = "9000000000";
const expected = { boot_id: bootId, now_boottime_ns: now };
const owner = { uid: process.getuid?.() ?? 0, gid: process.getgid?.() ?? 0 };

function request(overrides = {}) {
  return {
    boot_id: bootId,
    deadline_boottime_ns: deadline,
    isolation_policy_sha256: digest("4"),
    nonce: "nonce_contract_001",
    prompt_sha256: digest("2"),
    request_id: "req_contract_001",
    run_id: "run_gw_contract_001",
    runtime_manifest_sha256: digest("3"),
    schema: EXECUTOR_REQUEST_SCHEMA,
    workspace_id_hash: digest("1"),
    ...overrides,
  };
}

async function fixture() {
  const parent = await mkdtemp(join(tmpdir(), "agentops-executor-journal-"));
  const root = join(parent, "journal");
  await mkdir(root, { mode: 0o700 });
  chmodSync(root, 0o700);
  return { parent, root };
}

async function journal(root, durabilityPoint) {
  return ExecutorReplayJournal.open(root, { expectedOwner: owner, durabilityPoint });
}

function runChild(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [self, ...args], { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code, signal) => resolve({ code, signal, stdout, stderr }));
  });
}

if (process.argv[2] === "--reserve-child") {
  const [, , , root, encoded, crashPoint = ""] = process.argv;
  const body = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8"));
  const store = await journal(root, (point) => {
    if (point === crashPoint) process.exit(91);
  });
  try {
    const record = await store.reserve(canonicalExecutorRequestBytes(body), expected);
    process.stdout.write(`${JSON.stringify({ ok: true, state: record.state })}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ ok: false, error: error.code })}\n`);
    process.exitCode = 2;
  }
} else if (process.argv[2] === "--dispatch-child") {
  const [, , , root, requestId, crashPoint = ""] = process.argv;
  const store = await journal(root, (point) => {
    if (point === crashPoint) process.exit(92);
  });
  try {
    const record = await store.markDispatched(requestId, { ...expected, now_boottime_ns: "2000000000" });
    process.stdout.write(`${JSON.stringify({ ok: true, state: record.state })}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ ok: false, error: error.code })}\n`);
    process.exitCode = 2;
  }
} else {
  const fixtures = [];
  try {
    assert.deepEqual(
      canonicalExecutorRequestBytes({ z: 1, a: { y: false, b: "value" } }),
      Buffer.from('{"a":{"b":"value","y":false},"z":1}'),
    );
    const bytes = canonicalExecutorRequestBytes(request());
    assert.deepEqual(parseCanonicalExecutorRequest(bytes, expected), request());
    for (const [body, failure] of [
      [{ ...request(), raw_prompt: "forbidden" }, /executor_request_fields_invalid/],
      [{ ...request(), raw_response: "forbidden" }, /executor_request_fields_invalid/],
      [request({ boot_id: "not-a-boot-id" }), /executor_request_boot_id_invalid/],
      [request({ deadline_boottime_ns: now }), /executor_request_deadline_expired/],
      [request({ workspace_id_hash: "../escape" }), /workspace_id_hash_invalid/],
      [request({ request_id: "../escape" }), /executor_request_id_invalid/],
    ]) assert.throws(() => parseCanonicalExecutorRequest(canonicalExecutorRequestBytes(body), expected), failure);
    assert.throws(
      () => parseCanonicalExecutorRequest(Buffer.from(` ${bytes}`), expected),
      /executor_request_encoding_noncanonical/,
    );
    assert.throws(
      () => parseCanonicalExecutorRequest(
        Buffer.from(bytes.toString().replace('"schema":', '"schema":"duplicate","schema":')),
        expected,
      ),
      /executor_request_encoding_noncanonical/,
    );
    assert.throws(
      () => parseCanonicalExecutorRequest(Buffer.alloc(MAX_EXECUTOR_REQUEST_BYTES + 1), expected),
      /executor_request_size_invalid/,
    );
    assert.throws(
      () => parseCanonicalExecutorRequest(bytes, { ...expected, boot_id: "223e4567-e89b-42d3-a456-426614174000" }),
      /executor_request_boot_id_mismatch/,
    );

    const rootMetadata = {
      dev: 1, gid: 0, ino: 2, mode: 0o40700, nlink: 2, uid: 0,
      isDirectory: () => true, isSymbolicLink: () => false,
    };
    assert.deepEqual(validateExecutorJournalRootMetadata(rootMetadata), {
      dev: 1, gid: 0, ino: 2, mode: 0o700, uid: 0,
    });
    assert.throws(
      () => validateExecutorJournalRootMetadata({ ...rootMetadata, uid: 1 }),
      /executor_journal_root_owner_invalid/,
    );
    assert.throws(
      () => validateExecutorJournalRootMetadata({ ...rootMetadata, mode: 0o40750 }),
      /executor_journal_root_mode_invalid/,
    );
    const entryMetadata = {
      dev: 1, gid: 0, ino: 3, mode: 0o100600, nlink: 1, uid: 0,
      isFIFO: () => false, isFile: () => true, isSymbolicLink: () => false,
    };
    assert.throws(
      () => validateExecutorJournalEntryMetadata({ ...entryMetadata, isFIFO: () => true }),
      /executor_journal_entry_fifo_rejected/,
    );
    assert.throws(
      () => validateExecutorJournalEntryMetadata({ ...entryMetadata, nlink: 2 }),
      /executor_journal_entry_hardlink_rejected/,
    );

    const basic = await fixture(); fixtures.push(basic.parent);
    const durabilityEvents = [];
    const store = await journal(basic.root, (point) => durabilityEvents.push(point));
    const prepared = await store.reserve(bytes, expected);
    assert.equal(prepared.state, "prepared");
    assert.equal(prepared.real_runtime_process_spawned, false);
    assert.equal(prepared.runtime_receipt_verified, false);
    assert.equal(prepared.hostile_runtime_isolation_verified, false);
    assert.equal(lstatSync(basic.root).mode & 0o7777, 0o700);
    assert.equal(lstatSync(executorRequestJournalPath(basic.root, request().request_id)).mode & 0o7777, 0o600);
    assert.equal(lstatSync(executorNonceJournalPath(basic.root, request().nonce)).mode & 0o7777, 0o600);
    await assert.rejects(() => store.reserve(bytes, expected), /executor_journal_request_replayed/);
    const dispatched = await store.markDispatched(
      request().request_id,
      { ...expected, now_boottime_ns: "2000000000" },
    );
    assert.equal(dispatched.state, "dispatched");
    assert.equal(lstatSync(executorDispatchJournalPath(basic.root, request().request_id)).mode & 0o7777, 0o600);
    await assert.rejects(
      () => store.markDispatched(request().request_id, { ...expected, now_boottime_ns: "2100000000" }),
      /not_executable/,
    );
    const recoveredDispatch = await (await journal(
      basic.root,
      (point) => durabilityEvents.push(point),
    )).recover({ ...expected, now_boottime_ns: "2200000000" });
    assert.deepEqual(recoveredDispatch.uncertain, [request().request_id]);
    assert.equal((await store.read(request().request_id)).state, "uncertain");
    await assert.rejects(
      () => store.markDispatched(request().request_id, { ...expected, now_boottime_ns: "2300000000" }),
      /not_executable/,
    );
    await assert.rejects(
      () => store.markTerminal(request().request_id, "2400000000", "failed"),
      /transition_invalid/,
    );
    assert.deepEqual(durabilityEvents, [
      "request_reserved",
      "nonce_reserved",
      "dispatch_reserved",
      "state_dispatched_durable",
      "state_uncertain_durable",
    ]);
    await assert.rejects(
      () => store.markDispatched(request().request_id, { ...expected, now_boottime_ns: "2500000000" }),
      /not_executable/,
    );

    const rootLinkFixture = await fixture(); fixtures.push(rootLinkFixture.parent);
    const linkedRoot = join(rootLinkFixture.parent, "journal-link");
    await symlink(rootLinkFixture.root, linkedRoot);
    await assert.rejects(
      () => ExecutorReplayJournal.open(linkedRoot, { expectedOwner: owner }),
      /executor_journal_root_noncanonical/,
    );

    const concurrent = await fixture(); fixtures.push(concurrent.parent);
    const encoded = Buffer.from(JSON.stringify(request())).toString("base64url");
    const contenders = await Promise.all(Array.from({ length: 12 }, () => (
      runChild(["--reserve-child", concurrent.root, encoded])
    )));
    assert.equal(contenders.filter((result) => result.code === 0).length, 1);
    assert.equal(
      contenders.filter((result) => result.stdout.includes("executor_journal_request_replayed")).length,
      11,
      JSON.stringify(contenders),
    );

    const nonceRace = await fixture(); fixtures.push(nonceRace.parent);
    const nonceContenders = await Promise.all(Array.from({ length: 12 }, (_, index) => (
      runChild(["--reserve-child", nonceRace.root, Buffer.from(JSON.stringify(request({
        request_id: `req_nonce_race_${String(index).padStart(2, "0")}`,
      }))).toString("base64url")])
    )));
    assert.equal(nonceContenders.filter((result) => result.code === 0).length, 1);
    assert.equal(
      nonceContenders.filter((result) => result.stdout.includes("executor_journal_nonce_replayed")).length,
      11,
      JSON.stringify(nonceContenders),
    );

    const dispatchRace = await fixture(); fixtures.push(dispatchRace.parent);
    await (await journal(dispatchRace.root)).reserve(bytes, expected);
    const dispatchContenders = await Promise.all(Array.from({ length: 12 }, () => (
      runChild(["--dispatch-child", dispatchRace.root, request().request_id])
    )));
    assert.equal(dispatchContenders.filter((result) => result.code === 0).length, 1);
    const dispatchFailures = dispatchContenders.filter((result) => result.code !== 0);
    assert.equal(dispatchFailures.length, 11, JSON.stringify(dispatchContenders));
    assert.equal(dispatchFailures.every((result) => (
      result.stdout.includes("executor_journal_not_executable")
      || result.stdout.includes("executor_journal_stale_transition")
    )), true, JSON.stringify(dispatchContenders));

    const terminalContenders = await Promise.all(Array.from({ length: 12 }, async () => {
      try {
        return await (await journal(dispatchRace.root)).markTerminal(
          request().request_id,
          "3000000000",
          "completed",
        );
      } catch (error) {
        return { error: error.code };
      }
    }));
    assert.equal(terminalContenders.filter((result) => result.state === "terminal").length, 1);
    assert.equal(
      terminalContenders.filter((result) => [
        "executor_journal_stale_transition",
        "executor_journal_transition_invalid",
      ].includes(result.error)).length,
      11,
      JSON.stringify(terminalContenders),
    );

    const illegalTerminal = await fixture(); fixtures.push(illegalTerminal.parent);
    const illegalStore = await journal(illegalTerminal.root);
    await illegalStore.reserve(bytes, expected);
    await assert.rejects(
      () => illegalStore.markTerminal(request().request_id, "2000000000", "completed"),
      /transition_invalid/,
    );
    await assert.rejects(
      () => illegalStore.markTerminal(request().request_id, "9999999999", "cancelled"),
      /terminal_time_invalid/,
    );

    const crashRequest = await fixture(); fixtures.push(crashRequest.parent);
    const crashedBeforeNonce = await runChild([
      "--reserve-child", crashRequest.root, encoded, "request_reserved",
    ]);
    assert.equal(crashedBeforeNonce.code, 91);
    const recoveredPrepared = await (await journal(crashRequest.root)).recover(expected);
    assert.deepEqual(recoveredPrepared.prepared, [request().request_id]);
    assert.equal((await (await journal(crashRequest.root)).read(request().request_id)).state, "prepared");

    const crashNonce = await fixture(); fixtures.push(crashNonce.parent);
    const crashedAfterNonce = await runChild([
      "--reserve-child", crashNonce.root, encoded, "nonce_reserved",
    ]);
    assert.equal(crashedAfterNonce.code, 91);
    assert.deepEqual((await (await journal(crashNonce.root)).recover(expected)).prepared, [request().request_id]);

    const rebootDispatch = await fixture(); fixtures.push(rebootDispatch.parent);
    await (await journal(rebootDispatch.root)).reserve(bytes, expected);
    await assert.rejects(
      () => (journal(rebootDispatch.root)).then((value) => value.markDispatched(
        request().request_id,
        { boot_id: "223e4567-e89b-42d3-a456-426614174000", now_boottime_ns: "1" },
      )),
      /executor_journal_not_executable/,
    );

    const crashDispatch = await fixture(); fixtures.push(crashDispatch.parent);
    await (await journal(crashDispatch.root)).reserve(bytes, expected);
    const crashedAfterDispatchClaim = await runChild([
      "--dispatch-child", crashDispatch.root, request().request_id, "dispatch_reserved",
    ]);
    assert.equal(crashedAfterDispatchClaim.code, 92);
    assert.equal(lstatSync(executorDispatchJournalPath(crashDispatch.root, request().request_id)).isFile(), true);
    assert.deepEqual((await (await journal(crashDispatch.root)).recover(expected)).uncertain, [request().request_id]);
    assert.equal((await (await journal(crashDispatch.root)).read(request().request_id)).state, "uncertain");

    const bootRecovery = await fixture(); fixtures.push(bootRecovery.parent);
    await (await journal(bootRecovery.root)).reserve(bytes, expected);
    const nextBoot = { boot_id: "223e4567-e89b-42d3-a456-426614174000", now_boottime_ns: "1" };
    assert.deepEqual((await (await journal(bootRecovery.root)).recover(nextBoot)).terminal, [request().request_id]);
    assert.equal((await (await journal(bootRecovery.root)).read(request().request_id)).terminal_outcome, "abandoned_boot");

    const attacks = await fixture(); fixtures.push(attacks.parent);
    const attackStore = await journal(attacks.root);
    const requestPath = executorRequestJournalPath(attacks.root, request().request_id);
    const outside = join(attacks.parent, "outside");
    await writeFile(outside, "outside", { mode: 0o600 });
    await symlink(outside, requestPath);
    await assert.rejects(() => attackStore.reserve(bytes, expected), /executor_journal_entry_symlink_rejected/);
    await rm(requestPath);
    await writeFile(requestPath, "hardlink", { mode: 0o600 });
    await link(requestPath, join(attacks.parent, "second-link"));
    await assert.rejects(() => attackStore.reserve(bytes, expected), /executor_journal_entry_hardlink_rejected/);
    await rm(requestPath);
    assert.throws(() => executorRequestJournalPath("../relative", "request"), /root_path_invalid/);
    assert.throws(() => executorRequestJournalPath(`${attacks.root}/../escape`, "request"), /root_path_invalid/);
    assert.throws(() => executorNonceJournalPath(attacks.root, "../nonce"), /executor_request_nonce_invalid/);

    const rawJournal = await readFile(executorRequestJournalPath(basic.root, request().request_id), "utf8");
    assert.equal(rawJournal.includes("raw_prompt"), false);
    assert.equal(rawJournal.includes("raw_response"), false);

    process.stdout.write(`${JSON.stringify({
      contract: "agentops_openclaw_root_executor_request_a07_lane_a_v1",
      canonical_request_v2_verified: true,
      exact_bounded_wire_verified: true,
      boot_and_absolute_boottime_deadline_bound: true,
      root_owned_directory_metadata_abstraction_verified: true,
      atomic_request_and_nonce_reservation_verified: true,
      child_process_request_concurrency_verified: true,
      child_process_nonce_concurrency_verified: true,
      child_process_dispatch_exclusivity_verified: true,
      crash_restart_recovery_verified: true,
      irreversible_dispatch_and_uncertain_states_verified: true,
      symlink_fifo_hardlink_path_traversal_rejected: true,
      file_and_directory_fsync_paths_exercised: true,
      raw_prompt_response_omitted: true,
      real_runtime_process_spawned: false,
      runtime_receipt_verified: false,
      hostile_runtime_isolation_verified: false,
    })}\n`);
  } finally {
    await Promise.all(fixtures.map((path) => rm(path, { recursive: true, force: true })));
  }
}
