import { Pool, type PoolClient } from "pg";

import { postgresDsn, postgresSslEnabled } from "./config";
import { ControlPlaneHttpError } from "./http";

declare global {
  var __agentOpsControlPlanePool: Pool | undefined;
}

function pool() {
  if (!globalThis.__agentOpsControlPlanePool) {
    const configuredPoolMax = Number(process.env.AGENTOPS_POSTGRES_POOL_MAX || 10);
    const poolMax = Number.isFinite(configuredPoolMax)
      ? Math.max(1, Math.min(Math.trunc(configuredPoolMax), 30))
      : 10;
    globalThis.__agentOpsControlPlanePool = new Pool({
      connectionString: postgresDsn(),
      max: poolMax,
      ssl: postgresSslEnabled() ? { rejectUnauthorized: true } : undefined,
      application_name: "agentops-mis-typescript-control-plane",
    });
  }
  return globalThis.__agentOpsControlPlanePool;
}

export async function withPostgresTransaction<T>(work: (client: PoolClient) => Promise<T>): Promise<T> {
  const client = await pool().connect();
  try {
    await client.query("BEGIN");
    const result = await work(client);
    await client.query("COMMIT");
    return result;
  } catch (error) {
    if (error instanceof ControlPlaneHttpError && error.commitTransaction) {
      await client.query("COMMIT");
    } else {
      await client.query("ROLLBACK");
    }
    throw error;
  } finally {
    client.release();
  }
}
