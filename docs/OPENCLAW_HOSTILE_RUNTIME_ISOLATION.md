# OpenClaw Hostile Runtime Isolation

Status: engineering specification under implementation. The default customer
release remains on the two-service A01/A02 topology. The three-service A03
candidate in `deploy/byoc/compose.openclaw-phase-a03.yaml` passed its exact-image
Linux path-isolation gate at source commit
`6c37c47e16f6a4e4327372960c58144744af5721`. That proves the bounded A03 mount
and DAC claims only. The source-only A04/A05 successor lives in
`deploy/byoc/compose.openclaw-phase-a04-a05.yaml` and adds Linux `SO_PEERCRED`
gates in front of both Node.js protocol services. It earns no A04/A05 claim
until its own exact-image Linux attack workflow passes. Neither candidate is the
default customer topology, and this document is not evidence that the complete
hostile-runtime boundary is implemented.

## 1. Security Claims At The Current Baseline

The current two-service topology must not claim hostile-runtime isolation.

- `worker-openclaw` runs as uid/gid `1000:1000`.
- `openclaw-provider` runs its HTTP-over-UDS broker and the mounted OpenClaw
  runtime as uid `1001`, so a hostile runtime has the broker's OS authority.
- The shared socket directory is owned by `1001:1000` with mode `0750`; the
  Provider mounts it read-write and the Worker mounts it read-only. This is the
  implemented A01/A02 candidate and must pass the real mutation acceptance.
- The broker mounts the runtime, OpenClaw config, state, and workspace.
- `OPENCLAW_BIN_SHA256` binds one regular entrypoint file, not the complete
  executable and dependency tree.
- OpenClaw accepts the prompt only through `--message`. The raw prompt is
  observable in process argv by a sufficiently privileged local observer while
  the runtime is active.
- `provider_call_performed=true` proves only that the local adapter reports a
  runtime launch. It is neither a signed local execution receipt nor proof that
  a remote model Provider received the request.

Until Phase A passes every mandatory acceptance below, the default release's
maximum claim is credential separation between the Worker and the current
provider container. The A03 exact-image evidence additionally proves Worker
mount/path separation for that candidate. The A04/A05 candidate may set the
individual public and private peer-credential fields only after active Linux
wrong-uid probes pass. Both candidates must keep
`runtime_receipt_verified=false` and `hostile_runtime_isolation_verified=false`.
The A03 receipt must additionally keep `so_peercred_verified=false`.
Even after Phase A passes, the release metadata must state:

```text
runtime_isolation_verified=true
argv_confidentiality=false
provider_call_verified=false
```

No fake CLI, local process exit, local executor signature, model-shaped JSON, or
operator assertion may set `provider_call_verified=true`.

## 2. Threat Model And Invariants

Treat each of these as independently hostile after startup:

- a compromised TypeScript Worker;
- a compromised Broker;
- the mounted OpenClaw runtime and every dependency it loads;
- malformed, replayed, delayed, oversized, or interrupted UDS traffic;
- mutable customer mounts and a local user who can replace their contents;
- runtime descendants that fork, ignore signals, or continue after timeout.

The container engine, Linux kernel, immutable AgentOps image, deployment
manifest, Executor code, Executor signing key, and configured trust roots remain
in the trusted computing base. Host root is outside this isolation guarantee.

The following invariants are release gates:

1. Worker compromise cannot replace either UDS endpoint or obtain runtime,
   Provider, Executor, database, or Human-session credentials.
2. Broker compromise cannot read or execute the mounted runtime and cannot join
   either the control-plane or Provider-egress network.
3. Runtime compromise cannot reach the Worker token, control plane, public or
   private UDS, Executor signing key, or another execution's cgroup/state.
4. Only the Executor can start a measured runtime, and every runtime starts as
   uid/gid `1200:1200` with empty supplementary groups and capabilities.
5. Runtime success is not accepted until a signature and all request, runtime,
   result, deadline, and isolation bindings in the Executor receipt verify.
6. Remote Provider use is an independent evidence claim and remains false
   without evidence signed by, or cryptographically anchored to, that Provider.

## 3. Phase A: Three Services And Four Identities

Phase A requires three services and four distinct OS identities:

