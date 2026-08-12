import { ControlPlaneHttpError } from "./http";

type BoundedJsonOptions = {
  maxBytes: number;
  allowEmpty?: boolean;
  label: string;
};

export async function readBoundedBody(
  request: Request,
  options: BoundedJsonOptions,
) {
  const declaredLength = request.headers.get("content-length");
  if (
    declaredLength
    && (!/^\d+$/.test(declaredLength) || Number(declaredLength) > options.maxBytes)
  ) {
    throw new ControlPlaneHttpError(
      413,
      "request_too_large",
      `${options.label} body exceeds ${options.maxBytes} bytes.`,
    );
  }

  const chunks: Buffer[] = [];
  let receivedBytes = 0;
  const reader = request.body?.getReader();
  if (reader) {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      receivedBytes += value.byteLength;
      if (receivedBytes > options.maxBytes) {
        await reader.cancel().catch(() => undefined);
        throw new ControlPlaneHttpError(
          413,
          "request_too_large",
          `${options.label} body exceeds ${options.maxBytes} bytes.`,
        );
      }
      chunks.push(Buffer.from(value));
    }
  }
  return Buffer.concat(chunks, receivedBytes);
}

export function parseBoundedJsonObject(
  rawBody: Buffer,
  options: BoundedJsonOptions,
) {
  const raw = rawBody.toString("utf8");
  if (!raw.trim()) {
    if (options.allowEmpty) return {} as Record<string, unknown>;
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  return parsed as Record<string, unknown>;
}

export async function boundedJsonObject(
  request: Request,
  options: BoundedJsonOptions,
) {
  return parseBoundedJsonObject(await readBoundedBody(request, options), options);
}
