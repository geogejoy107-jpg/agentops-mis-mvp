import process from "node:process";

import {
  controlPlaneMode,
  isProductionDeployment,
  legacyPythonProxyAllowed,
} from "../src/server/controlPlane/config";


const KEYS = [
  "NODE_ENV",
  "AGENTOPS_DEPLOYMENT_MODE",
  "AGENTOPS_CONTROL_PLANE_MODE",
  "AGENTOPS_TS_CONTROL_PLANE_MODE",
] as const;

const environment = process.env as Record<string, string | undefined>;
const original = Object.fromEntries(KEYS.map((key) => [key, environment[key]]));

function configure(values: Partial<Record<(typeof KEYS)[number], string>>) {
  for (const key of KEYS) delete environment[key];
  for (const [key, value] of Object.entries(values)) environment[key] = value;
}

function require(condition: boolean, message: string) {
  if (!condition) throw new Error(message);
}

try {
  configure({ NODE_ENV: "production" });
  require(isProductionDeployment(), "standard_next_start_not_detected_as_production");
  require(controlPlaneMode() === "postgres", "standard_next_start_did_not_default_to_postgres");
  require(!legacyPythonProxyAllowed(), "standard_next_start_allowed_python_catch_all");

  configure({ NODE_ENV: "production", AGENTOPS_CONTROL_PLANE_MODE: "proxy" });
  require(controlPlaneMode() === "postgres", "production_proxy_override_did_not_fail_closed");

  configure({ NODE_ENV: "development", AGENTOPS_DEPLOYMENT_MODE: "production", AGENTOPS_TS_CONTROL_PLANE_MODE: "proxy" });
  require(isProductionDeployment(), "explicit_production_mode_not_detected");
  require(controlPlaneMode() === "postgres", "legacy_production_proxy_override_did_not_fail_closed");

  configure({ NODE_ENV: "production", AGENTOPS_DEPLOYMENT_MODE: "local", AGENTOPS_CONTROL_PLANE_MODE: "proxy" });
  require(!isProductionDeployment(), "explicit_local_mode_not_respected");
  require(controlPlaneMode() === "proxy", "explicit_local_proxy_mode_not_respected");
  require(legacyPythonProxyAllowed(), "explicit_local_python_proxy_not_respected");

  configure({ NODE_ENV: "production", AGENTOPS_DEPLOYMENT_MODE: "prodution" });
  let invalidModeRejected = false;
  try {
    controlPlaneMode();
  } catch {
    invalidModeRejected = true;
  }
  require(invalidModeRejected, "unknown_deployment_mode_failed_open");

  configure({ NODE_ENV: "development" });
  require(controlPlaneMode() === "proxy", "development_did_not_default_to_proxy");

  process.stdout.write(`${JSON.stringify({
    ok: true,
    contract: "control_plane_production_fail_closed_v1",
    standard_next_start_defaults_postgres: true,
    production_proxy_override_blocked: true,
    production_python_catch_all_blocked: true,
    unknown_deployment_mode_rejected: true,
    explicit_local_proxy_preserved: true,
  })}\n`);
} finally {
  for (const key of KEYS) {
    const value = original[key];
    if (value === undefined) delete environment[key];
    else environment[key] = value;
  }
}