| Service | Persistent identity | Purpose |
| --- | --- | --- |
| `worker-openclaw` | `1000:1000`, supplementary gid `2100` | Claims governed work, connects only to the public UDS, writes control-plane evidence. |
| `openclaw-broker` | `1100:1100`, supplementary gids `2100,2200` | Validates the Worker protocol, forwards one bounded request to the private UDS, verifies Executor receipts. |
| `openclaw-executor` PID 1 | `0:2200` with only `SETUID`, `SETGID`, `KILL` | Verifies runtime identity, owns the private UDS and signing key, creates execution cgroups, and supervises runtime descendants. |
| OpenClaw child | `1200:1200`, no supplementary groups | Executes the measured OpenClaw runtime with Provider egress and runtime-only mounts. |

The Executor and runtime are two identities in one service. The root Executor
must never execute OpenClaw logic in its own process and must not parse model
output beyond bounded framing and hashing.

### 3.1 Public UDS

Use `/run/agentops-openclaw-public` as a dedicated tmpfs volume.

```text
directory  uid=1100 gid=2100 mode=0750
socket     uid=1100 gid=2100 mode=0660
path       /run/agentops-openclaw-public/broker.sock
```

- Broker mounts the volume read-write and creates the socket atomically.
- Worker mounts the volume read-only and receives supplementary gid `2100`.
- Group `2100` may traverse the directory and connect to the socket, but has no
  directory write bit. The Worker must receive `EACCES`, `EPERM`, or `EROFS` for
  unlink, rename, hard-link, symlink, mkdir, and bind attempts.
- Broker must reject a connection unless Linux `SO_PEERCRED` reports uid `1000`.
  The expected pid and gid are recorded for diagnostics but uid is the mandatory
  authorization field.
- Startup fails if the directory owner/mode, mount read-only state in Worker, or
  existing socket type/owner/mode differs from this contract. No stale socket is
  adopted.

### 3.2 Private UDS

Use `/run/agentops-openclaw-private` as a separate tmpfs volume.

```text
directory  uid=0 gid=2200 mode=0750
socket     uid=0 gid=2200 mode=0660
path       /run/agentops-openclaw-private/executor.sock
```

- Executor mounts the volume read-write and owns the directory and socket.
- Broker mounts it read-only and receives supplementary gid `2200` only for
  traversal and socket connection.
- Worker does not mount this volume.
- Runtime uid/gid `1200:1200` has neither a mount path nor a traversable group.
- Executor rejects a connection unless `SO_PEERCRED` reports uid `1100`.
- Broker cannot unlink, rename, or rebind the private socket. Executor never
  accepts request traffic from uid `1000` or `1200`.

`SO_PEERCRED` checks are required in the production implementation and in a
real Linux acceptance test. Source-text assertions and macOS-only tests do not
satisfy this gate.

### 3.3 Mount And Secret Matrix

An omitted mount means the path must be absent, not merely unreadable.

| Resource | Worker | Broker | Executor PID 1 | Runtime child |
| --- | --- | --- | --- | --- |
| Public UDS volume | read-only | read-write | absent | absent |
| Private UDS volume | absent | read-only | read-write | no traversable path |
| Agent token | read-only secret | absent | absent | absent |
| Control-plane CA/config | read-only | absent | absent | absent |
| OpenClaw runtime root | absent | absent | read-only for verification | read-only for execution |
| OpenClaw config/Provider credential | absent | absent from Executor logic | descriptor prepared for child only | read-only descriptor or secret |
| OpenClaw workspace | absent | absent | read-only mount | read-only mount |
| Runtime state | absent | absent | lifecycle-managed | private tmpfs owned by `1200:1200` |
| Delegated cgroup v2 subtree | absent | absent | read-write, uid `0`, mode `0700` | entered before uid drop; no writable controller path |
| Executor signing private key | absent | absent | read-only, uid `0`, mode `0400` | inaccessible |
| Executor signing public key | pinned verifier | pinned verifier | read-only | absent |

The Executor must pass an allowlist of descriptors to the child and close every
other descriptor before exec. Provider credentials must not appear in argv,
environment, receipts, health output, or logs. Where the current OpenClaw
interface requires a config path, expose a runtime-only `/proc/self/fd/<n>` path
or a runtime-owned `0400` secret mount; never mount that secret into Broker.

### 3.4 Network Boundary

- Worker joins only `control_plane`; its network policy permits the configured
  MIS HTTPS origin and required DNS/CA endpoints. It has no Provider egress.
- Broker uses `network_mode: none`. It communicates exclusively over the two
  UDS volumes and has no host port.
