#!/usr/bin/env node

import { createHash, randomBytes } from "node:crypto";
import {
  constants,
  lstat,
  link,
  open,
  readdir,
  realpath,
  unlink,
} from "node:fs/promises";
import { isAbsolute, join, resolve } from "node:path";

export const EXECUTOR_REQUEST_SCHEMA = "agentops.openclaw.executor.request.v2";
export const EXECUTOR_JOURNAL_SCHEMA = "agentops.openclaw.executor.journal.v1";
export const EXECUTOR_NONCE_SCHEMA = "agentops.openclaw.executor.nonce.v1";
export const EXECUTOR_DISPATCH_SCHEMA = "agentops.openclaw.executor.dispatch.v1";
export const MAX_EXECUTOR_REQUEST_BYTES = 8 * 1024;
export const MAX_EXECUTOR_JOURNAL_BYTES = 16 * 1024;

const REQUEST_FIELDS = [
  "boot_id",
  "deadline_boottime_ns",
  "isolation_policy_sha256",
  "nonce",
  "prompt_sha256",
  "request_id",
  "run_id",
  "runtime_manifest_sha256",
  "schema",
  "workspace_id_hash",
].sort();
const EXPECTED_FIELDS = ["boot_id", "now_boottime_ns"].sort();
const JOURNAL_FIELDS = [
  "body",
  "body_sha256",
  "dispatched_boottime_ns",
  "hostile_runtime_isolation_verified",
  "nonce_hash",
  "prepared_boottime_ns",
  "real_runtime_process_spawned",
  "request_id_hash",
  "runtime_receipt_verified",
  "schema",
  "state",
  "state_version",
  "terminal_boottime_ns",
  "terminal_outcome",
  "uncertainty_reason",
  "updated_boottime_ns",
].sort();
const NONCE_FIELDS = [
  "body_sha256",
  "nonce_hash",
  "request_id_hash",
  "schema",
].sort();
const DISPATCH_FIELDS = [
  "body_sha256",
  "dispatch_boottime_ns",
  "request_id_hash",
  "schema",
].sort();
const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const TOKEN_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const BOOT_ID_PATTERN = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
const DECIMAL_PATTERN = /^(?:0|[1-9][0-9]{0,19})$/;
const TERMINAL_OUTCOMES = new Set(["abandoned_boot", "cancelled", "completed", "expired", "failed"]);
const UNCERTAINTY_REASONS = new Set([
  "dispatch_recovery",
  "journal_corrupt",
  "nonce_conflict",
  "nonce_missing",
]);

function fail(code, cause) {
  const error = new Error(code, cause === undefined ? undefined : { cause });
  error.code = code;
  throw error;
}

function plainObject(value, code) {
  if (
    value === null
    || typeof value !== "object"
    || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype
  ) fail(code);
  return value;
}

function exactFields(value, expected, code) {
  const actual = Object.keys(value).sort();
  if (actual.length !== expected.length || actual.some((name, index) => name !== expected[index])) {
    fail(code);
  }
}

function token(value, label) {
  if (typeof value !== "string" || !TOKEN_PATTERN.test(value)) fail(`${label}_invalid`);
}

function sha256Value(value, label) {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) fail(`${label}_invalid`);
}

function decimal(value, label) {
  if (typeof value !== "string" || !DECIMAL_PATTERN.test(value)) fail(`${label}_invalid`);
  const parsed = BigInt(value);
  if (parsed > 18_446_744_073_709_551_615n) fail(`${label}_invalid`);
  return parsed;
}

function canonicalValue(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) fail("executor_request_canonical_number_invalid");
    return value;
  }
  if (Array.isArray(value)) return value.map(canonicalValue);
  const object = plainObject(value, "executor_request_canonical_object_invalid");
  return Object.fromEntries(Object.keys(object).sort().map((name) => [name, canonicalValue(object[name])]));
}

