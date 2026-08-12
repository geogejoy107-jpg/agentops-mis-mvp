import {
  runPostgresSchemaCommand,
  SchemaReadinessError,
  type SchemaCommand,
} from "../src/server/controlPlane/schemaReadiness";

function operationFromArguments(): SchemaCommand {
  const argumentsSet = new Set(process.argv.slice(2));
  if (argumentsSet.size === 0) return "migrate";
  if (argumentsSet.size === 1 && argumentsSet.has("--check")) return "check";
  throw new SchemaReadinessError("invalid_arguments");
}

try {
  const receipt = await runPostgresSchemaCommand(operationFromArguments());
  console.log(JSON.stringify(receipt));
} catch (error) {
  const errorCode = error instanceof SchemaReadinessError
    ? error.code
    : "schema_runner_failed";
  console.log(JSON.stringify({
    contract: "agentops_postgres_schema_readiness_v1",
    ok: false,
    error_code: errorCode,
    credentials_omitted: true,
    sql_omitted: true,
    row_data_omitted: true,
  }));
  process.exitCode = 1;
}
