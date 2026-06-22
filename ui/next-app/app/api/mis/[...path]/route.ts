import http from "node:http";
import https from "node:https";
import { NextRequest, NextResponse } from "next/server";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

type ProxyResponse = {
  status: number;
  statusText: string;
  headers: Headers;
  body: Buffer;
};

export const runtime = "nodejs";

function proxyUrl(path: string[], search: string) {
  const cleanPath = path.map((part) => encodeURIComponent(part)).join("/");
  return `${TARGET_BASE.replace(/\/$/, "")}/${cleanPath}${search}`;
}

function isWorkerDispatchPath(path: string[]) {
  return path.join("/") === "workers/local/dispatch-once";
}

function isWorkerReleasePath(path: string[]) {
  return path.join("/") === "workers/tasks/release";
}

function parseJsonBody(body: Buffer | undefined) {
  if (!body || body.byteLength === 0) return {};
  return JSON.parse(body.toString("utf-8"));
}

function workerDispatchAdapter(body: Buffer | undefined) {
  if (!body || body.byteLength === 0) return "mock";
  try {
    const parsed = parseJsonBody(body);
    if (parsed && typeof parsed === "object" && "adapter" in parsed) {
      return String((parsed as { adapter?: unknown }).adapter || "mock");
    }
  } catch {
    return "invalid_json";
  }
  return "mock";
}

function workerReleaseGuard(body: Buffer | undefined) {
  try {
    const parsed = parseJsonBody(body);
    if (!parsed || typeof parsed !== "object") {
      return { ok: false, status: 400, error: "invalid_json" };
    }
    const input = parsed as { task_id?: unknown; force?: unknown };
    if (!input.task_id || typeof input.task_id !== "string") {
      return { ok: false, status: 400, error: "task_id_required" };
    }
    if (input.force) {
      return { ok: false, status: 403, error: "force_release_not_allowed_next_parity" };
    }
    return { ok: true, status: 200, error: "" };
  } catch {
    return { ok: false, status: 400, error: "invalid_json" };
  }
}

function forwardedHeaders(request: NextRequest) {
  const headers = new Headers();
  for (const [key, value] of request.headers.entries()) {
    const normalized = key.toLowerCase();
    if (!HOP_BY_HOP_HEADERS.has(normalized) && normalized !== "host" && normalized !== "content-length") {
      headers.set(key, value);
    }
  }
  return headers;
}

function proxyRequest(target: string, method: string, headers: Headers, body: Buffer | undefined): Promise<ProxyResponse> {
  return new Promise((resolve, reject) => {
    const url = new URL(target);
    const client = url.protocol === "https:" ? https : http;
    const requestHeaders: Record<string, string> = {};
    headers.forEach((value, key) => {
      requestHeaders[key] = value;
    });
    if (body) {
      requestHeaders["content-length"] = String(body.byteLength);
    }

    const upstream = client.request(url, { method, headers: requestHeaders }, (response) => {
      const chunks: Buffer[] = [];
      response.on("data", (chunk: Buffer | string) => {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      });
      response.on("end", () => {
        const responseHeaders = new Headers();
        for (const [key, value] of Object.entries(response.headers)) {
          if (Array.isArray(value)) {
            for (const item of value) {
              responseHeaders.append(key, item);
            }
          } else if (value !== undefined) {
            responseHeaders.set(key, String(value));
          }
        }
        resolve({
          status: response.statusCode || 502,
          statusText: response.statusMessage || "",
          headers: responseHeaders,
          body: Buffer.concat(chunks),
        });
      });
    });
    upstream.on("error", reject);
    if (body) {
      upstream.write(body);
    }
    upstream.end();
  });
}

async function proxy(request: NextRequest, context: RouteContext) {
  const { path = [] } = await context.params;
  const body = ["GET", "HEAD"].includes(request.method)
    ? undefined
    : Buffer.from(new Uint8Array(await request.arrayBuffer()));
  if (request.method === "POST" && isWorkerDispatchPath(path)) {
    const adapter = workerDispatchAdapter(body);
    if (adapter !== "mock") {
      return NextResponse.json({ ok: false, error: adapter === "invalid_json" ? "invalid_json" : "mock_only_next_parity" }, { status: 403 });
    }
  }
  if (request.method === "POST" && isWorkerReleasePath(path)) {
    const guard = workerReleaseGuard(body);
    if (!guard.ok) {
      return NextResponse.json({ released: false, error: guard.error }, { status: guard.status });
    }
  }
  const response = await proxyRequest(proxyUrl(path, request.nextUrl.search), request.method, forwardedHeaders(request), body);
  const headers = new Headers(response.headers);
  for (const key of HOP_BY_HOP_HEADERS) {
    headers.delete(key);
  }
  headers.delete("content-length");
  return new NextResponse(response.body.byteLength > 0 ? response.body : null, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
