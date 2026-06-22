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
const VALID_AGENT_GATEWAY_SCOPES = new Set([
  "agents:write",
  "agents:heartbeat",
  "agent_plans:read",
  "agent_plans:write",
  "plan_evidence:read",
  "plan_evidence:write",
  "knowledge:read",
  "knowledge:write",
  "tasks:create",
  "tasks:read",
  "tasks:claim",
  "runs:write",
  "toolcalls:write",
  "artifacts:write",
  "approvals:request",
  "memories:propose",
  "evaluations:submit",
  "audit:write",
]);
const VALID_RUNTIME_TYPES = new Set(["mock", "hermes", "openclaw"]);

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

function isEnrollmentRequestPath(path: string[]) {
  return path.join("/") === "agent-gateway/enrollment/request";
}

function isEnrollmentPath(path: string[]) {
  return path.join("/").startsWith("agent-gateway/enrollment/");
}

function isEnrollmentPolicyPreviewPath(path: string[]) {
  return path.join("/") === "agent-gateway/enrollment/policy-preview";
}

function isEnrollmentTokenIssuePath(path: string[]) {
  return [
    "agent-gateway/enrollment/create",
    "agent-gateway/enrollment/issue-approved",
    "agent-gateway/enrollment/rotate",
  ].includes(path.join("/"));
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

function normalizedScopes(value: unknown) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value.split(/[\s,]+/).map((scope) => scope.trim()).filter(Boolean);
  }
  return [];
}

function validateEnrollmentBasics(input: {
  agent_id?: unknown;
  workspace_id?: unknown;
  runtime_type?: unknown;
  runtime?: unknown;
  scopes?: unknown;
  allowed_scopes?: unknown;
  ttl_days?: unknown;
  heartbeat_timeout_sec?: unknown;
}, options: { requireAgentId: boolean }) {
  const agentId = String(input.agent_id || "").trim();
  const workspaceId = String(input.workspace_id || "local-demo").trim();
  const runtime = String(input.runtime_type || input.runtime || "mock").trim();
  const scopes = normalizedScopes(input.scopes || input.allowed_scopes);
  if (options.requireAgentId && (!agentId || agentId.length > 96 || !/^[A-Za-z0-9_.:-]+$/.test(agentId))) {
    return { ok: false, status: 400, error: "agent_id_invalid" };
  }
  if (!workspaceId || workspaceId.length > 96 || !/^[A-Za-z0-9_.:-]+$/.test(workspaceId)) {
    return { ok: false, status: 400, error: "workspace_id_invalid" };
  }
  if (!VALID_RUNTIME_TYPES.has(runtime)) {
    return { ok: false, status: 400, error: "runtime_type_invalid" };
  }
  if (!scopes.length) {
    return { ok: false, status: 400, error: "scopes_required" };
  }
  const invalidScopes = scopes.filter((scope) => !VALID_AGENT_GATEWAY_SCOPES.has(scope));
  if (invalidScopes.length) {
    return { ok: false, status: 400, error: "invalid_scopes", invalid_scopes: invalidScopes };
  }
  if (input.ttl_days !== undefined) {
    const ttlDays = Number(input.ttl_days);
    if (!Number.isFinite(ttlDays) || ttlDays < 1 || ttlDays > 365) {
      return { ok: false, status: 400, error: "ttl_days_invalid" };
    }
  }
  if (input.heartbeat_timeout_sec !== undefined) {
    const heartbeat = Number(input.heartbeat_timeout_sec);
    if (!Number.isFinite(heartbeat) || heartbeat < 30 || heartbeat > 86400) {
      return { ok: false, status: 400, error: "heartbeat_timeout_sec_invalid" };
    }
  }
  return { ok: true, status: 200, error: "" };
}

function enrollmentPolicyPreviewGuard(body: Buffer | undefined) {
  try {
    const parsed = parseJsonBody(body);
    if (!parsed || typeof parsed !== "object") {
      return { ok: false, status: 400, error: "invalid_json" };
    }
    return validateEnrollmentBasics(parsed as Record<string, unknown>, { requireAgentId: false });
  } catch {
    return { ok: false, status: 400, error: "invalid_json" };
  }
}

function enrollmentRequestGuard(body: Buffer | undefined) {
  try {
    const parsed = parseJsonBody(body);
    if (!parsed || typeof parsed !== "object") {
      return { ok: false, status: 400, error: "invalid_json" };
    }
    const input = parsed as {
      agent_id?: unknown;
      name?: unknown;
      scopes?: unknown;
      token?: unknown;
      token_id?: unknown;
      issue_now?: unknown;
      issue_token?: unknown;
      approved?: unknown;
    };
    const basics = validateEnrollmentBasics(input, { requireAgentId: true });
    if (!basics.ok) {
      return basics;
    }
    if (
      input.token !== undefined
      || input.token_id !== undefined
      || input.issue_now !== undefined
      || input.issue_token !== undefined
      || input.approved !== undefined
    ) {
      return { ok: false, status: 403, error: "enrollment_request_token_fields_not_allowed_next_parity" };
    }
    if (!input.agent_id || typeof input.agent_id !== "string") {
      return { ok: false, status: 400, error: "agent_id_required" };
    }
    if (!input.name || typeof input.name !== "string") {
      return { ok: false, status: 400, error: "name_required" };
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
  if (request.method === "POST" && isEnrollmentTokenIssuePath(path)) {
    return NextResponse.json({
      ok: false,
      error: "enrollment_token_issue_not_allowed_next_parity",
      token_issued: false,
      token_omitted: true,
    }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  if (request.method === "POST" && isEnrollmentPolicyPreviewPath(path)) {
    const guard = enrollmentPolicyPreviewGuard(body);
    if (!guard.ok) {
      return NextResponse.json({ ok: false, error: guard.error, invalid_scopes: "invalid_scopes" in guard ? guard.invalid_scopes : undefined, token_omitted: true }, { status: guard.status, headers: { "Cache-Control": "no-store" } });
    }
  }
  if (request.method === "POST" && isEnrollmentRequestPath(path)) {
    const guard = enrollmentRequestGuard(body);
    if (!guard.ok) {
      return NextResponse.json({ ok: false, error: guard.error, invalid_scopes: "invalid_scopes" in guard ? guard.invalid_scopes : undefined, token_issued: false, token_omitted: true }, { status: guard.status, headers: { "Cache-Control": "no-store" } });
    }
  }
  const response = await proxyRequest(proxyUrl(path, request.nextUrl.search), request.method, forwardedHeaders(request), body);
  const headers = new Headers(response.headers);
  for (const key of HOP_BY_HOP_HEADERS) {
    headers.delete(key);
  }
  headers.delete("content-length");
  if (isEnrollmentPath(path)) {
    headers.set("cache-control", "no-store");
  }
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
