#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import {
  chmodSync,
  existsSync,
  lstatSync,
  mkdtempSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { createServer, createConnection } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

if (process.platform !== "linux") {
  process.stderr.write("openclaw_peercred_gate_contract_requires_linux\n");
  process.exit(78);
}

const source = fileURLToPath(new URL("./openclaw-peercred-gate.c", import.meta.url));
const root = mkdtempSync(join(tmpdir(), "agentops-peercred-contract-"));
const binary = join(root, "openclaw-peercred-gate");
const listenPath = join(root, "public.sock");
const upstreamPath = join(root, "private.sock");
const allowedUid = process.getuid();
const deniedUid = allowedUid === 65534 ? 65533 : 65534;
const deniedCanary = Buffer.from("denied-peer-bytes-must-not-forward");
const allowedCanary = Buffer.from("allowed-peer-round-trip");

let upstream;
let gate;
let gateOutput = "";
let upstreamConnections = 0;
let upstreamBytes = 0;
let activeUpstreamConnections = 0;
let maximumUpstreamConnections = 0;
let upstreamDisconnects = 0;
let currentUpstreamSocket = null;

function waitFor(predicate, label, attempts = 250) {
  return new Promise(async (resolveWait, rejectWait) => {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        if (await predicate()) {
          resolveWait();
          return;
        }
      } catch {}
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 20));
    }
    rejectWait(new Error(`${label}_timeout`));
  });
}

function waitForExit(child) {
  return new Promise((resolveExit) => {
    if (child.exitCode !== null) resolveExit(child.exitCode);
    else child.once("exit", resolveExit);
  });
}

function gateArguments(expectedUid = allowedUid) {
  return [
    "--listen",
    listenPath,
    "--upstream",
    upstreamPath,
    "--expected-uid",
    String(expectedUid),
    "--listen-gid",
    String(process.getgid()),
  ];
}

