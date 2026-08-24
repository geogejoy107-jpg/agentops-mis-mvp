import { lstat } from "node:fs/promises";
import { request as httpRequest } from "node:http";
import { isAbsolute } from "node:path";

import type {
  PromptBundle,
  RuntimeAdapter,
  RuntimeAdapterResult,
} from "./contracts";
import {
  boundedInteger,
  redactText,
  sha256,
  stableHash,
} from "./redaction";

const MAX_RUNTIME_RESPONSE_BYTES = 1024 * 1024;
const PROVIDER_RESPONSE_OMITTED =
  "Provider response omitted; execution metadata and payload hash recorded.";
const PROVIDER_EMPTY_RESPONSE =
  "Provider response omitted; no visible assistant content was returned.";
const OPENCLAW_PROVIDER_REQUEST_SCHEMA =
  "agentops_openclaw_provider_request_v1";
const OPENCLAW_EXECUTOR_PUBLIC_REQUEST_SCHEMA =
  "agentops_openclaw_executor_public_request_v2";
const OPENCLAW_PROVIDER_RESPONSE_SCHEMA =
  "agentops_openclaw_provider_response_v1";
const SHA256_HEX = /^[a-f0-9]{64}$/;
const PROVIDER_ERROR_TYPE = /^[A-Za-z][A-Za-z0-9]{0,119}$/;
const PROVIDER_MODEL_NAME = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$/;
const OPENCLAW_PROVIDER_ERROR_MESSAGE =
  "Provider error detail omitted; OpenClaw execution failed.";
const OPENCLAW_PROVIDER_RESPONSE_KEYS = Object.freeze([
  "dry_run",
  "duration_ms",
  "error_message",
  "error_type",
  "model_name",
  "ok",
  "output_present",
  "output_tokens",
  "provider_call_performed",
  "raw_payload_hash",
  "raw_prompt_omitted",
  "raw_response_omitted",
  "retryable",
  "schema",
]);

function hasVisibleProviderContent(value: unknown) {
  return typeof value === "string" && value.trim().length > 0;
}

function loopbackHost(hostname: string) {
  return ["127.0.0.1", "::1", "[::1]", "localhost"].includes(
    hostname.toLowerCase(),
  ) || hostname.toLowerCase().endsWith(".localhost");
}

function runtimeUrl(value: string) {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("runtime_url_invalid");
  }
  if (
    url.username
    || url.password
    || url.search
    || url.hash
    || !["http:", "https:"].includes(url.protocol)
    || (url.protocol === "http:" && !loopbackHost(url.hostname))
  ) {
    throw new Error("runtime_url_invalid");
  }
  url.pathname = url.pathname.replace(/\/+$/, "");
  return url;
}

async function boundedRuntimeText(response: Response) {
  const declared = Number(response.headers.get("content-length") || 0);
  if (declared > MAX_RUNTIME_RESPONSE_BYTES) {
    throw new Error("runtime_response_too_large");
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength > MAX_RUNTIME_RESPONSE_BYTES) {
    throw new Error("runtime_response_too_large");
  }
  return new TextDecoder().decode(bytes);
}

async function unixSocketJson(options: {
  socketPath: string;
  path: string;
  body: Record<string, unknown>;
  timeoutMs: number;
  signal?: AbortSignal;
}) {
  const body = JSON.stringify(options.body);
  if (Buffer.byteLength(body, "utf8") > MAX_RUNTIME_RESPONSE_BYTES) {
    throw new Error("runtime_request_too_large");
  }
  return await new Promise<Record<string, unknown>>((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    const request = httpRequest({
      socketPath: options.socketPath,
      path: options.path,
      method: "POST",
      signal: options.signal,
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body, "utf8"),
      },
    }, (response) => {
      const declared = Number(response.headers["content-length"] || 0);
      const contentType = String(response.headers["content-type"] || "")
        .split(";", 1)[0]
        .trim()
        .toLowerCase();
      if (
        declared > MAX_RUNTIME_RESPONSE_BYTES
        || contentType !== "application/json"
      ) {
        request.destroy(new Error("openclaw_provider_response_boundary_invalid"));
        return;
      }
      response.once("error", reject);
      response.on("data", (chunk: Buffer) => {
        size += chunk.byteLength;
        if (size > MAX_RUNTIME_RESPONSE_BYTES) {
          request.destroy(new Error("runtime_response_too_large"));
          return;
        }
        chunks.push(chunk);
      });
      response.on("end", () => {
        if (size > MAX_RUNTIME_RESPONSE_BYTES) return;
        const raw = Buffer.concat(chunks).toString("utf8");
        if (response.statusCode !== 200) {
          reject(new Error(`openclaw_provider_http_${response.statusCode || 0}`));
          return;
        }
        try {
          const value = JSON.parse(raw) as unknown;
          if (!value || typeof value !== "object" || Array.isArray(value)) {
            throw new Error("openclaw_provider_response_object_required");
          }
          resolve(value as Record<string, unknown>);
        } catch {
          reject(new Error("openclaw_provider_response_invalid_json"));
        }
      });
    });
    request.setTimeout(options.timeoutMs, () => {
      request.destroy(new Error("openclaw_provider_timeout"));
    });
    request.once("error", reject);
    request.end(body);
  });
}

