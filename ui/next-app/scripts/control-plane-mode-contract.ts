import process from "node:process";
import { NextRequest } from "next/server";

import { POST as postLegacyApprovalReview } from "../app/workspace/approvals/review/route";
import { POST as postLegacyMemoryReview } from "../app/workspace/memory/review/route";
import {
  controlPlaneMode,
  isProductionDeployment,
  legacyPythonProxyAllowed,
} from "../src/server/controlPlane/config";
import { loadServerTasks } from "../src/lib/misServer";
import { legacyWorkspacePythonProxyGuard } from "../src/server/controlPlane/legacyWorkspacePythonProxyGuard";
import { proxyControlPlaneRequest } from "../src/server/controlPlane/proxy";


const KEYS = [
  "NODE_ENV",
  "AGENTOPS_DEPLOYMENT_MODE",
  "AGENTOPS_CONTROL_PLANE_MODE",
  "AGENTOPS_TS_CONTROL_PLANE_MODE",
  "AGENTOPS_ALLOWED_ORIGINS",
] as const;

const environment = process.env as Record<string, string | undefined>;
const original = Object.fromEntries(KEYS.map((key) => [key, environment[key]]));

function configure(values: Partial<Record<(typeof KEYS)[number], string>>) {
  for (const key of KEYS) delete environment[key];
  for (const [key, value] of Object.entries(values)) environment[key] = value;
}

