#!/usr/bin/env node

import { lookup as dnsLookup } from "node:dns/promises";
import { request as httpRequest, createServer } from "node:http";
import { request as httpsRequest } from "node:https";
import { BlockList, isIP } from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const UPSTREAM_ORIGIN_ENV = "OPENCLAW_EGRESS_GATEWAY_UPSTREAM_ORIGIN";
export const LISTEN_HOST = "0.0.0.0";
export const LISTEN_PORT = 18080;
export const HEALTHCHECK_HOST = "127.0.0.1";
export const INTERNAL_BASE_URL = "http://openclaw-egress-gateway:18080/v1";
export const MAX_REQUEST_BYTES = 1024 * 1024;
export const MAX_RESPONSE_BYTES = 4 * 1024 * 1024;
export const MAX_CONCURRENCY = 8;
export const UPSTREAM_TIMEOUT_MS = 30_000;

const HEALTH_PATH = "/health";
const MAX_HEADER_BYTES = 16 * 1024;
const MAX_DNS_ANSWERS = 16;
const HEALTHCHECK_TIMEOUT_MS = 2_000;
const HEALTHCHECK_MAX_BYTES = 1024;
const ALLOWED_ROUTES = new Set([
  "/v1/chat/completions",
  "/v1/messages",
  "/v1/responses",
]);
const FORWARDED_REQUEST_HEADERS = Object.freeze([
  "authorization",
  "x-api-key",
  "anthropic-version",
  "openai-organization",
  "openai-project",
]);
const DNS_NAME = /^(?=.{1,253}\.?$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.?$/u;
const JSON_CONTENT_TYPE = /^application\/json(?:\s*;\s*charset=utf-8)?$/iu;

const FORBIDDEN_IPV4 = new BlockList();
for (const [network, prefix] of [
  ["0.0.0.0", 8],
  ["10.0.0.0", 8],
  ["100.64.0.0", 10],
  ["127.0.0.0", 8],
  ["169.254.0.0", 16],
  ["172.16.0.0", 12],
  ["192.0.0.0", 24],
  ["192.0.2.0", 24],
  ["192.88.99.0", 24],
  ["192.168.0.0", 16],
  ["198.18.0.0", 15],
  ["198.51.100.0", 24],
  ["203.0.113.0", 24],
  ["224.0.0.0", 4],
  ["240.0.0.0", 4],
]) FORBIDDEN_IPV4.addSubnet(network, prefix, "ipv4");

const GLOBAL_IPV6 = new BlockList();
GLOBAL_IPV6.addSubnet("2000::", 3, "ipv6");
const FORBIDDEN_GLOBAL_IPV6 = new BlockList();
for (const [network, prefix] of [
  ["2001::", 32],
  ["2001:2::", 48],
  ["2001:10::", 28],
  ["2001:20::", 28],
  ["2001:db8::", 32],
  ["2002::", 16],
]) FORBIDDEN_GLOBAL_IPV6.addSubnet(network, prefix, "ipv6");

class GatewayError extends Error {
  constructor(code, statusCode) {
    super(code);
    this.code = code;
    this.statusCode = statusCode;
  }
}

function fail(code, statusCode = 500) {
  throw new GatewayError(code, statusCode);
}

function fixedJson(value) {
  return Buffer.from(`${JSON.stringify(value)}\n`, "utf8");
}

function normalizeHostname(value) {
  return String(value || "").replace(/^\[|\]$/gu, "").replace(/\.$/u, "").toLowerCase();
}

export function parseUpstreamOrigin(value) {
  let parsed;
  try {
    parsed = new URL(String(value || ""));
  } catch {
    fail("upstream_origin_invalid");
  }
  const hostname = normalizeHostname(parsed.hostname);
  if (
    parsed.protocol !== "https:"
    || parsed.username
    || parsed.password
    || parsed.pathname !== "/"
    || parsed.search
    || parsed.hash
    || !hostname
    || isIP(hostname) !== 0
    || hostname === "localhost"
    || hostname.endsWith(".localhost")
    || !DNS_NAME.test(hostname)
  ) fail("upstream_origin_invalid");
  return Object.freeze({
    hostname,
    origin: parsed.origin,
    port: parsed.port ? Number(parsed.port) : 443,
  });
}

export function addressIsForbidden(address) {
  const normalized = String(address || "").toLowerCase();
  const family = isIP(normalized);
  if (family === 4) return FORBIDDEN_IPV4.check(normalized, "ipv4");
  if (family !== 6) return true;
  if (normalized.startsWith("::ffff:")) {
    const mapped = normalized.slice("::ffff:".length);
    return isIP(mapped) !== 4 || FORBIDDEN_IPV4.check(mapped, "ipv4");
  }
  return !GLOBAL_IPV6.check(normalized, "ipv6")
    || FORBIDDEN_GLOBAL_IPV6.check(normalized, "ipv6");
}

export function validateResolvedAddresses(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_DNS_ANSWERS) {
    fail("upstream_dns_rejected", 502);
  }
  const unique = new Map();
  for (const entry of value) {
    const address = typeof entry === "string" ? entry : entry?.address;
    const family = isIP(String(address || ""));
    if (![4, 6].includes(family) || addressIsForbidden(address)) {
      fail("upstream_dns_rejected", 502);
    }
    if (entry?.family !== undefined && Number(entry.family) !== family) {
      fail("upstream_dns_rejected", 502);
    }
    unique.set(`${family}:${String(address).toLowerCase()}`, Object.freeze({
      address: String(address).toLowerCase(),
      family,
    }));
  }
  return Object.freeze([...unique.values()]);
}