export class HermesAdapter implements RuntimeAdapter {
  readonly runtime = "hermes" as const;
  readonly modelName: string;
  readonly #gatewayUrl: URL;
  readonly #timeoutMs: number;
  readonly #maxTokens: number;

  constructor(options: {
    gatewayUrl: string;
    model?: string;
    timeoutMs?: number;
    maxTokens?: number;
  }) {
    this.#gatewayUrl = runtimeUrl(options.gatewayUrl);
    this.modelName = redactText(options.model || "hermes-agent", 120);
    this.#timeoutMs = boundedInteger(options.timeoutMs, 180_000, 1_000, 300_000);
    this.#maxTokens = boundedInteger(options.maxTokens, 512, 64, 4096);
  }

  async execute(bundle: PromptBundle, signal?: AbortSignal): Promise<RuntimeAdapterResult> {
    const started = Date.now();
    const endpoint = new URL(this.#gatewayUrl);
    const basePath = this.#gatewayUrl.pathname.replace(/\/+$/, "");
    endpoint.pathname = `${basePath}/v1/chat/completions`;
    const targetResource = `hermes://gateway/${
      sha256(endpoint.origin).slice(0, 20)
    }/v1/chat/completions`;
    const controller = new AbortController();
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.#timeoutMs);
    const cancel = () => controller.abort(signal?.reason);
    if (signal?.aborted) cancel();
    else signal?.addEventListener("abort", cancel, { once: true });
    let providerCallPerformed = false;
    try {
      providerCallPerformed = true;
      const response = await fetch(endpoint, {
        method: "POST",
        redirect: "manual",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: this.modelName,
          messages: [{ role: "user", content: bundle.prompt }],
          temperature: 0,
          max_tokens: this.#maxTokens,
        }),
      });
      const raw = await boundedRuntimeText(response);
      const rawPayloadHash = sha256(raw);
      if (!response.ok) {
        return {
          ok: false,
          runtime: this.runtime,
          modelName: this.modelName,
          outputSummary: `Hermes returned HTTP ${response.status}.`,
          rawPayloadHash,
          targetResource,
          durationMs: Date.now() - started,
          outputTokens: 0,
          providerCallPerformed,
          dryRun: false,
          retryable: [408, 409, 425, 429].includes(response.status)
            || response.status >= 500,
          errorType: `HermesHTTP${response.status}`,
          errorMessage: `Hermes returned HTTP ${response.status}; body omitted.`,
        };
      }
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(raw) as Record<string, unknown>;
      } catch {
        throw new Error("hermes_response_invalid_json");
      }
      const choices = Array.isArray(payload.choices) ? payload.choices : [];
      const choice = choices[0] && typeof choices[0] === "object"
        ? choices[0] as Record<string, unknown>
        : {};
      const message = choice.message && typeof choice.message === "object"
        ? choice.message as Record<string, unknown>
        : {};
      const hasVisibleContent = hasVisibleProviderContent(message.content);
      const usage = payload.usage && typeof payload.usage === "object"
        ? payload.usage as Record<string, unknown>
        : {};
      return {
        ok: hasVisibleContent,
        runtime: this.runtime,
        modelName: this.modelName,
        outputSummary: hasVisibleContent
          ? PROVIDER_RESPONSE_OMITTED
          : PROVIDER_EMPTY_RESPONSE,
        rawPayloadHash,
        targetResource,
        durationMs: Date.now() - started,
        outputTokens: boundedInteger(
          usage.completion_tokens ?? usage.output_tokens,
          0,
          0,
          10_000_000,
        ),
        providerCallPerformed,
        dryRun: false,
        retryable: !hasVisibleContent,
        errorType: hasVisibleContent ? null : "HermesEmptyResponse",
        errorMessage: hasVisibleContent
          ? null
          : "Provider error detail omitted; Hermes returned no visible content.",
      };
    } catch (error) {
      const cancelled = signal?.aborted === true;
      const timeoutError = !cancelled && timedOut
        && error instanceof Error && error.name === "AbortError";
      return {
        ok: false,
        runtime: this.runtime,
        modelName: this.modelName,
        outputSummary: "Hermes execution failed.",
        rawPayloadHash: stableHash({
          runtime: this.runtime,
          error_type: cancelled
            ? "RuntimeCancelled"
            : timeoutError ? "HermesTimeout" : "HermesExecutionFailed",
        }),
        targetResource,
        durationMs: Date.now() - started,
        outputTokens: 0,
        providerCallPerformed,
        dryRun: false,
        retryable: !cancelled,
        errorType: cancelled
          ? "RuntimeCancelled"
          : timeoutError ? "HermesTimeout" : "HermesExecutionFailed",
        errorMessage: cancelled
          ? "Runtime execution cancelled for controlled shutdown."
          : timeoutError
            ? "Hermes execution timed out."
            : "Hermes transport failed; detail omitted.",
      };
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", cancel);
    }
  }
}

