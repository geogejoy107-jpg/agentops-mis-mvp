import assert from "node:assert/strict";

import {
  controlPlaneMode,
  isProductionDeployment,
  legacyPythonProxyAllowed,
  postgresDsn,
} from "../src/server/controlPlane/config";

const ENV_KEYS = [
  "AGENTOPS_CONTROL_PLANE_MODE",
  "AGENTOPS_TS_CONTROL_PLANE_MODE",
  "AGENTOPS_DEPLOYMENT_MODE",
  "AGENTOPS_POSTGRES_DSN",
  "NODE_ENV",
] as const;

const mutableEnvironment = process.env as Record<string, string | undefined>;
const originalEnvironment = Object.fromEntries(
  ENV_KEYS.map((key) => [key, mutableEnvironment[key]]),
) as Record<(typeof ENV_KEYS)[number], string | undefined>;

function clearContractEnvironment() {
  for (const key of ENV_KEYS) delete mutableEnvironment[key];
}

try {
  clearContractEnvironment();
  mutableEnvironment.AGENTOPS_DEPLOYMENT_MODE = "production";
  mutableEnvironment.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
  assert.equal(isProductionDeployment(), true);
  assert.equal(controlPlaneMode(), "postgres");
  assert.equal(legacyPythonProxyAllowed(), false);

  clearContractEnvironment();
  mutableEnvironment.AGENTOPS_DEPLOYMENT_MODE = "free_local";
  mutableEnvironment.AGENTOPS_CONTROL_PLANE_MODE = "proxy";
  assert.equal(isProductionDeployment(), false);
  assert.equal(controlPlaneMode(), "proxy");
  assert.equal(legacyPythonProxyAllowed(), true);

  clearContractEnvironment();
  mutableEnvironment.AGENTOPS_DEPLOYMENT_MODE = "local";
  mutableEnvironment.AGENTOPS_CONTROL_PLANE_MODE = "postgres";
  assert.equal(isProductionDeployment(), false);
  assert.equal(controlPlaneMode(), "postgres");
  assert.equal(legacyPythonProxyAllowed(), false);

  clearContractEnvironment();
  mutableEnvironment.NODE_ENV = "production";
  assert.equal(isProductionDeployment(), true);
  assert.equal(controlPlaneMode(), "postgres");
  assert.equal(legacyPythonProxyAllowed(), false);

  clearContractEnvironment();
  mutableEnvironment.AGENTOPS_DEPLOYMENT_MODE = "production";
  assert.throws(() => postgresDsn(), /AGENTOPS_POSTGRES_DSN is required/);
  mutableEnvironment.AGENTOPS_POSTGRES_DSN = "postgresql://control-plane.invalid/agentops";
  assert.equal(postgresDsn(), "postgresql://control-plane.invalid/agentops");

  clearContractEnvironment();
  mutableEnvironment.AGENTOPS_DEPLOYMENT_MODE = "unexpected";
  assert.throws(() => isProductionDeployment(), /AGENTOPS_DEPLOYMENT_MODE must be/);

  for (const alias of ["prod", "shared", "hosted"]) {
    clearContractEnvironment();
    mutableEnvironment.AGENTOPS_DEPLOYMENT_MODE = alias;
    assert.equal(isProductionDeployment(), true);
    assert.equal(controlPlaneMode(), "postgres");
    assert.equal(legacyPythonProxyAllowed(), false);
  }

  clearContractEnvironment();
  mutableEnvironment.AGENTOPS_DEPLOYMENT_MODE = "local";
  mutableEnvironment.AGENTOPS_CONTROL_PLANE_MODE = "unexpected";
  assert.throws(() => controlPlaneMode(), /AGENTOPS_CONTROL_PLANE_MODE must be/);

  console.log(JSON.stringify({
    contract: "nextjs_control_plane_mode_v2",
    ok: true,
    production_aliases_fail_closed: true,
    production_proxy_coerced_to_postgres: true,
    production_python_proxy_allowed: false,
    free_local_python_proxy_allowed: true,
    local_postgres_python_proxy_allowed: false,
    unknown_modes_rejected: true,
    postgres_dsn_required: true,
    token_omitted: true,
  }));
} finally {
  clearContractEnvironment();
  for (const key of ENV_KEYS) {
    const value = originalEnvironment[key];
    if (value !== undefined) mutableEnvironment[key] = value;
  }
}
