import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const FREE_LOCAL_DEPLOYMENT_MODES = new Set(["local", "free_local", "development"]);
const PRODUCTION_DEPLOYMENT_MODES = new Set(["production", "prod", "shared", "hosted"]);
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "::1", "localhost"]);

function normalized(value) {
  return String(value || "").trim().toLowerCase();
}

function productionDeployment() {
  const configured = normalized(process.env.AGENTOPS_DEPLOYMENT_MODE);
  if (PRODUCTION_DEPLOYMENT_MODES.has(configured)) return true;
  if (FREE_LOCAL_DEPLOYMENT_MODES.has(configured)) return false;
  if (configured) {
    throw new Error(
      "AGENTOPS_DEPLOYMENT_MODE must be production, prod, shared, hosted, local, free_local, or development.",
    );
  }
  return normalized(process.env.NODE_ENV) === "production";
}

function startConfiguration() {
  const production = productionDeployment();
  const configuredHost = String(process.env.AGENTOPS_NEXT_HOST || "").trim();
  if (production && !configuredHost) {
    throw new Error("AGENTOPS_NEXT_HOST must be explicit for a production Next control plane.");
  }
  const host = configuredHost || "127.0.0.1";
  if (!production && !LOOPBACK_HOSTS.has(normalized(host))) {
    throw new Error("Free Local Next may only bind to 127.0.0.1, ::1, or localhost.");
  }

  const portText = String(process.env.AGENTOPS_NEXT_PORT || process.env.PORT || "3001").trim();
  const port = Number(portText);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("AGENTOPS_NEXT_PORT or PORT must be an integer from 1 through 65535.");
  }
  return { host, port, production };
}

let configuration;
try {
  configuration = startConfiguration();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}

if (process.argv.includes("--check")) {
  console.log(JSON.stringify({
    contract: "nextjs_start_boundary_v1",
    ok: true,
    deployment: configuration.production ? "production" : "free_local",
    host: configuration.host,
    port: configuration.port,
    free_local_loopback_only: !configuration.production,
  }));
  process.exit(0);
}

const nextCli = fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url));
const child = spawn(
  process.execPath,
  [nextCli, "start", "-H", configuration.host, "-p", String(configuration.port)],
  { env: process.env, stdio: "inherit" },
);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    if (!child.killed) child.kill(signal);
  });
}

child.on("error", (error) => {
  console.error(error);
  process.exitCode = 1;
});
child.on("exit", (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});
