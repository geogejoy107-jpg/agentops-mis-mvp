export type ControlPlaneMode = "proxy" | "postgres";

function normalized(value: string | undefined) {
  return String(value || "").trim().toLowerCase();
}

export function controlPlaneMode(): ControlPlaneMode {
  const configured = normalized(process.env.AGENTOPS_TS_CONTROL_PLANE_MODE);
  if (configured === "proxy" || configured === "postgres") return configured;
  return normalized(process.env.AGENTOPS_DEPLOYMENT_MODE) === "production" ? "postgres" : "proxy";
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