function require(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

try {
  configure({ NODE_ENV: "production" });
  require(isProductionDeployment(), "standard_next_start_not_detected_as_production");
  require(controlPlaneMode() === "postgres", "standard_next_start_did_not_default_to_postgres");
  require(!legacyPythonProxyAllowed(), "standard_next_start_allowed_python_catch_all");
  const productionGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "http://127.0.0.1:3000/workspace/connectors/trust",
    {
      method: "POST",
      headers: {
        Host: "127.0.0.1:3000",
        Origin: "http://127.0.0.1:3000",
        "Sec-Fetch-Site": "same-origin",
      },
    },
  ));
  require(productionGuard?.status === 503, "production_workspace_write_guard_did_not_fail_closed");
  const centralProxyGuard = await proxyControlPlaneRequest(
    new NextRequest("http://127.0.0.1:3000/api/mis/future-route", { method: "POST", body: "must-not-forward" }),
    "/future-route",
  );
  require(centralProxyGuard.status === 503, "production_proxy_helper_did_not_fail_closed");
  const centralProxyPayload = await centralProxyGuard.json() as { python_proxy_performed?: boolean };
  require(centralProxyPayload.python_proxy_performed === false, "production_proxy_helper_forwarded_python");
  const productionServerLoader = await loadServerTasks();
  require(
    Boolean(productionServerLoader.error?.includes("typescript_route_owner_required")),
    "production_server_loader_called_python_directly",
  );

  configure({ NODE_ENV: "production", AGENTOPS_CONTROL_PLANE_MODE: "proxy" });
  require(controlPlaneMode() === "postgres", "production_proxy_override_did_not_fail_closed");

  configure({ NODE_ENV: "development", AGENTOPS_DEPLOYMENT_MODE: "production", AGENTOPS_TS_CONTROL_PLANE_MODE: "proxy" });
  require(isProductionDeployment(), "explicit_production_mode_not_detected");
  require(controlPlaneMode() === "postgres", "legacy_production_proxy_override_did_not_fail_closed");

  configure({ NODE_ENV: "production", AGENTOPS_DEPLOYMENT_MODE: "local", AGENTOPS_CONTROL_PLANE_MODE: "proxy" });
  require(!isProductionDeployment(), "explicit_local_mode_not_respected");
  require(controlPlaneMode() === "proxy", "explicit_local_proxy_mode_not_respected");
  require(legacyPythonProxyAllowed(), "explicit_local_python_proxy_not_respected");
  const sameOriginGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "http://127.0.0.1:3000/workspace/connectors/trust",
    {
      method: "POST",
      headers: {
        Host: "127.0.0.1:3000",
        Origin: "http://127.0.0.1:3000",
        "Sec-Fetch-Site": "same-origin",
      },
    },
  ));
  require(sameOriginGuard === null, "explicit_local_same_origin_proxy_blocked");
  for (const loopback of [
    { origin: "http://localhost:3001", host: "localhost:3001" },
    { origin: "http://[::1]:3002", host: "[::1]:3002" },
  ]) {
    const literalLoopbackGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
      `${loopback.origin}/workspace/connectors/trust`,
      {
        method: "POST",
        headers: {
          Host: loopback.host,
          Origin: loopback.origin,
          "Sec-Fetch-Site": "same-origin",
        },
      },
    ));
    require(literalLoopbackGuard === null, `literal_loopback_proxy_blocked:${loopback.host}`);
  }
  const dnsRebindingGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "http://rebind.attacker.invalid:3000/workspace/connectors/trust",
    {
      method: "POST",
      headers: {
        Host: "rebind.attacker.invalid:3000",
        Origin: "http://rebind.attacker.invalid:3000",
        "Sec-Fetch-Site": "same-origin",
      },
    },
  ));
  require(dnsRebindingGuard?.status === 403, "matching_malicious_host_origin_allowed_dns_rebinding");
  const dnsRebindingPayload = await dnsRebindingGuard.json() as {
    error?: string;
    python_proxy_performed?: boolean;
  };
  require(dnsRebindingPayload.error === "csrf_validation_failed", "dns_rebinding_error_drift");
  require(dnsRebindingPayload.python_proxy_performed === false, "dns_rebinding_proxy_performed");
  const loopbackSuffixGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "http://localhost.attacker.invalid:3000/workspace/connectors/trust",
    {
      method: "POST",
      headers: {
        Host: "localhost.attacker.invalid:3000",
        Origin: "http://localhost.attacker.invalid:3000",
        "Sec-Fetch-Site": "same-origin",
      },
    },
  ));
  require(loopbackSuffixGuard?.status === 403, "loopback_hostname_suffix_allowed_dns_rebinding");

  configure({
    NODE_ENV: "production",
    AGENTOPS_DEPLOYMENT_MODE: "local",
    AGENTOPS_CONTROL_PLANE_MODE: "proxy",
    AGENTOPS_ALLOWED_ORIGINS: "https://console.example.test:8443",
  });
  const configuredOriginGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "https://console.example.test:8443/workspace/connectors/trust",
    {
      method: "POST",
      headers: {
        Host: "console.example.test:8443",
        Origin: "https://console.example.test:8443",
        "Sec-Fetch-Site": "same-origin",
      },
    },
  ));
  require(configuredOriginGuard === null, "configured_exact_origin_proxy_blocked");
  const configuredPortMismatchGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "https://console.example.test:8443/workspace/connectors/trust",
    {
      method: "POST",
      headers: {
        Host: "console.example.test",
        Origin: "https://console.example.test:8443",
        "Sec-Fetch-Site": "same-origin",
      },
    },
  ));
  require(configuredPortMismatchGuard?.status === 403, "configured_origin_host_port_mismatch_allowed");
  const unconfiguredMatchingGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "https://rebind.attacker.invalid/workspace/connectors/trust",
    {
      method: "POST",
      headers: {
        Host: "rebind.attacker.invalid",
        Origin: "https://rebind.attacker.invalid",
        "Sec-Fetch-Site": "same-origin",
      },
    },
  ));
  require(unconfiguredMatchingGuard?.status === 403, "unconfigured_matching_host_origin_allowed");

  configure({
    NODE_ENV: "production",
    AGENTOPS_DEPLOYMENT_MODE: "local",
    AGENTOPS_CONTROL_PLANE_MODE: "proxy",
    AGENTOPS_ALLOWED_ORIGINS: "https://console.example.test/path",
  });
  const invalidConfigGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "https://console.example.test/workspace/connectors/trust",
    {
      method: "POST",
      headers: {
        Host: "console.example.test",
        Origin: "https://console.example.test",
        "Sec-Fetch-Site": "same-origin",
      },
    },
  ));
  require(invalidConfigGuard?.status === 403, "invalid_origin_configuration_failed_open");

  configure({ NODE_ENV: "production", AGENTOPS_DEPLOYMENT_MODE: "local", AGENTOPS_CONTROL_PLANE_MODE: "proxy" });
  const crossOriginGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "http://127.0.0.1:3000/workspace/connectors/trust",
    { method: "POST", headers: { Origin: "https://attacker.invalid", "Sec-Fetch-Site": "cross-site" } },
  ));
  require(crossOriginGuard?.status === 403, "explicit_local_cross_origin_proxy_allowed");
  const crossOriginPayload = await crossOriginGuard.json() as { error?: string; python_proxy_performed?: boolean };
  require(crossOriginPayload.error === "csrf_validation_failed", "explicit_local_cross_origin_error_drift");
  require(crossOriginPayload.python_proxy_performed === false, "explicit_local_cross_origin_proxy_performed");
  const crossSiteMetadataGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "http://127.0.0.1:3000/workspace/connectors/trust",
    {
      method: "POST",
      headers: {
        Host: "127.0.0.1:3000",
        Origin: "http://127.0.0.1:3000",
        "Sec-Fetch-Site": "cross-site",
      },
    },
  ));
  require(crossSiteMetadataGuard?.status === 403, "explicit_local_cross_site_metadata_proxy_allowed");
  const crossSiteMetadataPayload = await crossSiteMetadataGuard.json() as {
    error?: string;
    python_proxy_performed?: boolean;
  };
  require(crossSiteMetadataPayload.error === "csrf_validation_failed", "explicit_local_cross_site_metadata_error_drift");
  require(crossSiteMetadataPayload.python_proxy_performed === false, "explicit_local_cross_site_metadata_proxy_performed");
  const missingOriginGuard = legacyWorkspacePythonProxyGuard(new NextRequest(
    "http://127.0.0.1:3000/workspace/connectors/trust",
    { method: "POST" },
  ));
  require(missingOriginGuard?.status === 403, "explicit_local_missing_origin_proxy_allowed");
  const missingOriginPayload = await missingOriginGuard.json() as { error?: string; python_proxy_performed?: boolean };
  require(missingOriginPayload.error === "csrf_validation_failed", "explicit_local_missing_origin_error_drift");
  require(missingOriginPayload.python_proxy_performed === false, "explicit_local_missing_origin_proxy_performed");
  const originalFetch = globalThis.fetch;
  let legacyDecisionFetches = 0;
  globalThis.fetch = (async () => {
    legacyDecisionFetches += 1;
    return Response.json({ ok: true });
  }) as typeof fetch;
  try {
    const invalidDecisionHeaders = {
      "Content-Type": "application/x-www-form-urlencoded",
      Host: "127.0.0.1:3000",
      Origin: "http://127.0.0.1:3000",
      "Sec-Fetch-Site": "same-origin",
    };
    const invalidApprovalDecision = await postLegacyApprovalReview(new NextRequest(
      "http://127.0.0.1:3000/workspace/approvals/review",
      { method: "POST", headers: invalidDecisionHeaders, body: "approval_id=ap_contract&decision=unknown" },
    ));
    require(invalidApprovalDecision.status === 400, "legacy_approval_unknown_decision_allowed");
    const invalidApprovalPayload = await invalidApprovalDecision.json() as { error?: string };
    require(invalidApprovalPayload.error === "decision_invalid", "legacy_approval_unknown_decision_error_drift");
    const invalidMemoryDecision = await postLegacyMemoryReview(new NextRequest(
      "http://127.0.0.1:3000/workspace/memory/review",
      { method: "POST", headers: invalidDecisionHeaders, body: "memory_id=mem_contract&decision=unknown" },
    ));
    require(invalidMemoryDecision.status === 400, "legacy_memory_unknown_decision_allowed");
    const invalidMemoryPayload = await invalidMemoryDecision.json() as { error?: string };
    require(invalidMemoryPayload.error === "decision_invalid", "legacy_memory_unknown_decision_error_drift");
    require(legacyDecisionFetches === 0, "legacy_unknown_decision_reached_python_upstream");
  } finally {
    globalThis.fetch = originalFetch;
  }

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
    production_proxy_helper_blocked: true,
    production_server_loader_python_blocked: true,
    unknown_deployment_mode_rejected: true,
    explicit_local_proxy_preserved: true,
    explicit_local_dns_rebinding_blocked: true,
    configured_exact_origin_preserved: true,
    configured_origin_host_port_mismatch_blocked: true,
    invalid_origin_configuration_blocked: true,
    explicit_local_cross_origin_workspace_write_blocked: true,
    explicit_local_cross_site_metadata_workspace_write_blocked: true,
    explicit_local_missing_origin_workspace_write_blocked: true,
    explicit_local_unknown_review_decisions_blocked_before_proxy: true,
  })}\n`);
} finally {
  for (const key of KEYS) {
    const value = original[key];
    if (value === undefined) delete environment[key];
    else environment[key] = value;
  }
}