export function canonicalExecutorRequestBytes(value) {
  return Buffer.from(JSON.stringify(canonicalValue(value)), "utf8");
}

function digestBytes(value) {
  return createHash("sha256").update(value).digest("hex");
}

function digestText(value) {
  return digestBytes(Buffer.from(value, "utf8"));
}

function validateRequestBody(value) {
  const body = plainObject(value, "executor_request_body_invalid");
  exactFields(body, REQUEST_FIELDS, "executor_request_fields_invalid");
  if (body.schema !== EXECUTOR_REQUEST_SCHEMA) fail("executor_request_schema_invalid");
  token(body.request_id, "executor_request_id");
  token(body.run_id, "executor_request_run_id");
  token(body.nonce, "executor_request_nonce");
  sha256Value(body.workspace_id_hash, "executor_request_workspace_id_hash");
  sha256Value(body.prompt_sha256, "executor_request_prompt_sha256");
  sha256Value(body.runtime_manifest_sha256, "executor_request_manifest_sha256");
  sha256Value(body.isolation_policy_sha256, "executor_request_policy_sha256");
  if (typeof body.boot_id !== "string" || !BOOT_ID_PATTERN.test(body.boot_id)) {
    fail("executor_request_boot_id_invalid");
  }
  decimal(body.deadline_boottime_ns, "executor_request_deadline_boottime_ns");
  return body;
}

function validateExpectedClock(value) {
  const expected = plainObject(value, "executor_request_expected_invalid");
  exactFields(expected, EXPECTED_FIELDS, "executor_request_expected_fields_invalid");
  if (typeof expected.boot_id !== "string" || !BOOT_ID_PATTERN.test(expected.boot_id)) {
    fail("executor_request_expected_boot_id_invalid");
  }
  return {
    boot_id: expected.boot_id,
    now_boottime_ns: decimal(expected.now_boottime_ns, "executor_request_now_boottime_ns").toString(),
  };
}

export function parseCanonicalExecutorRequest(value, expectedValue) {
  if (!(Buffer.isBuffer(value) || value instanceof Uint8Array)) fail("executor_request_bytes_required");
  const bytes = Buffer.from(value);
  if (bytes.byteLength < 2 || bytes.byteLength > MAX_EXECUTOR_REQUEST_BYTES) {
    fail("executor_request_size_invalid");
  }
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch (error) {
    fail("executor_request_utf8_invalid", error);
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    fail("executor_request_json_invalid", error);
  }
  const body = validateRequestBody(parsed);
  if (!bytes.equals(canonicalExecutorRequestBytes(body))) fail("executor_request_encoding_noncanonical");
  const expected = validateExpectedClock(expectedValue);
  if (expected.boot_id !== body.boot_id) fail("executor_request_boot_id_mismatch");
  const now = BigInt(expected.now_boottime_ns);
  const deadline = decimal(body.deadline_boottime_ns, "executor_request_deadline_boottime_ns");
  if (deadline <= now) fail("executor_request_deadline_expired");
  return Object.freeze({ ...body });
}

function metadataShape(metadata, code) {
  if (metadata === null || typeof metadata !== "object") fail(code);
  for (const name of ["uid", "gid", "mode", "nlink", "dev", "ino"]) {
    if (!Number.isSafeInteger(Number(metadata[name]))) fail(code);
  }
  return metadata;
}

export function validateExecutorJournalRootMetadata(metadataValue, expectedValue = {}) {
  const metadata = metadataShape(metadataValue, "executor_journal_root_metadata_invalid");
  const expected = {
    uid: expectedValue.uid ?? 0,
    gid: expectedValue.gid ?? 0,
    mode: expectedValue.mode ?? 0o700,
  };
  if (typeof metadata.isDirectory !== "function" || !metadata.isDirectory()) {
    fail("executor_journal_root_not_directory");
  }
  if (typeof metadata.isSymbolicLink === "function" && metadata.isSymbolicLink()) {
    fail("executor_journal_root_symlink_rejected");
  }
  if (metadata.uid !== expected.uid || metadata.gid !== expected.gid) {
    fail("executor_journal_root_owner_invalid");
  }
  if ((metadata.mode & 0o7777) !== expected.mode) fail("executor_journal_root_mode_invalid");
  return Object.freeze({ dev: metadata.dev, ino: metadata.ino, ...expected });
}

