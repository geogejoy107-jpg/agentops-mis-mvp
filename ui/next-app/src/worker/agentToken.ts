import {
  closeSync,
  constants,
  fstatSync,
  lstatSync,
  openSync,
  readFileSync,
} from "node:fs";
import { isAbsolute } from "node:path";

const MAX_TOKEN_BYTES = 16 * 1024;

function readStableSecret(sourcePath: string) {
  if (!isAbsolute(sourcePath)) {
    throw new Error("agent_token_source_absolute_required");
  }
  const before = lstatSync(sourcePath);
  if (!before.isFile() || before.isSymbolicLink()) {
    throw new Error("agent_token_source_not_regular");
  }
  if (before.size < 16 || before.size > MAX_TOKEN_BYTES) {
    throw new Error("agent_token_source_size_invalid");
  }
  if (typeof constants.O_NOFOLLOW !== "number") {
    throw new Error("nofollow_unavailable");
  }
  const descriptor = openSync(sourcePath, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const opened = fstatSync(descriptor);
    if (
      !opened.isFile()
      || opened.dev !== before.dev
      || opened.ino !== before.ino
      || opened.size !== before.size
    ) {
      throw new Error("agent_token_source_identity_changed");
    }
    const bytes = readFileSync(descriptor);
    const after = fstatSync(descriptor);
    if (
      after.dev !== opened.dev
      || after.ino !== opened.ino
      || after.size !== opened.size
      || after.mtimeMs !== opened.mtimeMs
      || after.ctimeMs !== opened.ctimeMs
    ) {
      bytes.fill(0);
      throw new Error("agent_token_source_changed_during_read");
    }
    return bytes;
  } finally {
    closeSync(descriptor);
  }
}

export function readCommercialAgentToken() {
  const sourcePath = String(process.env.AGENTOPS_AGENT_TOKEN_SOURCE_FILE || "").trim();
  const environmentToken = String(
    process.env.AGENTOPS_API_KEY || process.env.AGENTOPS_AGENT_TOKEN || "",
  );
  if (sourcePath && environmentToken) {
    throw new Error("agent_token_source_conflict");
  }
  if (!sourcePath) {
    if (process.env.NODE_ENV === "production") {
      throw new Error("commercial_worker_file_agent_token_required");
    }
    return environmentToken;
  }
  const bytes = readStableSecret(sourcePath);
  try {
    if (bytes.includes(0)) throw new Error("agent_token_nul_forbidden");
    const token = bytes.toString("utf8").replace(/[\r\n]+$/, "");
    if (
      Buffer.byteLength(token, "utf8") < 16
      || Buffer.byteLength(token, "utf8") > MAX_TOKEN_BYTES
      || /[\r\n\u0000-\u001f\u007f]/.test(token)
    ) {
      throw new Error("agent_token_invalid");
    }
    return token;
  } finally {
    bytes.fill(0);
  }
}
