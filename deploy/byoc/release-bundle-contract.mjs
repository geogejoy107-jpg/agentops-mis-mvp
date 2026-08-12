#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import {
  appendFileSync,
  chmodSync,
  copyFileSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const moduleDirectory = dirname(fileURLToPath(import.meta.url));
const sourceRepository = resolve(moduleDirectory, "../..");
const image = `ghcr.io/example/agentops-mis-byoc@sha256:${"a".repeat(64)}`;
const releaseInputRoots = [
  ".dockerignore",
  "deploy/byoc",
  "migrations/postgres",
  "ui/next-app",
];

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function run(command, arguments_, cwd, acceptedStatuses = [0]) {
  const result = spawnSync(command, arguments_, {
    cwd,
    encoding: "utf8",
  });
  if (!acceptedStatuses.includes(result.status ?? -1)) {
    fail(`${command}_failed:${result.stderr.trim()}`);
  }
  return result;
}

function runWithEnvironment(
  command,
  arguments_,
  cwd,
  environment,
  acceptedStatuses = [0],
) {
  const result = spawnSync(command, arguments_, {
    cwd,
    encoding: "utf8",
    env: environment,
  });
  if (!acceptedStatuses.includes(result.status ?? -1)) {
    fail(`${command}_failed:${result.stderr.trim()}`);
  }
  return result;
}

const releaseInputs = run(
  "git",
  ["ls-files", "-z", "--", ...releaseInputRoots],
  sourceRepository,
).stdout.split("\0").filter(Boolean).sort();

function files(root, directory = root) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory()
      ? files(root, path)
      : [relative(root, path).replaceAll("\\", "/")];
  }).sort();
}

function copyInputs(repository) {
  for (const path of releaseInputs) {
    const target = join(repository, path);
    mkdirSync(dirname(target), { recursive: true });
    copyFileSync(join(sourceRepository, path), target);
  }
  for (const executable of [
    "deploy/byoc/build-release-bundle.mjs",
    "deploy/byoc/owner-bootstrap-contract.mjs",
    "deploy/byoc/release-bundle-contract.mjs",
    "deploy/byoc/install.sh",
    "deploy/byoc/owner-init.sh",
    "deploy/byoc/backup.sh",
    "deploy/byoc/restore-drill.sh",
    "deploy/byoc/postgres-destructive-database.sh",
    "deploy/byoc/postgres-restore-guardian.sh",
    "deploy/byoc/retained-data-lifecycle.mjs",
  ]) {
    chmodSync(join(repository, executable), 0o755);
  }
}

