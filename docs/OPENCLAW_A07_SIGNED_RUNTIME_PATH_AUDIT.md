# OpenClaw A07 Signed Runtime Path Audit

Status: blocking design audit for the A07 root Executor candidate.

This document audits the A07 foundation and integrated Executor runner source as
of 2026-08-12. The runner's contracts use injected execution dependencies; they
are not real-runtime or hostile-runtime acceptance evidence.

## 1. Finding Summary

| ID | Severity | Finding | Current consequence |
| --- | --- | --- | --- |
| PATH-01 | P1 | The runner now projects absolute `argv[1...]` paths below `runtimeRoot`, but that projection is duplicated runner logic, not a signed manifest path model or a root-fd-anchored resolver. | `/app/main.mjs` lexically becomes `/opt/agentops-provider/openclaw/app/main.mjs`, but a parent-component or mount replacement can redirect the pathname after preflight. |
| PATH-02 | P1 | Exact-tree verification closes every measured file descriptor. Per-request execution reopens and rehashes only Node; entrypoint and module loading reopen by pathname without manifest comparison. | Startup verification is not an execution-time binding. Host-side replacement behind the read-only bind mount remains a TOCTOU window. |
| PATH-03 | P1 | `execveat(..., AT_EMPTY_PATH)` binds only the Node executable inode. The projected `argv[1]`, absolute imports, subprocess paths, and later module loads are not fd-bound. | The Node binary can be measured while executable content loaded after startup comes from a replaced tree or the Executor root. |
| PATH-04 | P2 | The verifier uses absolute path joins plus `lstat`, `realpath`, and final-component `O_NOFOLLOW`; it is not descriptor-relative despite the architecture text. | Parent-component changes are checked but not atomically prevented. `openat2` root confinement is absent. |
| PATH-05 | P2 | A dynamically linked Node opened by fd still obtains its ELF interpreter and shared libraries from the Executor container root. | Those files are bound only by the immutable Executor image digest, not by the runtime manifest. This is acceptable only as an explicit two-root trust model. |
| PATH-06 | P1 | The repository has no claim-bearing build step that creates the real A07 runtime root and its manifest, and no Linux test invokes the runner's default path/open/spawn dependencies. | The green manifest test uses a synthetic tree, while the green runner test replaces all path and process operations. Neither proves that a real OpenClaw artifact has the declared `/usr/bin/node` and `/app/stdin-provider.mjs` shape. |

These are design blockers, not evidence of a successful hostile execution. The
working-tree service calls the runner, but the runner contract injects file-open,
launcher-spawn, cgroup, and child-result behavior. Its own output correctly says
`real_runtime_process_spawned=false`.

The launcher/runner status pipe is a narrower completed improvement. The
launcher emits `R` only after its isolation sequence and marks the descriptor
`CLOEXEC`; the runner requires exact `R` before accepting output. Missing status
or `RE` cannot produce a receipt. This proves neither root-fd path confinement
nor a real runtime launch, so it does not change any finding or claim below.

A native `openat2` resolver primitive is now packaged and tested separately. It
rejects traversal, symlinks, proc magiclinks, and mount crossing below an
inherited root directory fd. It currently reports
`resolved_fd_handoff_verified=false` and closes the resolved file descriptors;
the runner and launcher do not consume them yet. PATH-01 through PATH-04
therefore remain open until the resolved executable/entrypoint identity is
carried without pathname reopening into the actual launch sequence.

The source-only stdin adapter removes the prompt-argv blocker without weakening
the runner gate. It calls OpenClaw's public `agentCommand` export and has passed
a real local agent turn, but it is not yet part of a claim-bearing runtime
artifact or Linux launcher acceptance. The official OpenClaw 2026.5.4 tarball
contains 9,692 files; a full production dependency install measured roughly
44,670 files and 441 MiB, exceeding the current 20,000-file manifest bound.
Increasing that bound and copying an operator's global install is rejected as a
closure. The build must produce a version- and integrity-pinned OCI artifact or
a verified smaller adapter bundle whose dynamic resources are explicit. The
preferred closure is a complete platform-specific guest root: launcher-side
`openat2`, `fchdir`/`chroot`, and `execveat` then keep Node, ESM imports, native
addons, the ELF interpreter, and shared libraries inside one immutable root.

