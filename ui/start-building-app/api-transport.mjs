const FREE_LOCAL_DEPLOYMENT_MODES = new Set([
  "local",
  "free_local",
  "development",
]);
const PRODUCTION_DEPLOYMENT_MODES = new Set([
  "production",
  "prod",
  "shared",
  "hosted",
]);
const CONTROL_PLANE_MODES = new Set(["postgres", "proxy"]);

function normalized(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizedPath(pathname) {
  const value = String(pathname || "").replace(/\/+$/, "");
  return value || "/";
}

function loopbackHost(hostname) {
  const value = String(hostname || "").toLowerCase();
  return [
    "127.0.0.1",
    "::1",
    "[::1]",
    "localhost",
  ].includes(value) || value.endsWith(".localhost");
}

function apiBase(value, production, controlPlaneMode) {
  const configured = String(value || "").trim();
  const fallback = controlPlaneMode === "postgres" ? "/api/mis" : "/mis-api";
  const candidate = configured || fallback;
  let path;
  let result;

  if (candidate.startsWith("/")) {
    if (
      candidate.startsWith("//")
      || candidate.includes("?")
      || candidate.includes("#")
    ) {
      throw new Error("ui_api_base_invalid");
    }
    path = normalizedPath(candidate);
    result = path;
  } else {
    let parsed;
    try {
      parsed = new URL(candidate);
    } catch {
      throw new Error("ui_api_base_invalid");
    }
    if (
      !["http:", "https:"].includes(parsed.protocol)
      || parsed.username
      || parsed.password
      || parsed.search
      || parsed.hash
    ) {
      throw new Error("ui_api_base_invalid");
    }
    if (
      parsed.protocol !== "https:"
      && (production || !loopbackHost(parsed.hostname))
    ) {
      throw new Error(
        production
          ? "commercial_ui_https_api_base_required"
          : "ui_api_base_invalid",
      );
    }
    path = normalizedPath(parsed.pathname);
    parsed.pathname = path;
    result = parsed.toString().replace(/\/$/, "");
  }

  if (production && path === "/mis-api") {
    throw new Error("commercial_ui_python_api_base_forbidden");
  }
  if (controlPlaneMode === "postgres" && path !== "/api/mis") {
    throw new Error("ui_postgres_api_base_required");
  }
  return result;
}

export function resolveAgentOpsApiTransport(environment = {}) {
  const deploymentMode = normalized(
    environment.VITE_AGENTOPS_DEPLOYMENT_MODE,
  ) || "free_local";
  const knownDeployment = FREE_LOCAL_DEPLOYMENT_MODES.has(deploymentMode)
    || PRODUCTION_DEPLOYMENT_MODES.has(deploymentMode);
  if (!knownDeployment) {
    throw new Error("ui_deployment_mode_invalid");
  }
  const production = PRODUCTION_DEPLOYMENT_MODES.has(deploymentMode);
  const configuredControlPlane = normalized(
    environment.VITE_AGENTOPS_CONTROL_PLANE_MODE,
  );
  if (
    configuredControlPlane
    && !CONTROL_PLANE_MODES.has(configuredControlPlane)
  ) {
    throw new Error("ui_control_plane_mode_invalid");
  }
  const controlPlaneMode = configuredControlPlane
    || (production ? "postgres" : "proxy");
  if (production && controlPlaneMode !== "postgres") {
    throw new Error("commercial_ui_python_proxy_forbidden");
  }
  return Object.freeze({
    deploymentMode,
    controlPlaneMode,
    production,
    apiBase: apiBase(
      environment.VITE_AGENTOPS_API_BASE,
      production,
      controlPlaneMode,
    ),
    pythonProxyEnabled: !production && controlPlaneMode === "proxy",
  });
}
