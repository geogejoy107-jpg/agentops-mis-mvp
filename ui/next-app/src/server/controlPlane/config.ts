export type ControlPlaneMode = "proxy" | "postgres";

const FREE_LOCAL_DEPLOYMENT_MODES = new Set(["local", "free_local", "development"]);

function normalized(value: string | undefined) {
  return String(value || "").trim().toLowerCase();
}

export function controlPlaneMode(): ControlPlaneMode {
  const configured = normalized(
    process.env.AGENTOPS_CONTROL_PLANE_MODE || process.env.AGENTOPS_TS_CONTROL_PLANE_MODE,
  );
  if (configured === "postgres") return "postgres";
  if (configured === "proxy") return isProductionDeployment() ? "postgres" : "proxy";
  return isProductionDeployment() ? "postgres" : "proxy";
}

export function isProductionDeployment() {
  const configured = normalized(process.env.AGENTOPS_DEPLOYMENT_MODE);
  if (configured === "production") return true;
  if (FREE_LOCAL_DEPLOYMENT_MODES.has(configured)) return false;
  if (configured) {
    throw new Error(
      "AGENTOPS_DEPLOYMENT_MODE must be production, local, free_local, or development.",
    );
  }
  return normalized(process.env.NODE_ENV) === "production";
}

export function legacyPythonProxyAllowed() {
  return !isProductionDeployment();
}

export function postgresDsn() {
  const dsn = String(process.env.AGENTOPS_POSTGRES_DSN || "").trim();
  if (!dsn) {
    throw new Error("AGENTOPS_POSTGRES_DSN is required when the TypeScript control plane owns Postgres routes.");
  }
  return dsn;
}

export function proxyBaseUrl() {
  return String(process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api").replace(/\/$/, "");
}

export function postgresSslEnabled() {
  return ["1", "true", "require", "required", "on"].includes(normalized(process.env.AGENTOPS_POSTGRES_SSL));
}