function assertStaticCustomerBoundary() {
  const compose = readFileSync(join(moduleDirectory, "compose.release.yaml"), "utf8");
  if (/^\s+build:/m.test(compose) || /context:|dockerfile:|\.\.\/\.\./i.test(compose)) {
    fail("release_compose_build_boundary_invalid");
  }
  if ((compose.match(/image: "?\$\{AGENTOPS_IMAGE:\?[^}]+\}"?/g) || []).length !== 6) {
    fail("release_compose_image_binding_invalid");
  }
  const ownerService = compose.match(
    /  owner-bootstrap:\n([\s\S]*?)(?=\n  [a-z][a-z0-9-]+:|\nvolumes:)/,
  )?.[1] || "";
  const ownerOperator = readFileSync(join(moduleDirectory, "owner-init.sh"), "utf8");
  const ownerEntrypoint = readFileSync(
    join(moduleDirectory, "owner-bootstrap-entrypoint.mjs"),
    "utf8",
  );
  const ownerBootstrap = readFileSync(
    join(sourceRepository, "ui/next-app/scripts/bootstrap-owner.ts"),
    "utf8",
  );
  const workerEntrypoint = readFileSync(join(moduleDirectory, "worker-entrypoint.mjs"), "utf8");
  const workerHealthcheck = readFileSync(join(moduleDirectory, "worker-healthcheck.mjs"), "utf8");
  const workerContainerAcceptance = readFileSync(
    join(moduleDirectory, "worker-container-acceptance.mjs"),
    "utf8",
  );
  if (
    !ownerService.includes("profiles: [owner-bootstrap]")
    || !ownerService.includes("--postgres-migrator")
    || !ownerService.includes("postgres_migrator_password")
    || ownerService.includes("postgres_runtime_password")
    || ownerService.includes("postgres_entitlement_admin_password")
    || ownerService.includes("entitlement_operator_password")
    || ownerService.includes("human_session_hmac_key")
    || !ownerOperator.includes("--password-stdin")
    || !ownerOperator.includes("--pull never")
    || ownerOperator.includes("--no-build")
    || !ownerOperator.includes("set +x")
    || /openssl|rand\b/.test(ownerOperator)
    || !ownerEntrypoint.includes("PGPASSFILE")
    || !ownerEntrypoint.includes("process.execPath")
    || !ownerEntrypoint.includes('["--import", "tsx", "scripts/bootstrap-owner.ts"')
    || /spawn\(\s*"npm"/.test(ownerEntrypoint)
    || ownerEntrypoint.includes("childEnvironment.PGPASSWORD =")
    || !ownerBootstrap.includes("enforceMigrationAuthority: true")
    || ownerBootstrap.includes("enforceRuntimeBoundary: false")
  ) {
    fail("release_owner_bootstrap_boundary_invalid");
  }
  if (
    !compose.includes("profiles: [worker-hermes]")
    || !compose.includes("profiles: [worker-openclaw]")
    || !compose.includes("AGENTOPS_AGENT_TOKEN_SOURCE_FILE: /run/secrets/agent_token")
    || !compose.includes("/usr/local/lib/agentops/worker-entrypoint.mjs")
    || !compose.includes("/usr/local/lib/agentops/worker-healthcheck.mjs")
    || /\n\s+(?:AGENTOPS_API_KEY|AGENTOPS_AGENT_TOKEN):/.test(compose)
    || !workerEntrypoint.includes("direct_agent_token_environment_forbidden")
    || !workerEntrypoint.includes("worker_receipt_boundary_invalid")
    || !workerHealthcheck.includes("process.kill(payload.pid, 0)")
    || !workerContainerAcceptance.includes("agentops_byoc_typescript_worker_container_v1")
    || !workerContainerAcceptance.includes("provider_connections")
    || !workerContainerAcceptance.includes("agent_token_exposed_by_container")
    || !workerContainerAcceptance.includes('"--network", "none"')
    || !workerContainerAcceptance.includes("authorization_matches")
    || !workerContainerAcceptance.includes("org.opencontainers.image.revision")
  ) {
    fail("release_worker_boundary_invalid");
  }
  const installer = readFileSync(join(moduleDirectory, "install.sh"), "utf8");
  if (
    !installer.includes('fail "release_unmanifested_file"')
    || !installer.includes("stack_start_attempted=true")
    || !installer.includes("stop --timeout 10")
    || !installer.includes('[ "$install_complete" = false ]')
    || !installer.includes('host_platform=$(docker info --format')
    || !installer.includes('fail "customer_host_platform_unsupported"')
    || !installer.includes("pull --quiet")
  ) {
    fail("release_installer_failure_cleanup_contract_missing");
  }

  const workflow = readFileSync(
    join(sourceRepository, ".github/workflows/byoc-customer-release-acceptance.yml"),
    "utf8",
  );
  const consumerStart = workflow.indexOf("  clean-customer-install:\n");
  const nextJob = /^  [a-z][a-z0-9-]+:\n/gm;
  nextJob.lastIndex = consumerStart < 0 ? workflow.length : consumerStart + 1;
  const nextJobMatch = nextJob.exec(workflow);
  const consumer = consumerStart < 0
    ? ""
    : workflow.slice(consumerStart, nextJobMatch?.index || workflow.length);
  if (!consumer || /actions\/checkout|^\s+(?:run:\s*)?git\s/m.test(consumer)) {
    fail("release_consumer_checkout_boundary_invalid");
  }
  if (
    !consumer.includes(
      "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
    )
    || !/contents: read[\s\S]*packages: read[\s\S]*attestations: read/.test(consumer)
    || !consumer.includes("gh attestation verify")
    || !consumer.includes("--signer-workflow")
    || !consumer.includes("--source-ref")
    || !consumer.includes("--source-digest")
    || !consumer.includes("--deny-self-hosted-runners")
    || !consumer.includes("repository_checkout_required == false")
    || !consumer.includes("compose_build_performed == false")
    || !consumer.includes("/owner-init.sh")
    || !consumer.includes('owner_stderr="${RUNNER_TEMP}/customer-owner-bootstrap.stderr"')
    || !consumer.includes('duplicate_stderr="${RUNNER_TEMP}/customer-owner-duplicate.stderr"')
    || consumer.includes('--password-stdin > "${duplicate_receipt}" 2>&1')
    || !consumer.includes('"${owner_receipt}" "${owner_stderr}"')
    || !consumer.includes('"${duplicate_receipt}" "${duplicate_stderr}"')
    || !consumer.includes('owner_initial_status=${owner_status}')
    || !consumer.includes('owner_initial_receipt_parse=${owner_receipt_parse}')
    || !consumer.includes('owner_initial_error=${owner_error}')
    || !consumer.includes('owner_initial_stderr_nonempty=${owner_stderr_nonempty}')
    || !consumer.includes('test("^[a-z][a-z0-9_]{2,80}$")')
    || !consumer.includes('owner_duplicate_receipt_parse=${duplicate_receipt_parse}')
    || !consumer.includes('owner_duplicate_error=${duplicate_error}')
    || !consumer.includes("owner_duplicate_credential_residue")
    || !consumer.includes('test "${duplicate_status}" -ne 0')
    || consumer.includes('test "${duplicate_status}" -eq 2')
    || !consumer.includes('and .operation == "commercial_owner_bootstrap"')
    || !consumer.includes('and .error == "owner_already_initialized"')
    || !consumer.includes("human_auth.owner_bootstrap")
    || !consumer.includes("/deploy/byoc/worker-container-acceptance.mjs")
    || !consumer.includes('and .contract == "agentops_byoc_typescript_worker_container_v1"')
    || !consumer.includes("and .provider_connections == 0")
    || !consumer.includes("and .network_egress_disabled == true")
    || !consumer.includes("and .agent_token_authorization_verified == true")
    || !consumer.includes("and .token_in_argv == false")
  ) {
    fail("release_consumer_contract_missing");
  }
  if (
    !consumer.includes("/deploy/byoc/backup.sh")
    || !consumer.includes("/deploy/byoc/restore-drill.sh")
    || !consumer.includes("/deploy/byoc/retained-data-lifecycle.mjs")
    || !consumer.includes('and .operation == "apply"')
    || !consumer.includes('and .operation == "rollback"')
    || !consumer.includes("and .backup_restore_authoritative == true")
    || !consumer.includes('test "$(audit_count "${authority_id}"')
    || !consumer.includes('test "$(audit_count "${probe_id}"')
    || !consumer.includes("SELECT count(*) FROM audit_logs WHERE audit_id = :'audit_id';")
    || consumer.includes('--command "SELECT count(*) FROM audit_logs WHERE audit_id=')
  ) {
    fail("release_consumer_lifecycle_contract_missing");
  }
  if (
    !workflow.includes(
      "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
    )
    || !workflow.includes("id-token: write")
    || !workflow.includes("attestations: write")
    || !workflow.includes("archive_sha256")
  ) {
    fail("release_signed_provenance_contract_missing");
  }
  if (
    !workflow.includes("docker build --pull --platform linux/amd64")
    || !workflow.includes("'{{.Architecture}}'")
    || !workflow.includes('= "amd64"')
  ) {
    fail("release_platform_workflow_binding_missing");
  }
  if (
    !workflow.includes("push:\n    branches:\n      - codex/commercial-control-plane-main-integration")
    || workflow.includes("pull_request:")
    || workflow.includes("workflow_call:")
  ) {
    fail("release_exact_branch_trigger_boundary_missing");
  }

  const composeWorkflow = readFileSync(
    join(sourceRepository, ".github/workflows/byoc-compose-acceptance.yml"),
    "utf8",
  );
  if (
    (composeWorkflow.match(/DOCKER_DEFAULT_PLATFORM=linux\/amd64/g) || []).length !== 2
    || (composeWorkflow.match(/'\{\{\.Architecture\}\}'/g) || []).length < 2
  ) {
    fail("compose_release_platform_binding_missing");
  }

  const backup = readFileSync(join(moduleDirectory, "backup.sh"), "utf8");
  const lifecycle = readFileSync(
    join(moduleDirectory, "retained-data-lifecycle.mjs"),
    "utf8",
  );
  if (
    !backup.includes("backup_node_20_required")
    || !lifecycle.includes("lifecycle_node_20_required")
  ) {
    fail("release_operator_node_preflight_missing");
  }
}

const temporaryRoot = mkdtempSync(join(tmpdir(), "agentops-byoc-release-contract-"));

try {
  assertStaticCustomerBoundary();
  run(process.execPath, [join(moduleDirectory, "worker-service-contract.mjs")], sourceRepository);
  const repository = join(temporaryRoot, "repository");
  mkdirSync(repository);
  copyInputs(repository);
  run("git", ["init", "--quiet"], repository);
  run("git", ["config", "user.name", "BYOC Release Contract"], repository);
  run("git", ["config", "user.email", "byoc-release@example.invalid"], repository);
  run("git", ["add", "."], repository);
  run("git", ["commit", "--quiet", "-m", "clean release fixture"], repository);
  const revision = run("git", ["rev-parse", "HEAD"], repository).stdout.trim();
  if (!/^[0-9a-f]{40}$/.test(revision)) fail("release_clean_head_invalid");
  if (run("git", ["status", "--porcelain"], repository).stdout !== "") {
    fail("release_fixture_not_clean");
  }

  const builder = join(repository, "deploy/byoc/build-release-bundle.mjs");
  const output = join(temporaryRoot, "customer-release");
  const built = run(process.execPath, [
    builder,
    "build",
    "--output", output,
    "--image", image,
    "--source-revision", revision,
  ], repository);
  const receipt = JSON.parse(built.stdout);
  if (
    receipt.contract !== "agentops_byoc_release_bundle_v1"
    || receipt.source_revision !== revision
    || receipt.image_digest_verified !== true
    || receipt.credentials_omitted !== true
    || receipt.application_source_omitted !== true
    || receipt.repository_checkout_required !== false
    || receipt.owner_bootstrap_command_included !== true
  ) fail("release_build_receipt_invalid");

  const verified = run(
    process.execPath,
    [builder, "verify", output],
    repository,
  );
  if (JSON.parse(verified.stdout).source_revision !== revision) {
    fail("release_verify_revision_mismatch");
  }
  const installerVerification = run(
    join(output, "install.sh"),
    ["--verify-only"],
    output,
  );
  const installerReceipt = JSON.parse(installerVerification.stdout);
  if (
    installerReceipt.contract !== "agentops_byoc_customer_install_v1"
    || installerReceipt.operation !== "verify"
    || installerReceipt.source_revision !== revision
    || installerReceipt.image_digest_verified !== true
    || installerReceipt.repository_checkout_required !== false
  ) fail("release_installer_verify_contract_invalid");

  const manifest = JSON.parse(readFileSync(join(output, "release-manifest.json"), "utf8"));
  if (manifest.image !== image || manifest.files.length !== receipt.file_count) {
    fail("release_manifest_receipt_mismatch");
  }
  if (readFileSync(join(output, "release-image.env"), "utf8") !== `AGENTOPS_IMAGE=${image}\n`) {
    fail("release_image_environment_invalid");
  }
  const forbidden = files(output).filter((path) =>
    path === ".git"
    || path.endsWith("/build-release-bundle.mjs")
    || path.endsWith("/Dockerfile")
    || path.endsWith("/package.json")
    || path.endsWith("/package-lock.json")
    || path.endsWith("/server.py")
    || path.startsWith("migrations/")
  );
  if (forbidden.length) fail("release_source_or_build_input_present");
  if ((readFileSync(join(output, "owner-init.sh")).length || 0) < 1) {
    fail("release_owner_bootstrap_operator_missing");
  }
  if (
    (readFileSync(
      join(output, "deploy/byoc/worker-container-acceptance.mjs"),
      "utf8",
    ).length || 0) < 1
  ) {
    fail("release_worker_container_acceptance_missing");
  }

  writeFileSync(join(output, "compose.override.yaml"), "services: {}\n", "utf8");
  const unmanifested = run(
    join(output, "install.sh"),
    ["--verify-only"],
    output,
    [0, 1],
  );
  if (
    unmanifested.status === 0
    || !unmanifested.stderr.includes("release_unmanifested_file")
  ) fail("release_unmanifested_file_guard_missing");
  rmSync(join(output, "compose.override.yaml"));

  const fakeBin = join(temporaryRoot, "fake-bin");
  const dockerLog = join(temporaryRoot, "fake-docker.log");
  mkdirSync(fakeBin);
  writeFileSync(
    join(fakeBin, "docker"),
    `#!/bin/sh
set -eu
case " $* " in
  *" info --format "*) printf '%s\\n' "\${AGENTOPS_FAKE_PLATFORM:-linux/amd64}" ;;
  *" image inspect "*) printf '%s\\n' "$AGENTOPS_FAKE_REVISION" ;;
  *" stop --timeout 10 "*) printf '%s\\n' "stop" >> "$AGENTOPS_FAKE_DOCKER_LOG" ;;
esac
exit 0
`,
    { encoding: "utf8", mode: 0o700 },
  );
  writeFileSync(
    join(fakeBin, "curl"),
    "#!/bin/sh\nexit 1\n",
    { encoding: "utf8", mode: 0o700 },
  );
  const unsupportedHost = runWithEnvironment(
    join(output, "install.sh"),
    [],
    output,
    {
      ...process.env,
      PATH: `${fakeBin}:${process.env.PATH || ""}`,
      AGENTOPS_FAKE_PLATFORM: "linux/arm64",
      AGENTOPS_FAKE_REVISION: revision,
      AGENTOPS_FAKE_DOCKER_LOG: dockerLog,
    },
    [0, 1],
  );
  if (
    unsupportedHost.status === 0
    || !unsupportedHost.stderr.includes("customer_host_platform_unsupported")
    || files(output).some((path) => path === "deploy/byoc/.env"
      || path.startsWith("deploy/byoc/secrets/"))
  ) fail("release_unsupported_host_guard_missing");

  const missingNodeOutput = join(temporaryRoot, "missing-node.bundle");
  const missingNode = runWithEnvironment(
    "/bin/sh",
    [join(output, "deploy/byoc/backup.sh"), missingNodeOutput],
    output,
    { ...process.env, PATH: fakeBin },
    [0, 1],
  );
  if (
    missingNode.status === 0
    || !missingNode.stderr.includes("backup_node_20_required")
    || files(temporaryRoot).some((path) => path.startsWith("missing-node.bundle/"))
  ) fail("release_backup_node_preflight_missing");

  const failedHealth = runWithEnvironment(
    join(output, "install.sh"),
    [],
    output,
    {
      ...process.env,
      PATH: `${fakeBin}:${process.env.PATH || ""}`,
      AGENTOPS_FAKE_REVISION: revision,
      AGENTOPS_FAKE_DOCKER_LOG: dockerLog,
    },
    [0, 1],
  );
  if (
    failedHealth.status === 0
    || !failedHealth.stderr.includes("customer_health_failed")
    || readFileSync(dockerLog, "utf8").trim() !== "stop"
  ) fail("release_failed_health_cleanup_missing");
  rmSync(join(output, "deploy/byoc/.env"));
  rmSync(join(output, "deploy/byoc/secrets"), { force: true, recursive: true });

  const overwrite = run(process.execPath, [
    builder,
    "build",
    "--output", output,
    "--image", image,
    "--source-revision", revision,
  ], repository, [0, 1]);
  if (overwrite.status === 0 || !overwrite.stderr.includes("release_output_exists")) {
    fail("release_overwrite_guard_missing");
  }

  const releaseReadmePath = join(repository, "deploy/byoc/RELEASE_BUNDLE.md");
  const releaseReadme = readFileSync(releaseReadmePath);
  appendFileSync(releaseReadmePath, "dirty\n", "utf8");
  const dirty = run(process.execPath, [
    builder,
    "build",
    "--output", join(temporaryRoot, "dirty-release"),
    "--image", image,
    "--source-revision", revision,
  ], repository, [0, 1]);
  if (dirty.status === 0 || !dirty.stderr.includes("release_inputs_not_committed")) {
    fail("release_dirty_input_guard_missing");
  }
  writeFileSync(releaseReadmePath, releaseReadme);

  appendFileSync(
    join(repository, "ui/next-app/scripts/bootstrap-owner.ts"),
    "// dirty owner runtime dependency\n",
    "utf8",
  );
  const dirtyOwnerRuntime = run(process.execPath, [
    builder,
    "build",
    "--output", join(temporaryRoot, "dirty-owner-runtime-release"),
    "--image", image,
    "--source-revision", revision,
  ], repository, [0, 1]);
  if (
    dirtyOwnerRuntime.status === 0
    || !dirtyOwnerRuntime.stderr.includes("release_inputs_not_committed")
  ) fail("release_owner_runtime_dirty_input_guard_missing");

  appendFileSync(join(output, "README.md"), "tampered\n", "utf8");
  const tampered = run(
    process.execPath,
    [builder, "verify", output],
    repository,
    [0, 1],
  );
  if (tampered.status === 0 || !tampered.stderr.includes("release_file_checksum_mismatch")) {
    fail("release_tamper_guard_missing");
  }

  process.stdout.write(`${JSON.stringify({
    ok: true,
    contract: "agentops_byoc_release_bundle_contract_v2",
    clean_head_bound: true,
    source_free_bundle_verified: true,
    installer_verify_only_passed: true,
    no_checkout_consumer_bound: true,
    overwrite_refused: true,
    dirty_input_refused: true,
    unmanifested_file_refused: true,
    unsupported_host_refused: true,
    signed_provenance_required: true,
    node_20_operator_preflight_required: true,
    owner_bootstrap_operator_packaged: true,
    owner_bootstrap_real_customer_acceptance_required: true,
    owner_bootstrap_runtime_inputs_revision_bound: true,
    owner_bootstrap_password_stdin_only: true,
    owner_bootstrap_entitlement_boundary_unchanged: true,
    source_free_typescript_worker_profiles_packaged: true,
    worker_file_secret_and_health_lease_verified: true,
    worker_container_customer_acceptance_required: true,
    real_provider_execution_performed: false,
    failed_health_stack_stopped: true,
    tamper_refused: true,
    credentials_omitted: true,
  })}\n`);
} catch (error) {
  process.stderr.write(`${typeof error?.code === "string" ? error.code : "release_bundle_contract_failed"}\n`);
  process.exitCode = 1;
} finally {
  rmSync(temporaryRoot, { force: true, recursive: true });
}
