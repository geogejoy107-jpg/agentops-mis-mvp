#!/usr/bin/env node

const MAXIMUM_CONFIG_BYTES = 1024 * 1024;
const PROVIDER_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/u;
const SUPPORTED_PROVIDER_APIS = new Set([
  "anthropic-messages",
  "openai-completions",
  "openai-responses",
]);

export const OPENCLAW_EGRESS_GATEWAY_BASE_URL = "http://openclaw-egress-gateway:18080/v1";

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function record(value, code) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(code);
  return value;
}

function decodeConfig(value) {
  const bytes = Buffer.isBuffer(value) ? value : Buffer.from(value || []);
  if (bytes.byteLength < 2 || bytes.byteLength > MAXIMUM_CONFIG_BYTES) {
    fail("openclaw_egress_config_size_invalid");
  }
  try {
    return JSON.parse(new TextDecoder("utf8", { fatal: true }).decode(bytes));
  } catch {
    fail("openclaw_egress_config_json_invalid");
  }
}

export function validateOpenClawEgressConfiguration(value) {
  const config = record(decodeConfig(value), "openclaw_egress_config_root_invalid");
  const models = record(config.models, "openclaw_egress_config_models_invalid");
  if (models.mode !== "replace") fail("openclaw_egress_config_replace_mode_required");
  const providers = record(models.providers, "openclaw_egress_config_providers_invalid");
  const entries = Object.entries(providers);
  if (entries.length < 1 || entries.length > 32) {
    fail("openclaw_egress_config_provider_count_invalid");
  }
  for (const [name, providerValue] of entries) {
    if (!PROVIDER_NAME.test(name)) fail("openclaw_egress_config_provider_name_invalid");
    const provider = record(providerValue, "openclaw_egress_config_provider_invalid");
    if (provider.baseUrl !== OPENCLAW_EGRESS_GATEWAY_BASE_URL) {
      fail("openclaw_egress_config_gateway_base_url_required");
    }
    if (!SUPPORTED_PROVIDER_APIS.has(provider.api)) {
      fail("openclaw_egress_config_provider_api_unsupported");
    }
  }
  return Object.freeze({
    contract: "agentops_openclaw_egress_config_v1",
    credentials_omitted: true,
    gateway_base_url_verified: true,
    provider_catalog_replace_mode_verified: true,
    provider_count: entries.length,
  });
}