## 2. Current Path Trace

The manifest contract uses this metadata:

```text
runtime_executable = /usr/bin/node
entrypoint         = /app/main.mjs
argv_template      = [/usr/bin/node, /app/main.mjs, --mode=provider]
runtime_root       = /opt/agentops-provider/openclaw
```

`manifestPathToRelative` removes the first slash:

```text
/usr/bin/node -> usr/bin/node
/app/main.mjs -> app/main.mjs
```

Tree verification therefore measures these Executor-namespace paths:

```text
/opt/agentops-provider/openclaw/usr/bin/node
/opt/agentops-provider/openclaw/app/main.mjs
```

The Compose candidate mounts the host runtime tree only at
`/opt/agentops-provider/openclaw`. It does not mount that tree at `/`, `/usr`, or
`/app`, and the launcher does not call `chroot`, `pivot_root`, `fchdir`, or enter
a separate mount namespace.

The working-tree runner performs this mapping before calling the launcher:

1. It opens and rehashes
   `/opt/agentops-provider/openclaw/usr/bin/node`, then passes that fd as child
   fd 3.
2. It leaves `argv[0]` as `/usr/bin/node`. On Linux this is process-visible
   metadata; it does not choose the executable after fd execution.
3. For every absolute string at `argv[1...]`, it calls its local
   `manifestAbsolutePath`. The entrypoint becomes
   `/opt/agentops-provider/openclaw/app/stdin-provider.mjs`.
4. `execveat(exec_fd, "", child_argv, env, AT_EMPTY_PATH)` executes the inode
   held by fd 3. Node then opens the projected entrypoint by pathname.

The executable and entrypoint now lexically point into the same mounted tree, so
the earlier deterministic no-chroot `ENOENT` mismatch is avoided. They are not
bound to the same verified snapshot: only the executable is rehashed and held
by fd, while the entrypoint and modules are reopened after preflight. The runner
also projects any absolute argv value solely because it starts with `/`; the
manifest schema does not distinguish guest-root paths from opaque absolute
argument values.

No chroot still matters beyond the entrypoint. An absolute import, an executable
looked up through `PATH=/usr/bin:/bin`, or another absolute runtime file access
resolves against the Executor container root. The ELF interpreter and shared
libraries for the fd-executed Node binary also resolve there.

### 2.1 Artifact and test gap

The only repository caller of `generateRuntimeManifest` is
`openclaw-runtime-manifest-contract.mjs`. That contract creates a synthetic tree
with `usr/bin/node` and `app/*.mjs`. The A07 Compose file instead accepts an
operator path through `AGENTOPS_A07_RUNTIME_PATH`; it does not build or unpack a
digest-bound runtime artifact. Earlier OpenClaw topologies document a different
runtime shape with `bin/openclaw`.

The runner contract injects `openExecutionFiles`, `spawnLauncher`, cgroup
operations, and child results. It verifies governance and receipt behavior, but
does not execute `manifestAbsolutePath`, open the real Node fd, invoke the native
launcher, or let Node open the projected entrypoint. Consequently the current
path projection is source-reviewed only.

## 3. TOCTOU Boundary

`stableMeasuredTree` provides a useful bounded snapshot check:

- it rejects symlinks, hard links, special files, writable files and writable
  directories;
- it opens each final file with `O_NOFOLLOW`, hashes that descriptor, compares
  descriptor identity before and after reading, and repeats tree discovery;
- it rejects extra files and metadata or digest drift during that check.

It does not pin the verified tree for execution:

- all measured file descriptors are closed before preflight returns;
- preflight retains the manifest body and digest, not a root directory fd,
  executable fd, entrypoint fd, mount id, or per-file execution identity;
- the runtime source is an operator-provided host bind mount. `read_only: true`
  prevents writes from the container view but does not make the host backing
  tree content-addressed or immutable;
- the current runner reopens and rehashes the executable, but Node reopens the
  entrypoint, JavaScript modules, package metadata, native addons, and data files
  itself without request-time manifest comparison;
