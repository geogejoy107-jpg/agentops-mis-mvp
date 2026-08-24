#!/usr/bin/env node

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createServer, request as httpRequest } from "node:http";
import { createConnection } from "node:net";
import { PassThrough, Readable } from "node:stream";
import { fileURLToPath } from "node:url";
import {
  HEALTHCHECK_HOST,
  INTERNAL_BASE_URL,
  LISTEN_HOST,
  LISTEN_PORT,
  MAX_CONCURRENCY,
  MAX_REQUEST_BYTES,
  MAX_RESPONSE_BYTES,
  UPSTREAM_ORIGIN_ENV,
  UPSTREAM_TIMEOUT_MS,
  addressIsForbidden,
  checkGatewayHealth,
  createGatewayHandler,
  createPinnedLookup,
  parseUpstreamOrigin,
  validateResolvedAddresses,
} from "./openclaw-egress-gateway.mjs";

const UPSTREAM_HOST = "api.provider.example";
const PINNED_ADDRESS = "93.184.216.34";
const SECRET = "contract-secret-never-return";

function upstreamResponse(statusCode, body, headers = { "content-type": "application/json" }) {
  const stream = Readable.from([Buffer.from(body, "utf8")]);
  stream.statusCode = statusCode;
  stream.headers = headers;
  return stream;
}

function listen(server, host = "127.0.0.1", port = 0) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, host, () => {
      server.off("error", reject);
      resolve(server.address());
    });
  });
}

function close(server) {
  return new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}

function localRequest(port, {
  method = "POST",
  path = "/v1/chat/completions",
  body = Buffer.from("{}", "utf8"),
  headers = {},
} = {}) {
  return new Promise((resolve, reject) => {
    const request = httpRequest({
      host: "127.0.0.1",
      port,
      method,
      path,
      headers: {
        ...(body === null ? {} : { "content-length": String(body.byteLength) }),
        ...(method === "POST" ? { "content-type": "application/json" } : {}),
        connection: "close",
        ...headers,
      },
    }, async (response) => {
      try {
        const chunks = [];
        for await (const chunk of response) chunks.push(Buffer.from(chunk));
        resolve({
          body: Buffer.concat(chunks).toString("utf8"),
          headers: response.headers,
          statusCode: response.statusCode,
        });
      } catch (error) {
        reject(error);
      }
    });
    request.on("error", reject);
    if (body !== null) request.end(body);
    else request.end();
  });
}

function rawRequestWithoutContentLength(port) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    const socket = createConnection({ host: "127.0.0.1", port }, () => {
      socket.end([
        "POST /v1/chat/completions HTTP/1.1",
        `Host: 127.0.0.1:${port}`,
        "Content-Type: application/json",
        "Connection: close",
        "",
        "",
      ].join("\r\n"));
    });
    socket.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    socket.on("error", reject);
    socket.once("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      const [head, body = ""] = raw.split("\r\n\r\n", 2);
      const match = /^HTTP\/1\.1 ([0-9]{3}) /u.exec(head);
      if (!match) {
        reject(new Error("raw_http_response_invalid"));
        return;
      }
      resolve({ body, statusCode: Number(match[1]) });
    });
  });
}

function lookupResult(lookup, hostname, options = {}) {
  return new Promise((resolve, reject) => lookup(hostname, options, (error, address, family) => {
    if (error) reject(error);
    else resolve({ address, family });
  }));
}

assert.equal(UPSTREAM_ORIGIN_ENV, "OPENCLAW_EGRESS_GATEWAY_UPSTREAM_ORIGIN");
assert.equal(LISTEN_HOST, "0.0.0.0");
assert.equal(LISTEN_PORT, 18080);
assert.equal(HEALTHCHECK_HOST, "127.0.0.1");
assert.equal(INTERNAL_BASE_URL, "http://openclaw-egress-gateway:18080/v1");
assert.equal(MAX_REQUEST_BYTES, 1024 * 1024);
assert.equal(MAX_RESPONSE_BYTES, 4 * 1024 * 1024);
assert.equal(MAX_CONCURRENCY, 8);
assert.equal(UPSTREAM_TIMEOUT_MS, 30_000);
const gatewaySource = readFileSync(
  fileURLToPath(new URL("./openclaw-egress-gateway.mjs", import.meta.url)),
  "utf8",
);
assert.match(gatewaySource, /arguments_\.length === 1 && arguments_\[0\] === "--healthcheck"/u);
assert.match(gatewaySource, /await checkGatewayHealth\(\)/u);