export function createPinnedLookup(expectedHostname, addresses) {
  const expected = normalizeHostname(expectedHostname);
  const pinned = validateResolvedAddresses(addresses);
  return (hostname, options, callback) => {
    const settings = typeof options === "object" && options !== null ? options : {};
    const requestedFamily = typeof options === "number" ? options : Number(settings.family || 0);
    const done = typeof options === "function" ? options : callback;
    if (typeof done !== "function") return;
    if (normalizeHostname(hostname) !== expected) {
      done(new GatewayError("pinned_lookup_hostname_rejected", 502));
      return;
    }
    const eligible = requestedFamily === 0
      ? pinned
      : pinned.filter((entry) => entry.family === requestedFamily);
    if (eligible.length === 0) {
      done(new GatewayError("pinned_lookup_family_rejected", 502));
      return;
    }
    if (settings.all === true) {
      done(null, eligible.map((entry) => ({ ...entry })));
      return;
    }
    done(null, eligible[0].address, eligible[0].family);
  };
}

async function defaultResolveHost(hostname) {
  return dnsLookup(hostname, { all: true, verbatim: true });
}

function abortReason(signal) {
  return signal.reason instanceof GatewayError
    ? signal.reason
    : new GatewayError("upstream_aborted", 502);
}

function abortable(promise, signal) {
  if (signal.aborted) return Promise.reject(abortReason(signal));
  let onAbort;
  const aborted = new Promise((_, reject) => {
    onAbort = () => reject(abortReason(signal));
    signal.addEventListener("abort", onAbort, { once: true });
  });
  return Promise.race([Promise.resolve(promise), aborted])
    .finally(() => signal.removeEventListener("abort", onAbort));
}

function defaultRequestUpstream(options) {
  return new Promise((resolve, reject) => {
    const request = httpsRequest({
      protocol: "https:",
      hostname: options.upstream.hostname,
      port: options.upstream.port,
      servername: options.upstream.hostname,
      method: "POST",
      path: options.path,
      headers: options.headers,
      lookup: options.lookup,
      signal: options.signal,
      agent: false,
    }, resolve);
    request.once("error", (error) => {
      reject(options.signal.aborted ? abortReason(options.signal) : error);
    });
    request.end(options.body);
  });
}

function sendBuffer(response, statusCode, contentType, body) {
  if (response.headersSent || response.destroyed) return;
  response.writeHead(statusCode, {
    "cache-control": "no-store",
    connection: "close",
    "content-length": body.byteLength,
    "content-type": contentType,
    "x-content-type-options": "nosniff",
  });
  response.end(body);
}

function sendError(response, error) {
  const known = error instanceof GatewayError;
  const statusCode = known ? error.statusCode : 502;
  const code = known ? error.code : "gateway_failure";
  sendBuffer(response, statusCode, "application/json; charset=utf-8", fixedJson({
    error: { code },
  }));
}

function requestHeaderBytes(request) {
  return request.rawHeaders.reduce((size, value) => size + Buffer.byteLength(value), 0);
}