- `O_NOFOLLOW` covers the final component only. The preceding `lstat` and
  `realpath` checks are separate pathname operations, not an atomic
  `openat2(..., RESOLVE_IN_ROOT | RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS)` walk.

An executable fd removes the final executable pathname race only after that fd
has been opened and matched to the verified record. It does not bind the script
or Node's subsequent dependency loads.

## 4. Intermediate A07 Closure

The smallest independently reviewable step should turn the runner's current lexical
projection into a signed, root-anchored, immutable execution model without
claiming a complete hostile-runtime namespace.

### 4.1 Signed semantics

Introduce a manifest schema revision with:

```text
path_model = guest_root_absolute_v1
```

For every manifest absolute runtime path `G`, derive exactly one relative path
`R` and one Executor path `H`:

```text
R = validate_and_strip_one_leading_slash(G)
H = openat2(runtime_root_fd, R, RESOLVE_IN_ROOT | RESOLVE_BENEATH |
            RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS | RESOLVE_NO_XDEV)
```

`runtime_mount_path` is deployment configuration, not guest-runtime identity,
so it need not be signed. It must be opened once as a root fd and recorded by
mount id. Do not allow callers to concatenate or independently reinterpret
guest paths. The same resolver must own manifest validation, preflight
measurement, and request execution. The argv schema must explicitly mark which
items are guest paths instead of rewriting every absolute string.

### 4.2 Immutable source

Replace the arbitrary host runtime bind as the production source of truth. The
runtime tree should be copied into or mounted from a content-addressed OCI layer
bound to the exact runtime image digest. The mount must be read-only for the
entire Executor lifetime. A host directory remains acceptable only for local
development and must force all execution-verification claims to false.

At service startup retain a root directory fd and its `statx` identity including
mount id. Before every request:

1. confirm the root fd still identifies the expected immutable mount;
2. open the executable and entrypoint below that fd with `openat2` constraints;
3. compare their metadata and SHA-256 to the signed manifest;
4. retain the executable fd through `execveat`;
5. pass Node the projected Executor path for the measured entrypoint, never the
   unprojected `/app/main.mjs` guest path.

This upgrades the current lexical alignment into execution-time path binding.
Content-addressed mount immutability is what extends that binding to modules
that Node opens later.

### 4.3 Explicit two-root trust statement

For this minimum closure, the ELF interpreter and shared libraries used by Node
remain in the immutable Executor image. The receipt and acceptance evidence must
bind both:

- Executor image digest for launcher, ELF interpreter, and shared libraries;
- runtime image digest plus runtime manifest digest for Node, entrypoint, and
  runtime modules.

This supports a bounded `signed_runtime_path_execution_verified` claim. It does
not support `hostile_runtime_isolation_verified` because absolute runtime reads
can still reach the Executor container root.

## 5. Required Full Guest-Root Closure

The final hostile-isolation gate must replace path projection with a real guest
root. This is the target architecture, not an optional follow-up:

1. Build a complete signed guest root containing Node, its ELF interpreter,
   shared libraries, CA material, entrypoint, modules, and package metadata.
2. Declare mutable mount points for state and workspace in the signed policy.
   Verify each nested mount by mount id, filesystem type, flags, owner, and mode,
   while excluding its mutable contents from the immutable file manifest.
3. Pass a pinned guest-root fd and executable fd to the native launcher.
4. Before uid/gid drop, call `fchdir(root_fd)`, `chroot(".")`, and `chdir("/")`.
   Add only `CAP_SYS_CHROOT`, then clear it with all other capabilities before
   exec. Do not add `CAP_SYS_ADMIN`.
5. Execute Node by fd with the original guest argv
   `[/usr/bin/node, /app/main.mjs, ...]`. Absolute script, loader, library, and
   module paths then resolve inside the same signed guest root.
6. Keep secrets out of the guest filesystem where possible. Pass bounded,
   allowlisted descriptors and close every other fd.

Only this second closure can contribute to the hostile-runtime isolation claim.
It also requires active network, cgroup cleanup, secret non-disclosure, and
namespace escape tests; chroot alone is not the whole isolation proof.

## 6. Required File Changes

Minimum path closure:

- `deploy/byoc/openclaw-runtime-manifest.mjs`: schema revision, signed path model,
  one exported root-anchored resolver, and mount/source identity bindings.