export class OpenClawAdapter implements RuntimeAdapter {
  readonly runtime = "openclaw" as const;
  readonly modelName: string;
  readonly #providerSocketPath: string;
  readonly #agentName: string;
  readonly #timeoutSeconds: number;
  readonly #protocolVersion: "v1" | "v2";

  constructor(options: {
    providerSocketPath: string;
    agentName?: string;
    timeoutSeconds?: number;
    protocolVersion?: "v1" | "v2";
  }) {
    if (!isAbsolute(options.providerSocketPath)) {
      throw new Error("openclaw_provider_socket_absolute_path_required");
    }
    this.#providerSocketPath = options.providerSocketPath;
    this.#agentName = redactText(options.agentName || "main", 80);
    this.modelName = this.#agentName;
    this.#timeoutSeconds = boundedInteger(
      options.timeoutSeconds,
      180,
      1,
      600,
    );
    this.#protocolVersion = options.protocolVersion || "v1";
    if (!(["v1", "v2"] as const).includes(this.#protocolVersion)) {
      throw new Error("openclaw_provider_protocol_invalid");
    }
  }

  async execute(bundle: PromptBundle, signal?: AbortSignal): Promise<RuntimeAdapterResult> {
    return this.#executeViaProvider(bundle, signal);
  }

  async #executeViaProvider(
    bundle: PromptBundle,
    signal?: AbortSignal,
  ): Promise<RuntimeAdapterResult> {
    const started = Date.now();
    const targetResource = `local://openclaw/${this.#agentName}`;
    let providerCallPerformed = false;
    try {
      if (signal?.aborted) throw signal.reason;
      const socket = await lstat(this.#providerSocketPath);
      if (!socket.isSocket() || socket.isSymbolicLink()) {
        throw new Error("openclaw_provider_socket_invalid");
      }
      const context = bundle.executionContext;
      if (this.#protocolVersion === "v2" && !context) {
        throw new Error("openclaw_executor_execution_context_required");
      }
      const body = this.#protocolVersion === "v2"
        ? {
          schema: OPENCLAW_EXECUTOR_PUBLIC_REQUEST_SCHEMA,
          agent_name: this.#agentName,
          prompt: bundle.prompt,
          prompt_sha256: bundle.promptHash,
          timeout_seconds: this.#timeoutSeconds,
          request_id: context?.requestId,
          run_id: context?.runId,
          nonce: context?.nonce,
          workspace_id_hash: context?.workspaceIdHash,
        }
        : {
          schema: OPENCLAW_PROVIDER_REQUEST_SCHEMA,
          agent_name: this.#agentName,
          prompt: bundle.prompt,
          prompt_hash: bundle.promptHash,
          timeout_seconds: this.#timeoutSeconds,
        };
      // Once dispatched, a lost or malformed reply cannot prove execution did not occur.
      providerCallPerformed = true;
      const payload = await unixSocketJson({
        socketPath: this.#providerSocketPath,
        path: "/v1/execute",
        timeoutMs: (this.#timeoutSeconds + 30) * 1000,
        signal,
        body,
      });
      const responseKeys = Object.keys(payload).sort();
      if (
        responseKeys.length !== OPENCLAW_PROVIDER_RESPONSE_KEYS.length
        || responseKeys.some(
          (key, index) => key !== OPENCLAW_PROVIDER_RESPONSE_KEYS[index],
        )
        || payload.schema !== OPENCLAW_PROVIDER_RESPONSE_SCHEMA
        || typeof payload.ok !== "boolean"
        || typeof payload.provider_call_performed !== "boolean"
        || payload.dry_run !== false
        || typeof payload.output_present !== "boolean"
        || typeof payload.retryable !== "boolean"
        || payload.raw_prompt_omitted !== true
        || payload.raw_response_omitted !== true
        || typeof payload.model_name !== "string"
        || !PROVIDER_MODEL_NAME.test(payload.model_name)
        || !SHA256_HEX.test(String(payload.raw_payload_hash || ""))
        || typeof payload.duration_ms !== "number"
        || !Number.isSafeInteger(payload.duration_ms)
        || payload.duration_ms < 0
        || payload.duration_ms > 86_400_000
        || typeof payload.output_tokens !== "number"
        || !Number.isSafeInteger(payload.output_tokens)
        || payload.output_tokens < 0
        || payload.output_tokens > 10_000_000
        || (payload.error_type !== null
          && (typeof payload.error_type !== "string"
            || !PROVIDER_ERROR_TYPE.test(payload.error_type)))
        || (payload.error_message !== null
          && typeof payload.error_message !== "string")
        || (payload.ok === true && (
          payload.output_present !== true
          || payload.provider_call_performed !== true
          || payload.retryable !== false
          || payload.error_type !== null
          || payload.error_message !== null
        ))
        || (payload.ok === false && (
          payload.output_present !== false
          || typeof payload.error_type !== "string"
          || payload.error_message !== OPENCLAW_PROVIDER_ERROR_MESSAGE
        ))
      ) {
        throw new Error("openclaw_provider_response_contract_invalid");
      }
      const ok = payload.ok === true && payload.output_present === true;
      providerCallPerformed = payload.provider_call_performed === true;
      const errorType = ok
        ? null
        : payload.error_type === null
          ? "OpenClawProviderFailed"
          : payload.error_type;
      return {
        ok,
        runtime: this.runtime,
        modelName: redactText(payload.model_name, 120),
        outputSummary: ok ? PROVIDER_RESPONSE_OMITTED : PROVIDER_EMPTY_RESPONSE,
        rawPayloadHash: String(payload.raw_payload_hash),
        targetResource,
        durationMs: boundedInteger(
          payload.duration_ms,
          Date.now() - started,
          0,
          86_400_000,
        ),
        outputTokens: boundedInteger(payload.output_tokens, 0, 0, 10_000_000),
        providerCallPerformed,
        dryRun: false,
        retryable: payload.retryable === true,
        errorType,
        errorMessage: ok
          ? null
          : "Provider error detail omitted; OpenClaw provider execution failed.",
      };
    } catch {
      const cancelled = signal?.aborted === true;
      return {
        ok: false,
        runtime: this.runtime,
        modelName: this.modelName,
        outputSummary: "OpenClaw provider execution failed.",
        rawPayloadHash: stableHash({
          runtime: this.runtime,
          transport: "unix_socket",
          error_type: cancelled
            ? "RuntimeCancelled"
            : "OpenClawProviderUnavailable",
        }),
        targetResource,
        durationMs: Date.now() - started,
        outputTokens: 0,
        providerCallPerformed,
        dryRun: false,
        retryable: !cancelled,
        errorType: cancelled
          ? "RuntimeCancelled"
          : "OpenClawProviderUnavailable",
        errorMessage: cancelled
          ? "Runtime execution cancelled for controlled shutdown."
          : "OpenClaw provider transport failed; detail omitted.",
      };
    }
  }
}