function requiredContentLength(request) {
  const raw = request.headers["content-length"];
  if (request.headers["transfer-encoding"] !== undefined) fail("request_framing_rejected", 400);
  if (typeof raw !== "string" || !/^(?:0|[1-9][0-9]*)$/u.test(raw)) {
    fail("request_content_length_required", 411);
  }
  const size = Number(raw);
  if (!Number.isSafeInteger(size) || size < 2 || size > MAX_REQUEST_BYTES) {
    fail("request_too_large", 413);
  }
  return size;
}

async function readRequestBody(request, expectedBytes) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.byteLength;
    if (size > MAX_REQUEST_BYTES || size > expectedBytes) fail("request_too_large", 413);
    chunks.push(Buffer.from(chunk));
  }
  if (size !== expectedBytes) fail("request_length_mismatch", 400);
  return Buffer.concat(chunks);
}

function upstreamHeaders(request, body) {
  const result = {
    accept: "application/json, text/event-stream",
    "content-length": String(body.byteLength),
    "content-type": "application/json",
  };
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers[name];
    if (typeof value === "string" && value.length <= 8 * 1024 && !/[\r\n]/u.test(value)) {
      result[name] = value;
    }
  }
  return result;
}

async function readUpstreamResponse(response, signal) {
  const onAbort = () => response?.destroy?.(abortReason(signal));
  signal.addEventListener("abort", onAbort, { once: true });
  try {
    if (signal.aborted) throw abortReason(signal);
    const statusCode = Number(response?.statusCode);
    if (!Number.isInteger(statusCode) || statusCode < 100 || statusCode > 599) {
      fail("upstream_protocol_rejected", 502);
    }
    if (statusCode >= 300 && statusCode < 400) fail("upstream_redirect_rejected", 502);
    if (statusCode < 200 || statusCode >= 300) fail("upstream_rejected", 502);
    const declared = response.headers?.["content-length"];
    if (declared !== undefined) {
      if (!/^(?:0|[1-9][0-9]*)$/u.test(String(declared)) || Number(declared) > MAX_RESPONSE_BYTES) {
        fail("upstream_response_too_large", 502);
      }
    }
    const contentType = String(response.headers?.["content-type"] || "application/json")
      .split(";", 1)[0]
      .trim()
      .toLowerCase();
    if (!["application/json", "text/event-stream"].includes(contentType)) {
      fail("upstream_content_type_rejected", 502);
    }
    const chunks = [];
    let size = 0;
    try {
      for await (const chunk of response) {
        size += chunk.byteLength;
        if (size > MAX_RESPONSE_BYTES) fail("upstream_response_too_large", 502);
        chunks.push(Buffer.from(chunk));
      }
    } catch (error) {
      if (signal.aborted) throw abortReason(signal);
      throw error;
    }
    return Object.freeze({
      body: Buffer.concat(chunks),
      contentType: contentType === "text/event-stream"
        ? "text/event-stream"
        : "application/json; charset=utf-8",
      statusCode,
    });
  } finally {
    signal.removeEventListener("abort", onAbort);
  }
}

