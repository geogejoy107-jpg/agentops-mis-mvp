import assert from "node:assert/strict";

import { resolveAgentOpsApiTransport } from "../api-transport.mjs";

function fails(environment, code) {
  assert.throws(
    () => resolveAgentOpsApiTransport(environment),
    (error) => error instanceof Error && error.message === code,
  );
}

const freeLocal = resolveAgentOpsApiTransport({});
assert.deepEqual(freeLocal, {
  deploymentMode: "free_local",
  controlPlaneMode: "proxy",
  production: false,
  apiBase: "/mis-api",
  pythonProxyEnabled: true,
});

const localPostgres = resolveAgentOpsApiTransport({
  VITE_AGENTOPS_DEPLOYMENT_MODE: "local",
  VITE_AGENTOPS_CONTROL_PLANE_MODE: "postgres",
});
assert.equal(localPostgres.apiBase, "/api/mis");
assert.equal(localPostgres.pythonProxyEnabled, false);

for (const deploymentMode of ["production", "prod", "shared", "hosted"]) {
  const commercial = resolveAgentOpsApiTransport({
    VITE_AGENTOPS_DEPLOYMENT_MODE: deploymentMode,
  });
  assert.equal(commercial.controlPlaneMode, "postgres");
  assert.equal(commercial.apiBase, "/api/mis");
  assert.equal(commercial.pythonProxyEnabled, false);
}

const remoteCommercial = resolveAgentOpsApiTransport({
  VITE_AGENTOPS_DEPLOYMENT_MODE: "production",
  VITE_AGENTOPS_CONTROL_PLANE_MODE: "postgres",
  VITE_AGENTOPS_API_BASE: "https://mis.example.test/api/mis/",
});
assert.equal(
  remoteCommercial.apiBase,
  "https://mis.example.test/api/mis",
);

fails({
  VITE_AGENTOPS_DEPLOYMENT_MODE: "production",
  VITE_AGENTOPS_CONTROL_PLANE_MODE: "proxy",
}, "commercial_ui_python_proxy_forbidden");
fails({
  VITE_AGENTOPS_DEPLOYMENT_MODE: "production",
  VITE_AGENTOPS_API_BASE: "/mis-api",
}, "commercial_ui_python_api_base_forbidden");
fails({
  VITE_AGENTOPS_DEPLOYMENT_MODE: "production",
  VITE_AGENTOPS_API_BASE: "http://127.0.0.1:3001/api/mis",
}, "commercial_ui_https_api_base_required");
fails({
  VITE_AGENTOPS_DEPLOYMENT_MODE: "production",
  VITE_AGENTOPS_API_BASE: "https://example-user:example-pass@mis.example.test/api/mis",
}, "ui_api_base_invalid");
fails({
  VITE_AGENTOPS_DEPLOYMENT_MODE: "production",
  VITE_AGENTOPS_API_BASE: "https://mis.example.test/api/mis?mode=forbidden",
}, "ui_api_base_invalid");
fails({
  VITE_AGENTOPS_DEPLOYMENT_MODE: "production",
  VITE_AGENTOPS_API_BASE: "https://mis.example.test/api",
}, "ui_postgres_api_base_required");
fails({
  VITE_AGENTOPS_DEPLOYMENT_MODE: "unknown",
}, "ui_deployment_mode_invalid");
fails({
  VITE_AGENTOPS_CONTROL_PLANE_MODE: "unknown",
}, "ui_control_plane_mode_invalid");

process.stdout.write(`${JSON.stringify({
  ok: true,
  contract: "commercial_ui_api_transport_v1",
  free_local_python_proxy_default: true,
  local_postgres_supported: true,
  commercial_next_postgres_default: true,
  commercial_python_proxy_rejected: true,
  commercial_https_remote_only: true,
  credential_url_rejected: true,
  query_parameters_rejected: true,
  token_omitted: true,
})}\n`);