- Executor/runtime joins only `openclaw_provider_egress`; it has no route or DNS
  resolution to `control_plane`, PostgreSQL, MIS, Docker API, cloud metadata, or
  host gateway addresses.
- Provider egress is enforced by an external firewall or egress proxy allowlist,
  not by a Docker network name alone. The allowlist is versioned deployment
  input and defaults to deny.
- No service mounts `/var/run/docker.sock`, the host network namespace, host PID
  namespace, or a writable host path.

The acceptance environment must capture denied connection attempts from each
identity. A topology inspection without active connection tests is insufficient.

### 3.5 Executor Launch Sequence

The host or container supervisor delegates exactly one cgroup v2 subtree at
`/sys/fs/cgroup/agentops-openclaw-executor`. Executor sees that subtree
read-write as uid `0`, mode `0700`; it does not receive the host cgroup root or
another service's subtree. Required controllers are enabled before container
startup. Runtime enters its request cgroup before uid drop and cannot traverse
or write controller files afterward. Missing cgroup v2, controller delegation,
or writable limits makes Executor readiness fail; the service never falls back
to process-group-only cleanup.

For every request the Executor performs this exact fail-closed sequence:

1. Read one length-bounded canonical request from an authenticated Broker peer.
2. Validate schema, request id, nonce, prompt SHA-256, absolute monotonic
   deadline, agent allowlist, and maximum prompt size. Reject reused nonces.
3. Verify the signed runtime manifest and remeasure every declared runtime file
   using descriptor-relative, `O_NOFOLLOW` opens. Reject missing, extra,
   non-regular, writable, owner/mode-drifted, or digest-mismatched files.
4. Create a request-specific cgroup with configured `pids.max`, `memory.max`,
   `memory.swap.max=0`, `cpu.max`, and bounded I/O. Record its stable id.
5. Fork without a shell. In the child: enter the cgroup and private process
   group; clear supplementary groups; call `setresgid(1200,1200,1200)` and
   `setresuid(1200,1200,1200)`; set `PR_SET_NO_NEW_PRIVS`; clear all permitted,
   effective, inheritable, and ambient capabilities; install the runtime seccomp
   profile; close all non-allowlisted descriptors; then exec a fixed absolute
   argv template.
6. In the parent: close child-only descriptors, enforce the monotonic deadline,
   collect bounded stdout/stderr through pipes, hash raw output without storing
   it, and never return raw stderr.
7. On cancellation, timeout, Broker disconnect, Executor shutdown, malformed
   output, or receipt-write failure: signal the complete cgroup, wait a bounded
   grace interval, send `SIGKILL`, and verify `cgroup.events populated=0` before
   reporting cleanup complete.
8. Sign and return the local execution receipt. Delete request state only after
   the signed receipt is durably handed to Broker or an explicit reconciliation
   record is written.

Executor PID 1 runs as `0:2200`, with `no-new-privileges` and only Linux
capabilities `SETUID`, `SETGID`, and `KILL`. Its root filesystem is read-only;
`/tmp` and runtime state are bounded `noexec,nosuid,nodev` tmpfs mounts. Directory
ownership must be supplied by image build or tmpfs mount options so `CHOWN`,
`DAC_OVERRIDE`, `SYS_ADMIN`, `SYS_PTRACE`, and `NET_ADMIN` are not needed.

The seccomp profile must deny at least `mount`, `umount2`, `pivot_root`,
`setns`, `unshare`, `ptrace`, `bpf`, `perf_event_open`, `keyctl`, module loading,
raw sockets, and device creation. Runtime file descriptors, process count,
address space, core dumps, and output bytes also receive explicit rlimits.

### 3.6 Complete Runtime Manifest

Entry-file SHA-256 is retained as a diagnostic but is not the trust root. Each
release supplies a canonical, signed `agentops_openclaw_runtime_manifest_v1`
containing:

- immutable OCI image name and digest;
- OpenClaw version and absolute entrypoint;
- Node/runtime executable path, size, owner, mode, and SHA-256;
- every executable, JavaScript module, package manifest, lockfile, native addon,
  shared library, and loader reachable from the entrypoint, each with normalized
  path, type, size, owner, mode, and SHA-256;
- an allowlist of runtime-created paths, all confined to runtime state tmpfs;
- fixed argv template, environment-name allowlist, seccomp profile digest,
  cgroup policy digest, and expected runtime uid/gid;
