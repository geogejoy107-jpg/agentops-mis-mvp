#!/usr/bin/env node

import assert from "node:assert/strict";
import {
  OPENCLAW_EGRESS_GATEWAY_BASE_URL,
  validateOpenClawEgressConfiguration,
} from "./openclaw-egress-config.mjs";

function bytes(value) {
  return Buffer.from(JSON.stringify(value), "utf8");
}

function fixture(overrides = {}) {
  return {
    agents: { defaults: { model: { primary: "primary/model" } } },
    models: {
      mode: "replace",
      providers: {
        primary: {
          api: "openai-completions",
          apiKey: "contract-secret-primary",
          baseUrl: OPENCLAW_EGRESS_GATEWAY_BASE_URL,
          models: [{ id: "model" }],
        },
        secondary: {
          api: "anthropic-messages",
          apiKey: "contract-secret-secondary",
          baseUrl: OPENCLAW_EGRESS_GATEWAY_BASE_URL,
          models: [{ id: "model-two" }],
        },
      },
    },
    ...overrides,
  };
}

const accepted = validateOpenClawEgressConfiguration(bytes(fixture()));
assert.deepEqual(accepted, {
  contract: "agentops_openclaw_egress_config_v1",
  credentials_omitted: true,
  gateway_base_url_verified: true,
  provider_catalog_replace_mode_verified: true,
  provider_count: 2,
});
assert.doesNotMatch(JSON.stringify(accepted), /contract-secret|apiKey/u);

for (const [candidate, code] of [
  [Buffer.alloc(0), "openclaw_egress_config_size_invalid"],
  [Buffer.from([0xff, 0xfe]), "openclaw_egress_config_json_invalid"],
  [bytes([]), "openclaw_egress_config_root_invalid"],
  [bytes({}), "openclaw_egress_config_models_invalid"],
  [bytes({ models: {} }), "openclaw_egress_config_replace_mode_required"],
  [bytes({ models: { mode: "merge", providers: {} } }), "openclaw_egress_config_replace_mode_required"],
  [bytes({ models: { mode: "replace" } }), "openclaw_egress_config_providers_invalid"],
  [bytes({ models: { mode: "replace", providers: {} } }), "openclaw_egress_config_provider_count_invalid"],
  [bytes({ models: { mode: "replace", providers: { "bad/name": {} } } }), "openclaw_egress_config_provider_name_invalid"],
  [bytes({ models: { mode: "replace", providers: { valid: [] } } }), "openclaw_egress_config_provider_invalid"],
  [bytes({ models: { mode: "replace", providers: { valid: {} } } }), "openclaw_egress_config_gateway_base_url_required"],
  [bytes({ models: { mode: "replace", providers: { valid: { baseUrl: "https://api.provider.example/v1" } } } }), "openclaw_egress_config_gateway_base_url_required"],
  [bytes({ models: { mode: "replace", providers: { valid: { baseUrl: `${OPENCLAW_EGRESS_GATEWAY_BASE_URL}/extra` } } } }), "openclaw_egress_config_gateway_base_url_required"],
  [bytes({ models: { mode: "replace", providers: { valid: { api: "custom-provider", baseUrl: OPENCLAW_EGRESS_GATEWAY_BASE_URL } } } }), "openclaw_egress_config_provider_api_unsupported"],
]) {
  assert.throws(
    () => validateOpenClawEgressConfiguration(candidate),
    (error) => error?.code === code && error.message === code,
  );
}

const tooMany = Object.fromEntries(Array.from({ length: 33 }, (_, index) => [
  `provider-${index}`,
  { baseUrl: OPENCLAW_EGRESS_GATEWAY_BASE_URL },
]));
for (const provider of Object.values(tooMany)) {
  provider.api = "openai-completions";
}
assert.throws(
  () => validateOpenClawEgressConfiguration(bytes({ models: { mode: "replace", providers: tooMany } })),
  /openclaw_egress_config_provider_count_invalid/u,
);

process.stdout.write(`${JSON.stringify({
  contract: "agentops_openclaw_egress_config_contract_v1",
  credentials_omitted: true,
  direct_provider_origin_rejected: true,
  exact_internal_gateway_base_url_required: true,
  malformed_and_oversized_config_rejected: true,
  ok: true,
  production_dependency_language: "javascript",
  provider_catalog_replace_mode_required: true,
  provider_count_bounded: true,
  supported_provider_api_allowlist_verified: true,
})}\n`);
