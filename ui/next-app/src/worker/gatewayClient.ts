import type { GatewayPort } from "./contracts";
import { boundedInteger, safeIdentifier } from "./redaction";

const MAX_RESPONSE_BYTES = 1024 * 1024;

export class GatewayHttpError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(`agent_gateway_request_failed:${status}:${code}`);
    this.name = "GatewayHttpError";
    this.status = status;
    this.code = code;
  }
}

function isLoopback(hostname: string) {
  return ["127.0.0.1", "::1", "[::1]", "localhost"].includes(
    hostname.toLowerCase(),
  ) || hostname.toLowerCase().endsWith(".localhost");
}

export function validateGatewayBaseUrl(
  value: string,
  allowInsecureLoopback = false,
) {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("agent_gateway_url_invalid");
  }
  if (
    url.username
    || url.password
    || url.search
    || url.hash
    || !["http:", "https:"].includes(url.protocol)
  ) {
    throw new Error("agent_gateway_url_invalid");
  }
  if (
    url.protocol !== "https:"
    && !(allowInsecureLoopback && isLoopback(url.hostname))
  ) {
    throw new Error("agent_gateway_https_required");
  }
  url.pathname = url.pathname.replace(/\/+$/, "");
  return url;
}

async function readBoundedResponse(response: Response) {
  const declared = Number(response.headers.get("content-length") || 0);
  if (declared > MAX_RESPONSE_BYTES) {
    throw new GatewayHttpError(response.status, "response_too_large");
  }
  if (!response.body) return "";
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_RESPONSE_BYTES) {
      await reader.cancel();
      throw new GatewayHttpError(response.status, "response_too_large");
    }
    chunks.push(value);
  }
  const merged = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(merged);
}

function responseErrorCode(payload: unknown) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return "request_rejected";
  }
  const code = String((payload as Record<string, unknown>).error || "");
  return /^[a-z][a-z0-9_]{0,79}$/.test(code) ? code : "request_rejected";
}

export class HttpGatewayClient implements GatewayPort {
  readonly #baseUrl: URL;
  readonly #workspaceId: string;
  readonly #agentId: string;
  readonly #token: string;
  readonly #timeoutMs: number;

  constructor(options: {
    baseUrl: string;
    workspaceId: string;
    agentId: string;
    token: string;
    timeoutMs?: number;
    allowInsecureLoopback?: boolean;
  }) {
    this.#baseUrl = validateGatewayBaseUrl(
      options.baseUrl,
      options.allowInsecureLoopback,
    );
    this.#workspaceId = safeIdentifier(options.workspaceId, "workspace_id");
    this.#agentId = safeIdentifier(options.agentId, "agent_id");
    this.#token = String(options.token || "");
    if (Buffer.byteLength(this.#token, "utf8") < 16) {
      throw new Error("agent_gateway_token_required");
    }
    this.#timeoutMs = boundedInteger(
      options.timeoutMs,
      60_000,
      1_000,
      300_000,
    );
  }

  async #request<T extends Record<string, unknown>>(
    method: "GET" | "POST",
    path: string,
    body?: Record<string, unknown>,
    query?: Record<string, string | number | boolean | string[] | undefined>,
  ): Promise<T> {
    if (!path.startsWith("/") || path.startsWith("//")) {
      throw new Error("agent_gateway_path_invalid");
    }
    const url = new URL(this.#baseUrl);
    const prefix = this.#baseUrl.pathname.replace(/\/+$/, "");
    url.pathname = `${prefix}${path}`.replace(/\/{2,}/g, "/");
    url.search = "";
    for (const [key, raw] of Object.entries(query || {})) {
      if (raw === undefined) continue;
      for (const value of Array.isArray(raw) ? raw : [raw]) {
        url.searchParams.append(key, String(value));
      }
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.#timeoutMs);
    let response: Response;
    try {
      response = await fetch(url, {
        method,
        redirect: "manual",
        signal: controller.signal,
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.#token}`,
          "X-AgentOps-Workspace-Id": this.#workspaceId,
          "X-AgentOps-Agent-Id": this.#agentId,
          "User-Agent": "agentops-commercial-worker-ts/0.1",
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (error) {
      const code = error instanceof Error && error.name === "AbortError"
        ? "request_timeout"
        : "transport_unavailable";
      throw new GatewayHttpError(0, code);
    } finally {
      clearTimeout(timeout);
    }
    if (response.status >= 300 && response.status < 400) {
      throw new GatewayHttpError(response.status, "redirect_forbidden");
    }
    const raw = await readBoundedResponse(response);
    let payload: unknown = {};
    try {
      payload = raw ? JSON.parse(raw) : {};
    } catch {
      throw new GatewayHttpError(response.status, "invalid_json_response");
    }
    if (!response.ok) {
      throw new GatewayHttpError(response.status, responseErrorCode(payload));
    }
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new GatewayHttpError(response.status, "invalid_object_response");
    }
    return payload as T;
  }

  get<T extends Record<string, unknown>>(
    path: string,
    query?: Record<string, string | number | boolean | string[] | undefined>,
  ) {
    return this.#request<T>("GET", path, undefined, query);
  }

  post<T extends Record<string, unknown>>(
    path: string,
    body: Record<string, unknown>,
  ) {
    return this.#request<T>("POST", path, body);
  }
}