function launchGate(expectedUid = allowedUid) {
  const child = spawn(binary, gateArguments(expectedUid), {
    env: {},
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (chunk) => { gateOutput += chunk.toString("utf8"); });
  child.stderr.on("data", (chunk) => { gateOutput += chunk.toString("utf8"); });
  return child;
}

function connectClient({ uid, gid, payload }) {
  const clientSource = `
const { createConnection } = require("node:net");
const socket = createConnection({ path: process.argv[1] });
const chunks = [];
process.stdin.on("data", (chunk) => chunks.push(chunk));
process.stdin.once("end", () => {
  socket.once("connect", () => socket.write(Buffer.concat(chunks)));
});
socket.once("data", (chunk) => process.stdout.write(chunk));
socket.once("end", () => process.exit(0));
socket.once("close", () => process.exit(0));
socket.once("error", () => process.exit(0));
setTimeout(() => process.exit(2), 5000).unref();
`;
  const child = spawn(process.execPath, ["-e", clientSource, listenPath], {
    uid,
    gid,
    env: {},
    stdio: ["pipe", "pipe", "pipe"],
  });
  child.stdin.end(payload);
  return child;
}

function allowedRoundTrip(payload) {
  return new Promise((resolveClient, rejectClient) => {
    const socket = createConnection({ path: listenPath });
    const chunks = [];
    socket.once("connect", () => socket.write(payload));
    socket.on("data", (chunk) => chunks.push(chunk));
    socket.once("error", rejectClient);
    socket.once("end", () => resolveClient(Buffer.concat(chunks)));
  });
}

try {
  const sourceText = readFileSync(source, "utf8");
  assert.match(sourceText, /socket\(AF_UNIX, SOCK_STREAM/);
  assert.match(sourceText, /getsockopt\(client_fd, SOL_SOCKET, SO_PEERCRED/);
  assert.ok(
    sourceText.indexOf("getsockopt(client_fd, SOL_SOCKET, SO_PEERCRED")
      < sourceText.indexOf("connect_upstream(upstream_path"),
  );
  assert.ok(
    sourceText.indexOf("getsockopt(client_fd, SOL_SOCKET, SO_PEERCRED")
      < sourceText.indexOf("relay_connection(client_fd"),
  );
  assert.doesNotMatch(sourceText, /AF_INET|AF_INET6|SOCK_DGRAM/);
  assert.doesNotMatch(sourceText, /\bsystem\s*\(|\bpopen\s*\(|\bfork\s*\(|\bexec[lvpe]*\s*\(/);
  assert.doesNotMatch(sourceText, /printf\s*\([^,]+,\s*(?:buffer|data|payload)/);
  assert.match(sourceText, /argc != 9/);
  assert.match(sourceText, /strcmp\(argv\[1\], "--listen"\)/);
  assert.match(sourceText, /strcmp\(argv\[3\], "--upstream"\)/);
  assert.match(sourceText, /strcmp\(argv\[5\], "--expected-uid"\)/);
  assert.match(sourceText, /strcmp\(argv\[7\], "--listen-gid"\)/);

  const compile = spawnSync("cc", [
    "-std=c11",
    "-O2",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-pedantic",
    source,
    "-o",
    binary,
  ], { encoding: "utf8", env: { PATH: process.env.PATH } });
  assert.equal(compile.status, 0, compile.stderr);
  chmodSync(root, 0o755);
  chmodSync(root, 0o750);

  upstream = createServer((socket) => {
    upstreamConnections += 1;
    activeUpstreamConnections += 1;
    maximumUpstreamConnections = Math.max(maximumUpstreamConnections, activeUpstreamConnections);
    currentUpstreamSocket = socket;
    socket.on("data", (chunk) => {
      upstreamBytes += chunk.byteLength;
      if (
        chunk.equals(Buffer.from("client-disconnect-probe"))
        || chunk.equals(Buffer.from("signal-cleanup-probe"))
      ) return;
      socket.write(chunk);
      socket.end();
    });
    socket.once("close", () => {
      activeUpstreamConnections -= 1;
      upstreamDisconnects += 1;
      if (currentUpstreamSocket === socket) currentUpstreamSocket = null;
    });
  });
  await new Promise((resolveListen, rejectListen) => {
    upstream.once("error", rejectListen);
    upstream.listen(upstreamPath, () => {
      upstream.off("error", rejectListen);
      chmodSync(upstreamPath, 0o660);
      resolveListen();
    });
  });

  gate = launchGate();
  await waitFor(() => existsSync(listenPath), "gate_listen");
  const listenMetadata = lstatSync(listenPath);
  assert.equal(listenMetadata.uid, process.getuid());
  assert.equal(listenMetadata.gid, process.getgid());
  assert.equal(listenMetadata.mode & 0o777, 0o660);

  let deniedPeerTested = false;
  if (allowedUid === 0) {
    const denied = connectClient({ uid: deniedUid, gid: 0, payload: deniedCanary });
    const deniedOutput = [];
    denied.stdout.on("data", (chunk) => deniedOutput.push(chunk));
    assert.equal(await waitForExit(denied), 0);
    assert.equal(Buffer.concat(deniedOutput).byteLength, 0);
    deniedPeerTested = true;
  } else {
    const deniedGate = gate;
    deniedGate.kill("SIGTERM");
    assert.equal(await waitForExit(deniedGate), 0);
    await waitFor(() => !existsSync(listenPath), "denied_gate_cleanup");
    gate = launchGate(deniedUid);
    await waitFor(() => existsSync(listenPath), "denied_gate_listen");
    const denied = connectClient({ uid: allowedUid, gid: process.getgid(), payload: deniedCanary });
    assert.equal(await waitForExit(denied), 0);
    gate.kill("SIGTERM");
    assert.equal(await waitForExit(gate), 0);
    await waitFor(() => !existsSync(listenPath), "denied_gate_second_cleanup");
    gate = launchGate();
    await waitFor(() => existsSync(listenPath), "allowed_gate_listen");
    deniedPeerTested = true;
  }
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  assert.equal(upstreamConnections, 0);
  assert.equal(upstreamBytes, 0);

  const echoed = await allowedRoundTrip(allowedCanary);
  assert.deepEqual(echoed, allowedCanary);
  await waitFor(() => upstreamDisconnects === 1, "upstream_disconnect_after_round_trip");
  assert.equal(upstreamConnections, 1);
  assert.equal(upstreamBytes, allowedCanary.byteLength);

  const connectionsBeforeUpstreamIdentityDrift = upstreamConnections;
  chmodSync(upstreamPath, 0o666);
  const rejectedForIdentityDrift = await allowedRoundTrip(
    Buffer.from("upstream-identity-drift-must-not-forward"),
  ).catch(() => Buffer.alloc(0));
  assert.equal(rejectedForIdentityDrift.byteLength, 0);
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  assert.equal(upstreamConnections, connectionsBeforeUpstreamIdentityDrift);
  chmodSync(upstreamPath, 0o660);

  const disconnectsBeforeClientClose = upstreamDisconnects;
  const disconnectingClient = createConnection({ path: listenPath });
  await new Promise((resolveConnect, rejectConnect) => {
    disconnectingClient.once("connect", resolveConnect);
    disconnectingClient.once("error", rejectConnect);
  });
  disconnectingClient.write(Buffer.from("client-disconnect-probe"));
  await waitFor(() => currentUpstreamSocket !== null, "client_disconnect_upstream_connection");
  disconnectingClient.destroy();
  await waitFor(
    () => upstreamDisconnects === disconnectsBeforeClientClose + 1,
    "client_disconnect_propagation",
  );

  const activeClient = createConnection({ path: listenPath });
  await new Promise((resolveConnect, rejectConnect) => {
    activeClient.once("connect", resolveConnect);
    activeClient.once("error", rejectConnect);
  });
  activeClient.write(Buffer.from("signal-cleanup-probe"));
  await waitFor(() => currentUpstreamSocket !== null, "active_upstream_connection");
  const upstreamConnectionsBeforeQueuedClient = upstreamConnections;
  const queuedClient = createConnection({ path: listenPath });
  queuedClient.once("error", () => {});
  await new Promise((resolveConnect) => queuedClient.once("connect", resolveConnect));
  queuedClient.write(Buffer.from("queued-connection-must-not-reach-upstream"));
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  assert.equal(upstreamConnections, upstreamConnectionsBeforeQueuedClient);
  gate.kill("SIGTERM");
  assert.equal(await waitForExit(gate), 0);
  await waitFor(() => !existsSync(listenPath), "signal_socket_cleanup");
  await waitFor(() => currentUpstreamSocket === null, "signal_disconnect_propagation");
  activeClient.destroy();
  queuedClient.destroy();

  assert.equal(maximumUpstreamConnections, 1);
  assert.doesNotMatch(gateOutput, new RegExp(deniedCanary.toString("utf8")));
  assert.doesNotMatch(gateOutput, new RegExp(allowedCanary.toString("utf8")));

  const validArguments = gateArguments();
  for (const invalid of [
    validArguments.slice(0, -2),
    [...validArguments, "--extra", "value"],
    ["--upstream", upstreamPath, "--listen", listenPath, "--expected-uid", String(allowedUid), "--listen-gid", String(process.getgid())],
    ["--listen", "relative.sock", "--upstream", upstreamPath, "--expected-uid", String(allowedUid), "--listen-gid", String(process.getgid())],
    ["--listen", listenPath, "--upstream", "relative.sock", "--expected-uid", String(allowedUid), "--listen-gid", String(process.getgid())],
    ["--listen", listenPath, "--upstream", upstreamPath, "--expected-uid", "01", "--listen-gid", String(process.getgid())],
    ["--listen", listenPath, "--upstream", upstreamPath, "--expected-uid", "-1", "--listen-gid", String(process.getgid())],
    ["--listen", listenPath, "--upstream", upstreamPath, "--expected-uid", "not-a-uid", "--listen-gid", String(process.getgid())],
    ["--listen", listenPath, "--upstream", listenPath, "--expected-uid", String(allowedUid), "--listen-gid", String(process.getgid())],
    ["--listen", listenPath, "--upstream", upstreamPath, "--expected-uid", String(allowedUid), "--listen-gid", "01"],
  ]) {
    const rejected = spawnSync(binary, invalid, { encoding: "utf8", env: {} });
    assert.equal(rejected.status, 64);
  }

  chmodSync(root, 0o770);
  const invalidParent = spawnSync(binary, validArguments, { encoding: "utf8", env: {} });
  assert.equal(invalidParent.status, 78);
  chmodSync(root, 0o750);

  process.stdout.write(`${JSON.stringify({
    schema: "agentops_openclaw_peercred_gate_contract_v1",
    ok: true,
    linux_so_peercred_compiled: true,
    af_unix_stream_only: true,
    peer_credentials_checked_before_read_or_forward: true,
    exact_argv: "--listen PATH --upstream PATH --expected-uid UID --listen-gid GID",
    strict_named_argv_verified: true,
    listen_owner_uid_derived_from_getuid: true,
    listen_parent_uid_gid_mode_0750_verified: true,
    output_socket_mode_0660_verified: true,
    upstream_socket_identity_pinned_before_connect: true,
    upstream_identity_drift_forwarded_connections: 0,
    allowed_uid_round_trip_verified: true,
    denied_uid_connection_verified: deniedPeerTested,
    denied_peer_bytes_forwarded: 0,
    maximum_active_upstream_connections: maximumUpstreamConnections,
    bounded_poll_relay_verified: true,
    disconnect_propagation_verified: true,
    public_client_disconnect_propagation_verified: true,
    signal_cleanup_verified: true,
    payload_logging_omitted: true,
    full_hostile_runtime_isolation_verified: false,
  })}\n`);
} finally {
  if (gate && gate.exitCode === null) {
    gate.kill("SIGKILL");
    await waitForExit(gate);
  }
  if (currentUpstreamSocket) currentUpstreamSocket.destroy();
  if (upstream) {
    await new Promise((resolveClose) => upstream.close(resolveClose));
  }
  rmSync(root, { recursive: true, force: true });
}