- manifest issuer, key id, creation time, expiry policy, and Ed25519 signature.

Manifest generation fails on symlinks, hard links escaping the runtime root,
special files, writable measured files, duplicate normalized paths, undeclared
executables, or path traversal. Executor verification fails if the mounted tree
contains an undeclared regular file in a measured directory. The manifest trust
root is pinned in the immutable AgentOps image and rotated through a documented
dual-key release, never through customer runtime input.

### 3.7 Locally Signed Execution Receipt

Executor signs canonical bytes for
`agentops_openclaw_runtime_receipt_v1`. The signed body contains at least:

```text
receipt_id, request_id, workspace_id_hash, run_id, nonce
prompt_sha256, result_sha256, runtime_manifest_sha256
executor_image_digest, executor_key_id, runtime_uid, runtime_gid
public_peer_uid, private_peer_uid, cgroup_id, isolation_policy_sha256
started_monotonic_ns, finished_monotonic_ns, deadline_monotonic_ns
exit_kind, exit_code, termination_signal, descendants_cleanup_verified
runtime_process_spawned, argv_confidentiality, provider_call_verified
```

The private Ed25519 key is mounted `0400` for Executor PID 1 and is unreadable by
uid `1200`. Broker and control plane pin the public key and reject unknown key
ids, non-canonical encoding, invalid signatures, request/nonce/hash mismatch,
expired deadlines, replayed receipt ids, wrong manifest/policy digest, missing
descendant cleanup, or unexpected uid/gid.

This signature proves execution by the trusted local Executor under the bound
manifest and isolation policy. It does not prove a remote Provider call.

## 4. Phase B: Prompt FD And FD RPC

Phase B requires an upstream OpenClaw interface that removes the prompt from
argv. The minimum compatible CLI is:

```bash
openclaw agent --message-fd 3 --request-id <id> --json
```

The preferred long-term transport is an inherited `SOCK_SEQPACKET` RPC
descriptor with separate data and control message types. In either form:

- argv contains only fixed flags, request id, and non-secret protocol version;
- prompt bytes travel through an anonymous pipe or socketpair inherited as fd 3;
- the first framed message binds schema, request id, nonce, prompt length,
  `prompt_sha256`, and monotonic deadline;
- runtime acknowledges the same nonce and prompt hash before execution;
- every response frame binds request id, nonce, prompt hash, sequence number,
  final-result hash, and terminal status;
- a `CANCEL` control frame binds request id and nonce. EOF, deadline expiry, or
  invalid framing has identical cancellation semantics;
- Executor closes the prompt descriptor immediately after bounded delivery and
  never writes prompt bytes to disk, environment, argv, log, health output,
  receipt, crash report, or error text;
- timeout/cancel still terminates and empties the complete request cgroup;
- replayed nonce, response hash mismatch, response after terminal state, and
  frames after deadline fail closed and require reconciliation if execution may
  have started.

Phase B acceptance scans `/proc/*/cmdline`, `/proc/*/environ`, container inspect
output, logs, receipts, temporary files, and committed evidence for unique prompt
canaries while the real runtime is active. Only after those live tests pass may
`argv_confidentiality=true` be signed into a receipt.

Remote Provider proof is separate. `provider_call_verified=true` requires a
Provider- or Gateway-signed statement binding request id, nonce, model identity,
usage, prompt hash or privacy-preserving request commitment, output hash, and
completion time. An Executor signature alone never satisfies this condition.

## 5. Evidence Field Migration

Replace the overloaded success signal with three independent booleans:

| Field | Set true only when | Authority |
| --- | --- | --- |
| `runtime_process_spawned` | Executor successfully execs the measured child as uid/gid `1200:1200` inside the bound cgroup. | Executor observation; trustworthy only inside a verified receipt. |
| `runtime_receipt_verified` | Broker/control plane verifies the Executor signature and every request, manifest, policy, deadline, result, and cleanup binding. | Broker/control plane verifier. |
| `provider_call_verified` | A configured remote Provider trust root verifies Provider/Gateway evidence bound to this execution. | Remote Provider/Gateway verifier. |

Rules:

- Persist all three fields on runtime, Tool, Evaluation, Audit, reconciliation,
  and release-status evidence. Omission is false; unknown schema fails closed.
- A successful Phase A run requires `runtime_process_spawned=true` and
  `runtime_receipt_verified=true`, while `provider_call_verified=false` remains
  expected and must not block local-execution acceptance.