export function validateExecutorJournalEntryMetadata(metadataValue, expectedValue = {}) {
  const metadata = metadataShape(metadataValue, "executor_journal_entry_metadata_invalid");
  const expectedUid = expectedValue.uid ?? 0;
  const expectedGid = expectedValue.gid ?? 0;
  if (typeof metadata.isSymbolicLink === "function" && metadata.isSymbolicLink()) {
    fail("executor_journal_entry_symlink_rejected");
  }
  if (typeof metadata.isFIFO === "function" && metadata.isFIFO()) {
    fail("executor_journal_entry_fifo_rejected");
  }
  if (typeof metadata.isFile !== "function" || !metadata.isFile()) {
    fail("executor_journal_entry_type_invalid");
  }
  if (metadata.nlink > 1) fail("executor_journal_entry_hardlink_rejected");
  if (metadata.nlink !== 1) fail("executor_journal_entry_identity_changed");
  if (metadata.uid !== expectedUid || metadata.gid !== expectedGid) {
    fail("executor_journal_entry_owner_invalid");
  }
  if ((metadata.mode & 0o7777) !== 0o600) fail("executor_journal_entry_mode_invalid");
  return Object.freeze({ dev: metadata.dev, ino: metadata.ino });
}

function canonicalRootPath(root) {
  if (typeof root !== "string" || !isAbsolute(root) || resolve(root) !== root) {
    fail("executor_journal_root_path_invalid");
  }
  if (root.length > 1 && root.endsWith("/")) fail("executor_journal_root_path_invalid");
  return root;
}

function entryPath(root, prefix, identifier, label) {
  token(identifier, label);
  return join(root, `${prefix}-${digestText(identifier)}.json`);
}

export function executorRequestJournalPath(root, requestId) {
  return entryPath(canonicalRootPath(root), "request", requestId, "executor_request_id");
}

export function executorNonceJournalPath(root, nonce) {
  return entryPath(canonicalRootPath(root), "nonce", nonce, "executor_request_nonce");
}

export function executorDispatchJournalPath(root, requestId) {
  return entryPath(canonicalRootPath(root), "dispatch", requestId, "executor_request_id");
}

export function executorRequestStatePath(root, requestId, version) {
  if (!Number.isSafeInteger(version) || version < 2 || version > 999_999_999) {
    fail("executor_journal_state_version_invalid");
  }
  token(requestId, "executor_request_id");
  return join(
    canonicalRootPath(root),
    `state-${digestText(requestId)}-v${String(version).padStart(9, "0")}.json`,
  );
}

