import { createHash } from "node:crypto";

const REDACTION_RULES: ReadonlyArray<[RegExp, string]> = Object.freeze([
  [
    /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/gi,
    "[REDACTED_PRIVATE_KEY]",
  ],
  [
    /\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis):\/\/[^\s"'<>]+/gi,
    "[REDACTED_DSN]",
  ],
  [
    /\bBearer\s+[A-Za-z0-9._~+/=-]{12,}/gi,
    "Bearer [REDACTED_TOKEN]",
  ],
  [
    /\b(?:agtok|agtsess|ghp|github_pat|sk|xox[baprs])_[A-Za-z0-9._-]{12,}\b/gi,
    "[REDACTED_TOKEN]",
  ],
  [
    /\b(?:credential|secret|token|password|api[_-]?key)_canary_[A-Za-z0-9_-]{12,}\b/gi,
    "[REDACTED_CANARY]",
  ],
  [
    /\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization|cookie)\b\s*[:=]\s*["']?[^\s,"';]{8,}/gi,
    "$1=[REDACTED]",
  ],
]);

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonicalize(item)]),
    );
  }
  return value;
}

export function stableJson(value: unknown) {
  return JSON.stringify(canonicalize(value));
}

export function sha256(value: string | Buffer) {
  return createHash("sha256").update(value).digest("hex");
}

export function stableHash(value: unknown) {
  return sha256(typeof value === "string" ? value : stableJson(value));
}

export function redactText(value: unknown, maximum = 360) {
  let text = String(value ?? "")
    .replaceAll("\u0000", "")
    .replace(/[\u0001-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  for (const [pattern, replacement] of REDACTION_RULES) {
    text = text.replace(pattern, replacement);
  }
  return text.slice(0, Math.max(0, maximum));
}

export function containsProtectedMaterial(value: unknown) {
  const text = String(value ?? "");
  return REDACTION_RULES.some(([pattern]) => {
    pattern.lastIndex = 0;
    return pattern.test(text);
  });
}

export function safeIdentifier(value: unknown, label: string) {
  const identifier = String(value ?? "").trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/.test(identifier)) {
    throw new Error(`${label}_invalid`);
  }
  return identifier;
}

export function boundedInteger(
  value: unknown,
  fallback: number,
  minimum: number,
  maximum: number,
) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(minimum, Math.min(Math.trunc(parsed), maximum));
}