assert.deepEqual(parseUpstreamOrigin("https://api.provider.example"), {
  hostname: UPSTREAM_HOST,
  origin: "https://api.provider.example",
  port: 443,
});
for (const origin of [
  "",
  "http://api.provider.example",
  "https://localhost",
  "https://service.localhost",
  "https://127.0.0.1",
  "https://[::1]",
  "https://single-label",
  "https://user:password@api.provider.example",
  "https://api.provider.example/v1",
  "https://api.provider.example/?target=other.example",
  "https://api.provider.example/#fragment",
]) assert.throws(() => parseUpstreamOrigin(origin), /upstream_origin_invalid/u);

for (const address of [
  "0.0.0.0",
  "10.0.0.1",
  "100.64.0.1",
  "127.0.0.1",
  "169.254.169.254",
  "172.16.0.1",
  "192.168.1.1",
  "192.0.2.1",
  "198.18.0.1",
  "198.51.100.1",
  "203.0.113.1",
  "224.0.0.1",
  "240.0.0.1",
  "::",
  "::1",
  "::ffff:127.0.0.1",
  "fc00::1",
  "fe80::1",
  "ff02::1",
  "2001:db8::1",
  "2002::1",
]) assert.equal(addressIsForbidden(address), true, address);
assert.equal(addressIsForbidden(PINNED_ADDRESS), false);
assert.equal(addressIsForbidden("2606:2800:220:1:248:1893:25c8:1946"), false);

for (const answer of [
  [],
  [{ address: "127.0.0.1", family: 4 }],
  [{ address: PINNED_ADDRESS, family: 6 }],
  [{ address: PINNED_ADDRESS, family: 4 }, { address: "169.254.169.254", family: 4 }],
  [{ address: "not-an-ip", family: 4 }],
]) assert.throws(() => validateResolvedAddresses(answer), /upstream_dns_rejected/u);

const pinnedLookup = createPinnedLookup(UPSTREAM_HOST, [
  { address: PINNED_ADDRESS, family: 4 },
]);
assert.deepEqual(await lookupResult(pinnedLookup, UPSTREAM_HOST), {
  address: PINNED_ADDRESS,
  family: 4,
});
await assert.rejects(lookupResult(pinnedLookup, "rebind.provider.example"), /pinned_lookup_hostname_rejected/u);