async function syncDirectory(root) {
  const handle = await open(root, constants.O_RDONLY | (constants.O_DIRECTORY ?? 0));
  try {
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function writeExclusive(path, value, mode, durabilityPoint) {
  let handle;
  try {
    handle = await open(
      path,
      constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW ?? 0),
      mode,
    );
    await handle.chmod(mode);
    await handle.writeFile(canonicalExecutorRequestBytes(value));
    await handle.sync();
  } finally {
    await handle?.close();
  }
  await syncDirectory(resolve(path, ".."));
  await durabilityPoint?.();
}

async function publishImmutable(path, value, mode, durabilityPoint) {
  const directory = resolve(path, "..");
  const temporary = join(directory, `.tmp-${randomBytes(16).toString("hex")}`);
  let published = false;
  try {
    await writeExclusive(temporary, value, mode);
    await link(temporary, path);
    published = true;
    await syncDirectory(directory);
    await unlink(temporary);
    await syncDirectory(directory);
    await durabilityPoint?.();
  } catch (error) {
    try {
      await unlink(temporary);
      await syncDirectory(directory);
    } catch {}
    throw error;
  }
  if (!published) fail("executor_journal_publish_failed");
}

function sameIdentity(left, right) {
  return left.dev === right.dev && left.ino === right.ino;
}

async function stableEntryStat(path) {
  for (let attempt = 0; attempt < 25; attempt += 1) {
    const metadata = await lstat(path);
    if (metadata.nlink === 1) return metadata;
    if (metadata.nlink !== 2) return metadata;
    await new Promise((resolveWait) => setTimeout(resolveWait, 1));
  }
  return lstat(path);
}

function validateJournalBody(value) {
  const record = plainObject(value, "executor_journal_record_invalid");
  exactFields(record, JOURNAL_FIELDS, "executor_journal_record_fields_invalid");
  if (record.schema !== EXECUTOR_JOURNAL_SCHEMA) fail("executor_journal_record_schema_invalid");
  validateRequestBody(record.body);
  sha256Value(record.body_sha256, "executor_journal_body_sha256");
  sha256Value(record.request_id_hash, "executor_journal_request_id_hash");
  sha256Value(record.nonce_hash, "executor_journal_nonce_hash");
  if (record.body_sha256 !== digestBytes(canonicalExecutorRequestBytes(record.body))) {
    fail("executor_journal_body_digest_mismatch");
  }
  if (record.request_id_hash !== digestText(record.body.request_id)) {
    fail("executor_journal_request_id_hash_mismatch");
  }
  if (record.nonce_hash !== digestText(record.body.nonce)) fail("executor_journal_nonce_hash_mismatch");
  if (!["prepared", "dispatched", "terminal", "uncertain"].includes(record.state)) {
    fail("executor_journal_state_invalid");
  }
  if (!Number.isSafeInteger(record.state_version) || record.state_version < 1) {
    fail("executor_journal_state_version_invalid");
  }
  for (const name of [
    "prepared_boottime_ns",
    "updated_boottime_ns",
    "dispatched_boottime_ns",
    "terminal_boottime_ns",
  ]) {
    if (record[name] !== null) decimal(record[name], `executor_journal_${name}`);
  }
  if (record.prepared_boottime_ns === null || record.updated_boottime_ns === null) {
    fail("executor_journal_time_invalid");
  }
  if (record.terminal_outcome !== null && !TERMINAL_OUTCOMES.has(record.terminal_outcome)) {
    fail("executor_journal_terminal_outcome_invalid");
  }
  if (record.uncertainty_reason !== null && !UNCERTAINTY_REASONS.has(record.uncertainty_reason)) {
    fail("executor_journal_uncertainty_reason_invalid");
  }
  if (record.state === "prepared" && (
    record.dispatched_boottime_ns !== null
    || record.terminal_boottime_ns !== null
    || record.terminal_outcome !== null
    || record.uncertainty_reason !== null
  )) fail("executor_journal_prepared_shape_invalid");
  if (record.state === "dispatched" && (
    record.dispatched_boottime_ns === null
    || record.terminal_boottime_ns !== null
    || record.terminal_outcome !== null
    || record.uncertainty_reason !== null
  )) fail("executor_journal_dispatched_shape_invalid");
  if (record.state === "uncertain" && (
    record.dispatched_boottime_ns === null
    || record.terminal_boottime_ns !== null
    || record.terminal_outcome !== null
    || record.uncertainty_reason === null
  )) fail("executor_journal_uncertain_shape_invalid");
  if (record.state === "terminal" && (
    record.terminal_boottime_ns === null
    || record.terminal_outcome === null
    || record.uncertainty_reason !== null
  )) fail("executor_journal_terminal_shape_invalid");
  if (
    record.real_runtime_process_spawned !== false
    || record.runtime_receipt_verified !== false
    || record.hostile_runtime_isolation_verified !== false
  ) fail("executor_journal_runtime_claim_invalid");
  return record;
}

function validateNonceBody(value) {
  const record = plainObject(value, "executor_nonce_record_invalid");
  exactFields(record, NONCE_FIELDS, "executor_nonce_record_fields_invalid");
  if (record.schema !== EXECUTOR_NONCE_SCHEMA) fail("executor_nonce_record_schema_invalid");
  sha256Value(record.body_sha256, "executor_nonce_body_sha256");
  sha256Value(record.request_id_hash, "executor_nonce_request_id_hash");
  sha256Value(record.nonce_hash, "executor_nonce_hash");
  return record;
}

function validateDispatchBody(value) {
  const record = plainObject(value, "executor_dispatch_record_invalid");
  exactFields(record, DISPATCH_FIELDS, "executor_dispatch_record_fields_invalid");
  if (record.schema !== EXECUTOR_DISPATCH_SCHEMA) fail("executor_dispatch_record_schema_invalid");
  sha256Value(record.body_sha256, "executor_dispatch_body_sha256");
  sha256Value(record.request_id_hash, "executor_dispatch_request_id_hash");
  decimal(record.dispatch_boottime_ns, "executor_dispatch_boottime_ns");
  return record;
}

export class ExecutorReplayJournal {
  static async open(rootValue, options = {}) {
    const root = canonicalRootPath(rootValue);
    let resolved;
    try {
      resolved = await realpath(root);
    } catch (error) {
      fail("executor_journal_root_unavailable", error);
    }
    if (resolved !== root) fail("executor_journal_root_noncanonical");
    const rootStat = await lstat(root);
    const identity = validateExecutorJournalRootMetadata(rootStat, options.expectedOwner);
    return new ExecutorReplayJournal(root, identity, options);
  }

  constructor(root, identity, options) {
    this.root = root;
    this.identity = identity;
    this.owner = {
      uid: options.expectedOwner?.uid ?? 0,
      gid: options.expectedOwner?.gid ?? 0,
    };
    this.durabilityPoint = options.durabilityPoint;
  }

  async assertRoot() {
    const resolved = await realpath(this.root);
    if (resolved !== this.root) fail("executor_journal_root_noncanonical");
    const current = validateExecutorJournalRootMetadata(await lstat(this.root), {
      ...this.owner,
      mode: 0o700,
    });
    if (!sameIdentity(current, this.identity)) fail("executor_journal_root_identity_changed");
  }

  async inspectExisting(path) {
    const before = await stableEntryStat(path);
    const identity = validateExecutorJournalEntryMetadata(before, this.owner);
    const handle = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
    try {
      const after = await handle.stat();
      validateExecutorJournalEntryMetadata(after, this.owner);
      if (!sameIdentity(identity, after)) fail("executor_journal_entry_identity_changed");
      const pathAfter = await lstat(path);
      validateExecutorJournalEntryMetadata(pathAfter, this.owner);
      if (!sameIdentity(identity, pathAfter)) fail("executor_journal_entry_identity_changed");
    } finally {
      await handle.close();
    }
  }

  async readRecordByPath(path, validator, maximum = MAX_EXECUTOR_JOURNAL_BYTES) {
    await this.assertRoot();
    const before = await stableEntryStat(path);
    const identity = validateExecutorJournalEntryMetadata(before, this.owner);
    if (before.size < 2 || before.size > maximum) fail("executor_journal_entry_size_invalid");
    const handle = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
    try {
      const after = await handle.stat();
      validateExecutorJournalEntryMetadata(after, this.owner);
      if (!sameIdentity(identity, after)) fail("executor_journal_entry_identity_changed");
      const bytes = await handle.readFile();
      let value;
      try {
        value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
      } catch (error) {
        fail("executor_journal_entry_encoding_invalid", error);
      }
      validator(value);
      if (!bytes.equals(canonicalExecutorRequestBytes(value))) {
        fail("executor_journal_entry_noncanonical");
      }
      const pathAfter = await lstat(path);
      validateExecutorJournalEntryMetadata(pathAfter, this.owner);
      if (!sameIdentity(identity, pathAfter)) fail("executor_journal_entry_identity_changed");
      return value;
    } finally {
      await handle.close();
    }
  }

  async read(requestId) {
    let current = await this.readRecordByPath(
      executorRequestJournalPath(this.root, requestId),
      validateJournalBody,
    );
    if (current.state_version !== 1) fail("executor_journal_initial_version_invalid");
    for (let version = 2; version <= 999_999_999; version += 1) {
      const path = executorRequestStatePath(this.root, requestId, version);
      let next;
      try {
        next = await this.readRecordByPath(path, validateJournalBody);
      } catch (error) {
        if (error?.code === "ENOENT") break;
        throw error;
      }
      if (
        next.state_version !== version
        || next.body_sha256 !== current.body_sha256
        || next.request_id_hash !== current.request_id_hash
        || next.nonce_hash !== current.nonce_hash
      ) fail("executor_journal_state_chain_invalid");
      current = next;
    }
    return current;
  }

  async reserve(requestBytes, expected) {
    await this.assertRoot();
    const body = parseCanonicalExecutorRequest(requestBytes, expected);
    const canonical = canonicalExecutorRequestBytes(body);
    const bodyDigest = digestBytes(canonical);
    const requestPath = executorRequestJournalPath(this.root, body.request_id);
    const noncePath = executorNonceJournalPath(this.root, body.nonce);
    const now = expected.now_boottime_ns;
    const record = {
      body,
      body_sha256: bodyDigest,
      dispatched_boottime_ns: null,
      hostile_runtime_isolation_verified: false,
      nonce_hash: digestText(body.nonce),
      prepared_boottime_ns: now,
      real_runtime_process_spawned: false,
      request_id_hash: digestText(body.request_id),
      runtime_receipt_verified: false,
      schema: EXECUTOR_JOURNAL_SCHEMA,
      state: "prepared",
      state_version: 1,
      terminal_boottime_ns: null,
      terminal_outcome: null,
      uncertainty_reason: null,
      updated_boottime_ns: now,
    };
    const nonceRecord = {
      body_sha256: bodyDigest,
      nonce_hash: record.nonce_hash,
      request_id_hash: record.request_id_hash,
      schema: EXECUTOR_NONCE_SCHEMA,
    };
    try {
      await writeExclusive(requestPath, record, 0o600, () => this.durabilityPoint?.("request_reserved"));
    } catch (error) {
      if (error?.code === "EEXIST") {
        await this.inspectExisting(requestPath);
        fail("executor_journal_request_replayed");
      }
      throw error;
    }
    try {
      await writeExclusive(noncePath, nonceRecord, 0o600, () => this.durabilityPoint?.("nonce_reserved"));
    } catch (error) {
      if (error?.code === "EEXIST") {
        await this.inspectExisting(noncePath);
        await this.toUncertain(record, "nonce_conflict", now);
        fail("executor_journal_nonce_replayed");
      }
      throw error;
    }
    return Object.freeze({ ...record });
  }

  async replaceRecord(record) {
    validateJournalBody(record);
    await this.assertRoot();
    if (record.state_version < 2) fail("executor_journal_state_version_invalid");
    const current = await this.read(record.body.request_id);
    if (
      current.state_version + 1 !== record.state_version
      || current.body_sha256 !== record.body_sha256
      || current.request_id_hash !== record.request_id_hash
      || current.nonce_hash !== record.nonce_hash
    ) fail("executor_journal_stale_transition");
    const path = executorRequestStatePath(this.root, record.body.request_id, record.state_version);
    try {
      await publishImmutable(
        path,
        record,
        0o600,
        () => this.durabilityPoint?.(`state_${record.state}_durable`),
      );
    } catch (error) {
      if (error?.code === "EEXIST") fail("executor_journal_stale_transition");
      throw error;
    }
    return Object.freeze({ ...record });
  }

  async toUncertain(record, reason, now) {
    if (!UNCERTAINTY_REASONS.has(reason)) fail("executor_journal_uncertainty_reason_invalid");
    if (record.state !== "dispatched" && record.state !== "prepared") {
      fail("executor_journal_transition_invalid");
    }
    return this.replaceRecord({
      ...record,
      dispatched_boottime_ns: record.dispatched_boottime_ns ?? now,
      state: "uncertain",
      state_version: record.state_version + 1,
      uncertainty_reason: reason,
      updated_boottime_ns: now,
    });
  }

  async markDispatched(requestId, expectedValue) {
    const expected = validateExpectedClock(expectedValue);
    const now = expected.now_boottime_ns;
    const record = await this.read(requestId);
    if (record.state !== "prepared") fail("executor_journal_not_executable");
    if (
      record.body.boot_id !== expected.boot_id
      || BigInt(record.body.deadline_boottime_ns) <= BigInt(now)
    ) {
      fail("executor_journal_not_executable");
    }
    const nonce = await this.readRecordByPath(
      executorNonceJournalPath(this.root, record.body.nonce),
      validateNonceBody,
    );
    if (
      nonce.body_sha256 !== record.body_sha256
      || nonce.request_id_hash !== record.request_id_hash
      || nonce.nonce_hash !== record.nonce_hash
    ) fail("executor_journal_nonce_binding_invalid");
    const dispatchPath = executorDispatchJournalPath(this.root, requestId);
    const dispatchRecord = {
      body_sha256: record.body_sha256,
      dispatch_boottime_ns: now,
      request_id_hash: record.request_id_hash,
      schema: EXECUTOR_DISPATCH_SCHEMA,
    };
    try {
      await writeExclusive(
        dispatchPath,
        dispatchRecord,
        0o600,
        () => this.durabilityPoint?.("dispatch_reserved"),
      );
    } catch (error) {
      if (error?.code === "EEXIST") {
        await this.inspectExisting(dispatchPath);
        fail("executor_journal_not_executable");
      }
      throw error;
    }
    return this.replaceRecord({
      ...record,
      dispatched_boottime_ns: now,
      state: "dispatched",
      state_version: record.state_version + 1,
      updated_boottime_ns: now,
    });
  }

  async markTerminal(requestId, nowBoottimeNs, outcome) {
    const now = decimal(nowBoottimeNs, "executor_journal_now_boottime_ns").toString();
    if (!TERMINAL_OUTCOMES.has(outcome)) fail("executor_journal_terminal_outcome_invalid");
    const record = await this.read(requestId);
    const dispatchRequired = new Set(["completed", "failed"]);
    if (
      record.state === "terminal"
      || record.state === "uncertain"
      || (dispatchRequired.has(outcome) && record.state !== "dispatched")
      || (record.state !== "prepared" && record.state !== "dispatched")
    ) fail("executor_journal_transition_invalid");
    const prepared = BigInt(record.prepared_boottime_ns);
    const observed = BigInt(now);
    const deadline = BigInt(record.body.deadline_boottime_ns);
    let terminal = observed;
    if (outcome === "expired") {
      if (record.state !== "prepared" || observed < deadline) {
        fail("executor_journal_terminal_time_invalid");
      }
      terminal = deadline;
    } else if (outcome === "abandoned_boot") {
      if (record.state !== "prepared") fail("executor_journal_transition_invalid");
      terminal = prepared;
    } else if (
      terminal < prepared
      || terminal > deadline
      || (record.dispatched_boottime_ns !== null
        && terminal < BigInt(record.dispatched_boottime_ns))
    ) fail("executor_journal_terminal_time_invalid");
    return this.replaceRecord({
      ...record,
      state: "terminal",
      state_version: record.state_version + 1,
      terminal_boottime_ns: terminal.toString(),
      terminal_outcome: outcome,
      uncertainty_reason: null,
      updated_boottime_ns: now,
    });
  }

  async recover(expectedValue) {
    await this.assertRoot();
    const expected = validateExpectedClock(expectedValue);
    const now = expected.now_boottime_ns;
    const names = await readdir(this.root);
    const report = { prepared: [], terminal: [], uncertain: [], corrupt: [] };
    for (const name of names.sort()) {
      if (name.startsWith(".tmp-")) {
        report.corrupt.push(name);
        continue;
      }
      if (!/^request-[a-f0-9]{64}\.json$/.test(name)) continue;
      const path = join(this.root, name);
      let record;
      try {
        record = await this.readRecordByPath(path, validateJournalBody);
        if (name !== `request-${record.request_id_hash}.json`) {
          fail("executor_journal_request_path_binding_invalid");
        }
        record = await this.read(record.body.request_id);
      } catch {
        report.corrupt.push(name);
        continue;
      }
      if (record.state === "terminal") {
        report.terminal.push(record.body.request_id);
        continue;
      }
      if (record.state === "uncertain") {
        report.uncertain.push(record.body.request_id);
        continue;
      }
      if (record.state === "dispatched") {
        record = await this.toUncertain(record, "dispatch_recovery", now);
        report.uncertain.push(record.body.request_id);
        continue;
      }
      const dispatchPath = executorDispatchJournalPath(this.root, record.body.request_id);
      let dispatch = null;
      let dispatchError = null;
      try {
        dispatch = await this.readRecordByPath(dispatchPath, validateDispatchBody);
      } catch (error) {
        dispatchError = error;
      }
      if (dispatch !== null) {
        if (
          dispatch.body_sha256 !== record.body_sha256
          || dispatch.request_id_hash !== record.request_id_hash
        ) fail("executor_dispatch_binding_invalid");
        await this.toUncertain(record, "dispatch_recovery", now);
        report.uncertain.push(record.body.request_id);
        continue;
      }
      if (dispatchError?.code !== "ENOENT") {
        await this.toUncertain(record, "journal_corrupt", now);
        report.uncertain.push(record.body.request_id);
        continue;
      }
      if (record.body.boot_id !== expected.boot_id) {
        await this.markTerminal(record.body.request_id, now, "abandoned_boot");
        report.terminal.push(record.body.request_id);
        continue;
      }
      if (BigInt(record.body.deadline_boottime_ns) <= BigInt(now)) {
        await this.markTerminal(record.body.request_id, now, "expired");
        report.terminal.push(record.body.request_id);
        continue;
      }
      const noncePath = executorNonceJournalPath(this.root, record.body.nonce);
      const nonceRecord = {
        body_sha256: record.body_sha256,
        nonce_hash: record.nonce_hash,
        request_id_hash: record.request_id_hash,
        schema: EXECUTOR_NONCE_SCHEMA,
      };
      try {
        await writeExclusive(noncePath, nonceRecord, 0o600);
      } catch (error) {
        if (error?.code !== "EEXIST") throw error;
        try {
          const existing = await this.readRecordByPath(noncePath, validateNonceBody);
          if (canonicalExecutorRequestBytes(existing).equals(canonicalExecutorRequestBytes(nonceRecord))) {
            report.prepared.push(record.body.request_id);
            continue;
          }
        } catch {
          // Unsafe or corrupt nonce reservations make this request permanently uncertain.
        }
        await this.toUncertain(record, "nonce_conflict", now);
        report.uncertain.push(record.body.request_id);
        continue;
      }
      report.prepared.push(record.body.request_id);
    }
    return Object.freeze({
      ...report,
      hostile_runtime_isolation_verified: false,
      real_runtime_process_spawned: false,
      runtime_receipt_verified: false,
    });
  }
}