- `provider_call_performed` is deprecated. During one additive-schema migration
  window it may mirror `runtime_process_spawned` for old readers, but it must
  never be interpreted or displayed as `provider_call_verified`.
- If transport fails after dispatch, record an explicit uncertain outcome and
  require manual reconciliation. Never infer false merely because no receipt
  returned, and never retry an uncertain execution automatically.
- Mock and fake-runtime tests must force `provider_call_verified=false`.

## 6. Mandatory Attack Acceptance Matrix

All Phase A rows run on real Linux with the production container topology. Each
test must record exact image digests, manifest/policy digests, identity, denied
operation, exit status, cleanup state, and secret/canary scan result.

| ID | Attacker/action | Required result | Phase |
| --- | --- | --- | --- |
| A01 | Worker unlinks or renames public `broker.sock`. | Denied by directory DAC and read-only mount; original inode remains connected. | A |
| A02 | Worker binds a replacement socket or inserts symlink/hard link. | Denied; Broker inode/owner/mode unchanged; health remains bound to original listener. | A |
| A03 | Worker opens private UDS or runtime/config/signing paths. | Paths absent or traversal denied. | A |
| A04 | Process with uid other than `1000` connects to public UDS. | Broker rejects using `SO_PEERCRED` before reading a request body. | A |
| A05 | Fake Broker uid connects to private UDS. | Executor rejects any peer uid other than `1100`. | A |
| A06 | Broker lists or opens runtime, workspace, Provider config, Agent token, or signing key. | Paths absent; mount inspection confirms no source mount. | A |
| A07 | Runtime opens either UDS, Agent token, control-plane config, or signing key. | Paths absent or `EACCES`; no secret canary appears in runtime output. | A |
| A08 | Runtime connects to MIS, PostgreSQL, Docker API, metadata IP, host gateway, or non-allowlisted Internet host. | Connection and DNS resolution denied; Provider allowlisted endpoint remains reachable. | A |
| A09 | Entrypoint, dependency, native addon, loader, or manifest is modified after startup. | Pre-exec remeasurement rejects launch; `runtime_process_spawned=false`. | A |
| A10 | Runtime tree adds undeclared executable/module, symlink, FIFO, device, or escaping hard link. | Manifest verification rejects launch. | A |
| A11 | Runtime tries privilege regain, namespace creation, mount, ptrace, raw socket, or forbidden syscall. | Capability/seccomp/no-new-privileges boundary denies it; uid remains `1200`. | A |
| A12 | Runtime forks indefinitely or ignores TERM. | `pids.max` contains it; timeout kills the full cgroup and verifies `populated=0`. | A |
| A13 | Runtime exceeds memory, CPU, output, file, or deadline budget. | Bounded failure receipt; full cgroup cleanup; no unbounded logs or buffers. | A |
| A14 | Concurrent/slow/oversized/interrupted requests race the Broker or Executor. | Atomic single-flight or configured bounded concurrency; slots release; no duplicate launch. | A |
| A15 | Receipt body, signature, nonce, request id, prompt/result hash, manifest digest, policy digest, uid, deadline, or cleanup flag is altered. | Verification fails; `runtime_receipt_verified=false`; no success evidence. | A |
| A16 | A valid signed receipt is replayed. | Receipt id and nonce replay cache rejects it without another launch. | A |
| A17 | Fake CLI returns plausible model JSON and exit code 0. | Local receipt may prove measured fake execution only; `provider_call_verified=false`. | A |
| A18 | Broker disconnects or Executor receives TERM during execution. | Cancellation reaches the request cgroup; descendants are empty before shutdown success. | A |
| A19 | Unique Agent-token, signing-key, database, and Human-session canaries are scanned across all outputs and files. | Zero disclosure; only approved hash fields exist. | A |
| B01 | Unique prompt canary is inspected live in argv and environment. | Absent from all `/proc/*/cmdline` and `/proc/*/environ` entries. | B |
| B02 | Prompt canary is scanned in logs, temp files, state, receipts, crash output, and committed evidence. | Zero disclosure; only `prompt_sha256` is retained. | B |
| B03 | FD frame nonce/hash/length is altered, replayed, reordered, duplicated, or sent after deadline. | Protocol fails closed; no success receipt; uncertain starts require reconciliation. | B |
| B04 | Cancel is sent before delivery, during execution, and after terminal response. | Correct idempotent state transition; active cgroup empties; no second result is accepted. | B |
| B05 | Local runtime or Executor claims Provider success without valid remote evidence. | `provider_call_verified=false`; promotion/status code rejects any stronger claim. | B |
| B06 | Valid Provider evidence is rebound to another request, nonce, model, prompt commitment, result, or time. | Provider proof verification fails. | B |