const observed = [];
let responseMode = "success";
let releaseConcurrency;
let concurrentArrivals = 0;
const concurrencyBarrier = new Promise((resolve) => { releaseConcurrency = resolve; });
const handler = createGatewayHandler({
  environment: { [UPSTREAM_ORIGIN_ENV]: "https://api.provider.example" },
  resolveHost: async (hostname) => {
    assert.equal(hostname, UPSTREAM_HOST);
    return [{ address: PINNED_ADDRESS, family: 4 }];
  },
  requestUpstream: async (request) => {
    const lookup = await lookupResult(request.lookup, UPSTREAM_HOST);
    observed.push({
      body: request.body.toString("utf8"),
      headers: request.headers,
      lookup,
      path: request.path,
      timeoutMs: request.timeoutMs,
      upstream: request.upstream,
    });
    if (responseMode === "error") {
      return upstreamResponse(401, `{"secret":"${SECRET}"}`, {
        "content-type": "application/json",
        "set-cookie": `credential=${SECRET}`,
      });
    }
    if (responseMode === "redirect") {
      return upstreamResponse(302, SECRET, {
        location: `https://redirect.example/${SECRET}`,
      });
    }
    if (responseMode === "oversized") {
      return upstreamResponse(200, "{}", {
        "content-length": String(MAX_RESPONSE_BYTES + 1),
        "content-type": "application/json",
      });
    }
    if (responseMode === "concurrency") {
      concurrentArrivals += 1;
      await concurrencyBarrier;
    }
    return upstreamResponse(200, "{\"ok\":true}");
  },
});
const server = createServer(handler);
const address = await listen(server);
try {
  assert.equal(await checkGatewayHealth({ port: address.port, timeoutMs: 1_000 }), true);

  const success = await localRequest(address.port, {
    body: Buffer.from("{\"model\":\"fixed\"}", "utf8"),
    headers: {
      authorization: `Bearer ${SECRET}`,
      host: "attacker-controlled.example",
      "x-forwarded-host": "attacker-controlled.example",
    },
  });
  assert.equal(success.statusCode, 200);
  assert.equal(success.body, "{\"ok\":true}");
  assert.equal(observed[0].path, "/v1/chat/completions");
  assert.equal(observed[0].timeoutMs, UPSTREAM_TIMEOUT_MS);
  assert.equal(observed[0].upstream.hostname, UPSTREAM_HOST);
  assert.equal(observed[0].lookup.address, PINNED_ADDRESS);
  assert.equal(observed[0].headers.authorization, `Bearer ${SECRET}`);
  assert.equal(observed[0].headers.host, undefined);
  assert.equal(observed[0].headers["x-forwarded-host"], undefined);

  const anthropicSuccess = await localRequest(address.port, { path: "/v1/messages" });
  assert.equal(anthropicSuccess.statusCode, 200);
  assert.equal(observed.at(-1).path, "/v1/messages");

  for (const [request, statusCode, code] of [
    [{ method: "GET", path: "/v1/chat/completions", body: null }, 405, "request_method_rejected"],
    [{ path: "/v1/models" }, 404, "request_path_rejected"],
    [{ path: "/v1/chat/completions?host=other.example" }, 404, "request_path_rejected"],
    [{ path: "https://other.example/v1/chat/completions" }, 404, "request_path_rejected"],
    [{ headers: { "content-type": "text/plain" } }, 415, "request_content_type_rejected"],
    [{ headers: { "content-encoding": "gzip" } }, 415, "request_content_encoding_rejected"],
    [{ body: null, headers: { "content-length": String(MAX_REQUEST_BYTES + 1) } }, 413, "request_too_large"],
  ]) {
    const rejected = await localRequest(address.port, request);
    assert.equal(rejected.statusCode, statusCode);
    assert.equal(JSON.parse(rejected.body).error.code, code);
    assert.doesNotMatch(rejected.body, /attacker-controlled|contract-secret/u);
  }

  const missingContentLength = await rawRequestWithoutContentLength(address.port);
  assert.equal(missingContentLength.statusCode, 411);
  assert.equal(JSON.parse(missingContentLength.body).error.code, "request_content_length_required");

  responseMode = "error";
  const upstreamError = await localRequest(address.port, {
    headers: { authorization: `Bearer ${SECRET}` },
  });
  assert.equal(upstreamError.statusCode, 502);
  assert.equal(JSON.parse(upstreamError.body).error.code, "upstream_rejected");
  assert.doesNotMatch(JSON.stringify(upstreamError), new RegExp(SECRET, "u"));
  assert.equal(upstreamError.headers["set-cookie"], undefined);

  responseMode = "redirect";
  const redirect = await localRequest(address.port);
  assert.equal(redirect.statusCode, 502);
  assert.equal(JSON.parse(redirect.body).error.code, "upstream_redirect_rejected");
  assert.doesNotMatch(JSON.stringify(redirect), new RegExp(SECRET, "u"));
  assert.equal(redirect.headers.location, undefined);

  responseMode = "oversized";
  const oversized = await localRequest(address.port);
  assert.equal(oversized.statusCode, 502);
  assert.equal(JSON.parse(oversized.body).error.code, "upstream_response_too_large");

  responseMode = "concurrency";
  const held = Array.from({ length: MAX_CONCURRENCY }, () => localRequest(address.port));
  while (concurrentArrivals < MAX_CONCURRENCY) {
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  const saturated = await localRequest(address.port);
  assert.equal(saturated.statusCode, 503);
  assert.equal(JSON.parse(saturated.body).error.code, "request_concurrency_exceeded");
  releaseConcurrency();
  assert.deepEqual((await Promise.all(held)).map((result) => result.statusCode), Array(MAX_CONCURRENCY).fill(200));
} finally {
  releaseConcurrency();
  await close(server);
}

let timeoutAbortObserved = 0;
let timeoutMode = "pending";
const timeoutHandler = createGatewayHandler({
  environment: { [UPSTREAM_ORIGIN_ENV]: "https://api.provider.example" },
  resolveHost: async () => [{ address: PINNED_ADDRESS, family: 4 }],
  upstreamTimeoutMs: 25,
  requestUpstream: ({ signal }) => {
    assert.equal(signal instanceof AbortSignal, true);
    if (timeoutMode === "success") return upstreamResponse(200, "{\"recovered\":true}");
    return new Promise((_, reject) => {
      signal.addEventListener("abort", () => {
        timeoutAbortObserved += 1;
        reject(signal.reason);
      }, { once: true });
    });
  },
});
const timeoutServer = createServer(timeoutHandler);
const timeoutAddress = await listen(timeoutServer);
try {
  const timedOut = await Promise.all(
    Array.from({ length: MAX_CONCURRENCY }, () => localRequest(timeoutAddress.port)),
  );
  assert.deepEqual(timedOut.map((result) => result.statusCode), Array(MAX_CONCURRENCY).fill(504));
  assert.deepEqual(
    timedOut.map((result) => JSON.parse(result.body).error.code),
    Array(MAX_CONCURRENCY).fill("upstream_timeout"),
  );
  assert.equal(timeoutAbortObserved, MAX_CONCURRENCY);
  timeoutMode = "success";
  const afterTimeout = await localRequest(timeoutAddress.port);
  assert.equal(afterTimeout.statusCode, 200);
  assert.equal(afterTimeout.body, "{\"recovered\":true}");
} finally {
  await close(timeoutServer);
}

let slowResponseDestroyed = false;
const responseTimeoutHandler = createGatewayHandler({
  environment: { [UPSTREAM_ORIGIN_ENV]: "https://api.provider.example" },
  resolveHost: async () => [{ address: PINNED_ADDRESS, family: 4 }],
  upstreamTimeoutMs: 25,
  requestUpstream: async () => {
    const stream = new PassThrough();
    stream.statusCode = 200;
    stream.headers = { "content-type": "application/json" };
    stream.once("close", () => { slowResponseDestroyed = stream.destroyed; });
    stream.write("{");
    return stream;
  },
});
const responseTimeoutServer = createServer(responseTimeoutHandler);
const responseTimeoutAddress = await listen(responseTimeoutServer);
try {
  const timedOutResponse = await localRequest(responseTimeoutAddress.port);
  assert.equal(timedOutResponse.statusCode, 504);
  assert.equal(JSON.parse(timedOutResponse.body).error.code, "upstream_timeout");
  assert.equal(slowResponseDestroyed, true);
} finally {
  await close(responseTimeoutServer);
}

let disconnectTransportStarted;
const transportStarted = new Promise((resolve) => { disconnectTransportStarted = resolve; });
let disconnectAbortObserved;
const clientAbort = new Promise((resolve) => { disconnectAbortObserved = resolve; });
const disconnectHandler = createGatewayHandler({
  environment: { [UPSTREAM_ORIGIN_ENV]: "https://api.provider.example" },
  resolveHost: async () => [{ address: PINNED_ADDRESS, family: 4 }],
  upstreamTimeoutMs: 1_000,
  requestUpstream: ({ signal }) => new Promise((_, reject) => {
    disconnectTransportStarted();
    signal.addEventListener("abort", () => {
      disconnectAbortObserved(signal.reason?.code);
      reject(signal.reason);
    }, { once: true });
  }),
});
const disconnectServer = createServer(disconnectHandler);
const disconnectAddress = await listen(disconnectServer);
let disconnectSocket;
try {
  disconnectSocket = createConnection({ host: "127.0.0.1", port: disconnectAddress.port });
  disconnectSocket.on("error", () => {});
  await new Promise((resolve, reject) => {
    disconnectSocket.once("connect", resolve);
    disconnectSocket.once("error", reject);
  });
  const disconnectRequest = [
    "POST /v1/chat/completions HTTP/1.1",
    `Host: 127.0.0.1:${disconnectAddress.port}`,
    "Content-Type: application/json",
    "Content-Length: 2",
    "Connection: close",
    "",
    "{}",
  ].join("\r\n");
  await new Promise((resolve, reject) => {
    disconnectSocket.write(disconnectRequest, (error) => error ? reject(error) : resolve());
  });
  await transportStarted;
  disconnectSocket.destroy();
  assert.equal(await clientAbort, "client_disconnected");
} finally {
  disconnectSocket?.destroy();
  await close(disconnectServer);
}

process.stdout.write(`${JSON.stringify({
  bounded_concurrency_verified: true,
  bounded_method_path_size_and_timeout_verified: true,
  abort_on_total_timeout_verified: true,
  candidate_source_only: true,
  client_disconnect_abort_verified: true,
  credential_and_upstream_detail_omission_verified: true,
  dns_rebind_pinned_lookup_verified: true,
  exact_provider_route_allowlist_verified: true,
  fixed_internal_base_url_verified: true,
  fixed_listener_contract_verified: true,
  healthcheck_contract_verified: true,
  network_policy_verified: false,
  no_external_network_used: true,
  ok: true,
  production_dependency_language: "javascript",
  redirect_rejected: true,
  response_stream_destroyed_on_timeout: true,
  slot_released_after_timeout: true,
  reserved_dns_results_rejected: true,
  upstream_origin_operator_fixed: true,
})}\n`);