- `deploy/byoc/openclaw-runtime-manifest-contract.mjs`: path projection,
  `openat2` rejection, immutable mount, decoy path, and swap tests.
- `deploy/byoc/openclaw-executor-service.mjs`: retain the verified root fd and
  mount identity; make request-time verification mandatory.
- `deploy/byoc/openclaw-executor-runner.mjs`: consume only resolver-produced fds
  and projected paths.
- `deploy/byoc/compose.openclaw-phase-a07.yaml`: replace the production host bind
  with a content-addressed immutable runtime source.
- `deploy/byoc/Dockerfile`: package or mount the exact runtime layer and record
  both image identities.
- `deploy/byoc/openclaw-phase-a07-image-contract.mjs`: reject host-path runtime
  sources for claim-bearing mode.
- `.github/workflows/openclaw-phase-a07-foundation.yml`: run the real Linux path
  execution and adversarial swap contract.
- a new release-side manifest builder/contract: construct the exact OpenClaw
  runtime artifact, generate its signed manifest, and fail unless regenerating
  from the same OCI digest produces byte-identical metadata and file digests.

Full guest-root closure additionally changes:

- `deploy/byoc/openclaw-runtime-launcher.c`: root-fd argument, chroot sequence,
  fd allowlist, and capability lifecycle.
- `deploy/byoc/openclaw-runtime-launcher-contract.mjs`: real root-only guest-root
  execution, decoy-root, loader, module, uid/gid, capability, and fd tests.
- runtime manifest and Compose policy: complete rootfs and explicit nested mount
  declarations for mutable state/workspace.

## 7. Linux Acceptance Assertions

The minimum closure is not complete until a real Linux job proves all of these:

1. Mount the signed runtime at a randomized path other than `/`; execute it and
   observe the expected provider marker using the runner's default dependencies,
   not injected path/open/spawn substitutes.
2. Place a different executable marker at container `/app/main.mjs`; prove the
   decoy is never opened or executed.
3. Assert `/proc/<pid>/exe` has the same device/inode as the verified executable
   fd and the digest of manifest `usr/bin/node`.
4. Assert the Node entrypoint's resolved path, device/inode, size, mode, owner,
   and digest match manifest `app/main.mjs` below the retained root fd.
5. Swap a parent symlink and replace the runtime path between verification and
   dispatch; require `openat2` failure or execution from the already pinned
   immutable mount, never execution from the replacement.
6. Mutate a module after startup but before dispatch in development host-bind
   mode; require request rejection and all claim booleans false.
7. In claim-bearing OCI-layer mode, prove attempted writes and renames fail from
   both Executor and runtime identities and that the root mount id remains fixed.
8. Record every mapped ELF interpreter and shared library from
   `/proc/<pid>/maps`; bind each to the immutable Executor image evidence for the
   minimum two-root model.
9. Preserve all existing cgroup entry, uid/gid drop, no-new-privileges, seccomp,
   fd-close, timeout, and descendant cleanup assertions.

The full guest-root job must additionally prove that the entrypoint, ELF
interpreter, shared libraries, relative modules, absolute modules, and native
addons all resolve beneath `/` of the signed guest root, while a decoy Executor
root remains unreachable after chroot.

## 8. Claim Boundary

At the audited A07 working tree, the accurate claim state is:

```text
canonical_runtime_manifest_signature_verified = true in contracts/preflight
exact_runtime_tree_snapshot_verified           = true at preflight time
entrypoint_lexically_projected_under_runtime    = true in runner source
real_a07_runtime_artifact_manifested             = false
default_runner_path_execution_tested             = false
runtime_execution_path_bound_to_manifest       = false
runtime_process_spawned                         = false
runtime_receipt_verified                        = false
provider_call_verified                          = false
toctou_resistant_runtime_execution              = false
hostile_runtime_isolation_verified              = false
```

Do not promote `manifest_tree_verified_at_startup` into an execution or
isolation claim. The first new claim allowed after Section 4 passes is the
bounded two-root `signed_runtime_path_execution_verified`. Hostile isolation
remains false until Section 5 and its adversarial acceptance suite pass.