export function createGatewayHandler({
  environment = process.env,
  resolveHost = defaultResolveHost,
  requestUpstream = defaultRequestUpstream,
  upstreamTimeoutMs = UPSTREAM_TIMEOUT_MS,
} = {}) {
  const upstream = parseUpstreamOrigin(environment[UPSTREAM_ORIGIN_ENV]);
  if (!Number.isSafeInteger(upstreamTimeoutMs) || upstreamTimeoutMs < 10 || upstreamTimeoutMs > UPSTREAM_TIMEOUT_MS) {
    fail("gateway_timeout_invalid");
  }
  let activeRequests = 0;
  return async function gatewayHandler(request, response) {
    response.on("error", () => {});
    if (request.method === "GET" && request.url === HEALTH_PATH) {
      sendBuffer(response, 200, "application/json; charset=utf-8", fixedJson({
        schema: "agentops_openclaw_egress_gateway_health_v1",
        ok: true,
        ready: true,
      }));
      return;
    }
    try {
      if (requestHeaderBytes(request) > MAX_HEADER_BYTES) fail("request_headers_too_large", 431);
      if (request.method !== "POST") fail("request_method_rejected", 405);
      if (!ALLOWED_ROUTES.has(request.url)) fail("request_path_rejected", 404);
      if (!JSON_CONTENT_TYPE.test(String(request.headers["content-type"] || ""))) {
        fail("request_content_type_rejected", 415);
      }
      if (request.headers["content-encoding"] !== undefined) {
        fail("request_content_encoding_rejected", 415);
      }
      const expectedBytes = requiredContentLength(request);
      if (activeRequests >= MAX_CONCURRENCY) fail("request_concurrency_exceeded", 503);
      activeRequests += 1;
      let deadline;
      let rawResponse;
      let result;
      const controller = new AbortController();
      const abortForClientDisconnect = () => {
        if (!response.writableEnded) {
          controller.abort(new GatewayError("client_disconnected", 499));
        }
      };
      try {
        const body = await readRequestBody(request, expectedBytes);
        request.once("aborted", abortForClientDisconnect);
        response.once("close", abortForClientDisconnect);
        if (request.aborted || response.destroyed) abortForClientDisconnect();
        deadline = setTimeout(() => {
          controller.abort(new GatewayError("upstream_timeout", 504));
        }, upstreamTimeoutMs);
        deadline.unref?.();
        const resolved = await abortable(resolveHost(upstream.hostname), controller.signal);
        const pinned = validateResolvedAddresses(resolved);
        const lookup = createPinnedLookup(upstream.hostname, pinned);
        rawResponse = await abortable(requestUpstream({
          body,
          headers: upstreamHeaders(request, body),
          lookup,
          path: request.url,
          signal: controller.signal,
          timeoutMs: upstreamTimeoutMs,
          upstream,
        }), controller.signal);
        result = await readUpstreamResponse(rawResponse, controller.signal);
      } finally {
        clearTimeout(deadline);
        request.removeListener("aborted", abortForClientDisconnect);
        response.removeListener("close", abortForClientDisconnect);
        if (result === undefined) rawResponse?.destroy?.();
        activeRequests -= 1;
      }
      sendBuffer(response, result.statusCode, result.contentType, result.body);
    } catch (error) {
      sendError(response, error);
    }
  };
}

export function startGateway(dependencies = {}) {
  const handler = createGatewayHandler(dependencies);
  const server = createServer({
    maxHeaderSize: MAX_HEADER_BYTES,
    requireHostHeader: true,
  }, handler);
  server.headersTimeout = 5_000;
  server.requestTimeout = UPSTREAM_TIMEOUT_MS + 5_000;
  server.keepAliveTimeout = 1_000;
  server.maxHeadersCount = 32;
  server.on("clientError", (_error, socket) => {
    socket.on("error", () => {});
    if (!socket.destroyed) {
      socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n");
    }
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(LISTEN_PORT, LISTEN_HOST, () => {
      server.off("error", reject);
      resolve(server);
    });
  });
}

export function checkGatewayHealth({
  host = HEALTHCHECK_HOST,
  port = LISTEN_PORT,
  timeoutMs = HEALTHCHECK_TIMEOUT_MS,
} = {}) {
  return new Promise((resolve, reject) => {
    const request = httpRequest({
      host,
      port,
      method: "GET",
      path: HEALTH_PATH,
      headers: { connection: "close" },
    }, async (response) => {
      try {
        const chunks = [];
        let size = 0;
        for await (const chunk of response) {
          size += chunk.byteLength;
          if (size > HEALTHCHECK_MAX_BYTES) fail("healthcheck_response_rejected");
          chunks.push(Buffer.from(chunk));
        }
        const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        if (
          response.statusCode !== 200
          || payload?.schema !== "agentops_openclaw_egress_gateway_health_v1"
          || payload.ok !== true
          || payload.ready !== true
        ) fail("healthcheck_response_rejected");
        resolve(true);
      } catch {
        reject(new GatewayError("healthcheck_failed", 500));
      }
    });
    request.setTimeout(timeoutMs, () => request.destroy(new GatewayError("healthcheck_failed", 500)));
    request.once("error", () => reject(new GatewayError("healthcheck_failed", 500)));
    request.end();
  });
}

async function runCli() {
  const arguments_ = process.argv.slice(2);
  if (arguments_.length === 1 && arguments_[0] === "--healthcheck") {
    await checkGatewayHealth();
    return;
  }
  if (arguments_.length !== 0) fail("arguments_rejected");
  const server = await startGateway();
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.once(signal, () => server.close(() => process.exit(0)));
  }
}

const entrypoint = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (entrypoint === fileURLToPath(import.meta.url)) {
  runCli().catch(() => {
    process.stderr.write("openclaw_egress_gateway_failed\n");
    process.exitCode = 1;
  });
}