The release gate requires every applicable row to pass repeatedly under parallel
load and once during forced container shutdown. A source grep or mocked Docker
configuration is supplemental evidence only.

## 7. Migration And Rollback Order

### 7.1 Phase A rollout

1. Add the three evidence columns and uncertain-outcome state through an
   additive PostgreSQL migration. Deploy readers that understand both old and
   new schemas; keep `provider_call_performed` as a deprecated compatibility
   field only.
2. Build and pin Broker and Executor images, runtime manifest trust roots,
   Executor receipt public keys, seccomp/cgroup policies, UDS tmpfs ownership,
   network deny rules, and mount allowlists. Keep production traffic on the old
   topology.
3. Run A01-A19 against synthetic and fake runtimes. Then run exact-image real
   OpenClaw acceptance with `runtime_process_spawned=true`,
   `runtime_receipt_verified=true`, and `provider_call_verified=false`.
4. Start Broker and Executor in dark mode. Health checks must verify peer-cred
   support, socket inode/owner/mode, manifest trust root, receipt key id, cgroup
   controller availability, seccomp load, and network deny policy before ready.
5. Drain one Worker, switch only that Worker to the public Broker socket, and run
   one bounded canary task. Do not duplicate a live prompt through both paths.
6. Increase traffic by explicit workspace cohort. Promotion requires no
   uncertain executions, valid signed receipts, complete cleanup, and all attack
   gates on the exact images.
7. After the retention window, remove the old combined provider service and
   reject deployments that lack the three-field evidence schema. Preserve old
   receipts as historical, weaker evidence.

### 7.2 Phase B rollout

1. Release a separately versioned OpenClaw runtime implementing `--message-fd`
   or the FD RPC and include that interface in the signed runtime manifest.
2. Deploy Executor support behind an explicit per-runtime protocol version. Run
   B01-B06 with synthetic canaries and a real runtime while Phase A remains the
   default.
3. Canary one drained Worker cohort. Require live argv/environment inspection,
   prompt-omission scans, nonce/deadline/cancel bindings, and cgroup cleanup.
4. Promote cohorts, then reject `--message` runtimes for configurations claiming
   `argv_confidentiality=true`.
5. Remove Phase A prompt-in-argv support only after all supported runtime versions
   implement FD transport and rollback artifacts have been retained.

### 7.3 Rollback

- Rollback is explicit and cohort-scoped; no component automatically falls back
  to the old combined provider or direct Worker execution.
- Stop new claims, drain active requests, reconcile every request without a
  verified terminal receipt, and revoke the affected readiness lease before
  changing topology.
- Phase A code can roll back to the previous image because the database migration
  is additive. The deployment must immediately downgrade its claims to
  `runtime_isolation_verified=false`, `runtime_receipt_verified=false`,
  `argv_confidentiality=false`, and `provider_call_verified=false`.
- Phase B may roll back to a previously accepted Phase A runtime only through an
  operator setting that visibly restores `argv_confidentiality=false`. It must
  not rewrite or reinterpret prior receipts.
- Never retry a request whose Provider or runtime completion is uncertain. Human
  reconciliation must resolve it by request id, nonce, receipt id, and immutable
  evidence before a replacement task is issued.
- Retain the last known-good images, manifests, receipt public keys, schema
  reader, and policy digests. Private signing keys are rotated or revoked, never
  copied into a rollback bundle.

## 8. Definition Of Done

Phase A is complete only when the production Compose/release bundle implements
the identities and boundaries above, A01-A19 pass against its exact immutable
images, real OpenClaw produces a verified local receipt, and product/status UI
does not imply remote Provider proof. Its honest terminal claim remains:

```text
runtime_process_spawned=true
runtime_receipt_verified=true
runtime_isolation_verified=true
argv_confidentiality=false
provider_call_verified=false
```

Phase B is complete only when B01-B06 pass with the FD interface on the exact
runtime manifest and live prompt-canary scans prove argv/environment omission.
`provider_call_verified` remains independently false unless the configured
remote Provider/Gateway evidence verifies against its own pinned trust root.
