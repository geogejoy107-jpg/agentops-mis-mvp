# OpenClaw A07 Signed Runtime Path Audit

Status: blocking audit of the current A07 branch plus its A08 egress candidate.
Updated 2026-08-24. This document distinguishes implemented source paths from
exact-head Linux, Docker, and real-provider evidence.

The current candidate has materially advanced beyond the original A07 design:
the Executor consumes canonical signed runtime manifest v2, retains the guest
root and runtime executable descriptors, and passes those descriptors to the
native launcher. The source-only contracts do not prove that this exact working
tree has executed successfully on Linux. A08 provider egress is wired as a
four-service candidate, but its real network policy gate remains false.

## 1. Finding Summary

| ID | Severity | Current finding | Required evidence or closure |
| --- | --- | --- | --- |
| PATH-01 | P1 | Manifest v2 is now consumed by the production Executor preflight. The service securely reads the committed release and trust roots, verifies the canonical Ed25519 envelope and signed runtime, OCI, platform, policy, uid/gid, entrypoint, and rootfs bindings. | Run the exact current head through the real Linux workflow; source and injected contracts are not runtime evidence. |
| PATH-02 | P1 | Preflight opens the guest root with `O_DIRECTORY | O_NOFOLLOW`, opens the signed runtime executable with `O_NOFOLLOW`, checks path/fd identity around a second rootfs measurement, and retains both `rootFd` and `execFd` for dispatch. | Prove descriptor identity, lifetime, and cleanup in the exact-head root Linux run. |
| PATH-03 | P1 | The default runner passes retained root, executable, and cgroup descriptors to the native launcher. The launcher source owns the `fchdir`/`chroot` and `execveat(..., AT_EMPTY_PATH)` path rather than projecting the entrypoint into the Executor root. | Re-run the strict default open/spawn contract on the exact image and record non-synthetic evidence. |
| PATH-04 | P1 | `openclaw-runtime-real-runner-contract.mjs` has a source-audit mode that deliberately reports `strict_linux_execution_performed=false`. Its strict mode requires root Linux, a real guest root, launcher, cgroup v2, and default runner dependencies. | Do not treat source-audit output as strict-mode evidence. The current exact-head strict result is pending. |
| PATH-05 | P1 | The A08 candidate wires `worker`, `broker`, `executor`, and `egress-gateway`; the runtime-facing network is internal and only the gateway also joins the provider-egress network. OpenClaw config requires replacement mode and is restricted to one fixed internal gateway base URL plus three supported provider API modes. | Prove DNS, routing, direct-egress denial, gateway-only provider access, redirect/rebinding denial, and fail-closed startup on real Linux. `runtime_network_policy_verified` remains false. |
| PATH-06 | P1 | The repository can build, export, measure, and sign an ephemeral digest-pinned guest-root candidate, but this A08 candidate has no recorded exact-head remote Linux result and no same-head real-provider receipt. | Run the exact-head Linux gates on a Docker-capable Linux host, then record real provider evidence against that exact candidate. |

These findings are release blockers, not evidence of a completed hostile-runtime
or provider-egress gate. Historical Linux or provider receipts from earlier
commits cannot be attributed to the current A08 candidate.

## 2. Current Manifest v2 Path

### 2.1 Secure input and signature verification

`openclaw-executor-service.mjs` now imports the manifest v2 implementation and
performs the following production preflight path:

1. It validates the configured runtime root, release root, trust-root path,
   issuer, key id, runtime image identity, and fixed runtime uid/gid.
2. It reads policy, trust, and release inputs through bounded regular-file
   checks. `readSecureFile` requires a root-owned, non-writable, single-link
   regular file, opens it with `O_NOFOLLOW | O_CLOEXEC`, and compares pathname
   and descriptor identity before accepting bytes.
3. It reads the committed runtime release and parses the canonical manifest v2
   envelope.
4. It verifies the Ed25519 signature and exact bindings for issuer/key, body
   digest, OCI image, platform, cgroup and seccomp policy hashes, runtime
   executable, entrypoint, uid/gid, and rootfs Merkle identity.
5. It measures mutable-mount policy and immutable rootfs content twice, rejecting
   changes in mount evidence, Merkle digest, file count, byte count, or runtime
   root identity during preflight.

This is an implemented fail-closed code path. It does not establish that the
current exact working tree has completed preflight in a real Linux candidate.

### 2.2 Retained root and executable descriptors

The service opens and retains:

```text
rootFd = open(runtimeRoot, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
execFd = open(runtimeExecutableBelowRoot, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
```

Before returning from preflight it compares the opened executable with its
pathname identity before and after the second tree measurement and rechecks the
runtime-root fd against the configured path. The resulting preflight object owns
`runtimeHandles = { execFd, rootFd }`; these descriptors are not closed at the
end of successful preflight. Failure paths close them, and the service shutdown
path closes the retained handles.

For each dispatch, the default runner passes the retained descriptors to the
launcher as inherited fd 3 and fd 4, with a request cgroup descriptor at fd 5
and the readiness pipe at fd 6. The native launcher is expected to enter the
guest root and execute the already-opened runtime executable by fd. This removes
the old design in which Node reopened a lexically projected host path from the
Executor root.

The remaining claim boundary is evidence, not source wiring: the local
source-only contract can verify exports, code shape, and fail-closed branches,
but only the strict root-Linux mode exercises the real default file opens,
launcher spawn, chroot, cgroup, guest entrypoint, and descriptor cleanup.

## 3. A08 Provider Egress Candidate

The A08 code changes the candidate topology to four services:

| Service | Network access in Compose source | Role |
| --- | --- | --- |
| `worker` | `control-plane` only | Commercial TypeScript Worker and MIS control-plane traffic. |
| `broker` | `network_mode: none` | Unix-socket request and verified-receipt boundary. |
| `executor` | internal `runtime-egress` only | Root bootstrap, manifest preflight, launcher, and guest runtime. |
| `egress-gateway` | internal `runtime-egress` plus external `provider-egress` | The sole source-wired bridge from runtime traffic to one operator-approved HTTPS provider origin. |

`runtime-egress` is declared with `internal: true`. The gateway is addressed by
the fixed service alias `openclaw-egress-gateway` and runs as uid/gid 1300 with a
read-only root, all capabilities dropped, `no-new-privileges`, bounded pids, and
a bounded tmpfs.

Executor preflight securely reads the OpenClaw configuration from the
manifest-declared guest path `/run/secrets/openclaw_config` and invokes the A08
validator. The validator requires `models.mode` to equal `replace` and every
configured provider to use exactly:

```text
http://openclaw-egress-gateway:18080/v1
```

Only `anthropic-messages`, `openai-completions`, and `openai-responses` are
accepted. The gateway source allowlists the matching provider routes, requires
POST JSON requests, applies body/response/concurrency/deadline bounds, pins DNS
resolution to public addresses, rejects redirects and unsafe origins, and
redacts upstream failures.

These are source and configuration gates only. The current candidate has not yet
proved on real Linux that the guest can resolve and reach the gateway while all
direct provider, metadata, private-address, alternate-DNS, redirect, and DNS
rebinding paths fail. Therefore:

```text
internal_runtime_egress_network_wired = true
provider_egress_config_gate_wired     = true
trusted_provider_egress_gateway_wired = true
runtime_network_policy_verified       = false
```

The existing operator egress attestation remains a required input. It must not
be interpreted as a substitute for A08 attack acceptance.

## 4. Evidence Boundary

### 4.1 What source contracts can establish

The current local contracts can check:

- manifest v2 canonical parsing, signature and binding rejection paths;
- service preflight ownership, no-follow reads, rootfs measurements, and retained
  handle wiring;
- default runner source export and launcher descriptor handoff;
- A08 fixed gateway URL, provider API allowlist, request bounds, DNS/origin
  rejection logic, and Compose topology;
- claim outputs that remain false until a stricter lane supplies evidence.

The source-audit invocation of the real-runner contract must continue to emit:

```text
real_default_open_spawn_executed          = false
runtime_sensitive_path_open_denials_verified = false
runtime_path_toctou_closed                = false
strict_linux_execution_performed          = false
```

An injected runner contract may model a successful provider result to exercise
receipt logic, but it still reports `real_runtime_process_spawned=false` and
cannot become product evidence.

### 4.2 What remains pending

The exact current head plus A08 changes still require:

1. A real root-Linux strict runner using the production default open/spawn path,
   real launcher, cgroup v2, signed guest root, and sensitive-path probes.
2. A real four-service Compose run proving the internal network boundary and
   gateway-only provider access under adversarial DNS, redirect, private-address,
   metadata-address, direct-IP, and direct-origin attempts.
3. A same-head real OpenClaw provider call through the gateway, followed by
   Broker receipt verification and cleanup evidence, without raw prompt,
   response, credential, or transcript capture.
4. Exact-head remote workflow results and durable release evidence for the image,
   OCI export, Merkle inventory, manifest, and signatures used by the run.

No exact-candidate Linux/Docker evidence for those lanes is currently recorded.
Static Compose rendering or source-contract success does not replace either
missing runtime.

## 5. Acceptance Assertions

The path and A08 gates are not complete until one exact candidate proves all of
the following:

1. Manifest v2 and trust inputs are the exact signed files consumed by Executor
   preflight, and tamper, replacement, symlink, ownership, mode, issuer, key,
   image, platform, policy, or Merkle drift fails before dispatch.
2. `/proc/<pid>/exe` identifies the retained executable, the process root is the
   signed guest root, and the entrypoint, loader, libraries, modules, config,
   workspace, state, and tmp resolve only under the declared guest-root policy.
3. Root and executable fd identity remains stable through dispatch and both
   descriptors are closed on every final service path.
4. The guest runs as uid/gid 1200 with the expected fixed environment, enters
   its delegated cgroup, receives the exact launcher `R` readiness handshake,
   and leaves no descendants or undeclared state after success, failure,
   cancellation, or timeout.
5. Sensitive Executor paths, host canaries, replay storage, signing material,
   policies, manifests, and trust roots cannot be opened by the guest.
6. The runtime reaches the approved provider only through
   `openclaw-egress-gateway:18080`; direct external traffic and every bypass case
   fail closed without leaking upstream errors or credentials.
7. Broker verification binds the exact Executor image, runtime image, manifest,
   isolation policy, request, process outcome, provider outcome, and cleanup
   evidence from that same run.

## 6. Claim Boundary

The accurate state for the current A08 candidate is:

```text
manifest_v2_consumed_by_executor_source       = true
secure_manifest_and_trust_read_path_wired     = true
root_and_exec_fds_retained_by_preflight       = true
default_runner_fd_handoff_wired               = true
four_service_egress_topology_wired            = true
provider_egress_config_gate_wired             = true
source_only_contracts_equal_real_linux        = false
exact_head_strict_linux_execution_verified    = false
exact_head_real_provider_call_verified        = false
runtime_network_policy_verified               = false
runtime_path_toctou_closed                     = false
runtime_receipt_verified                       = false
hostile_runtime_isolation_verified             = false
```

Do not promote a source contract, static Compose render, healthcheck, operator
attestation, historical CI run, or historical provider receipt into any of the
false claims above. Promotion requires the exact-head evidence chain described
in Sections 4 and 5.
