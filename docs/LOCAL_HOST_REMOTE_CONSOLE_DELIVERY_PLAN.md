# Local Host + Remote Console Delivery Plan

This plan implements `docs/LOCAL_HOST_REMOTE_CONSOLE_SPEC.md` as small,
verifiable slices. It preserves loopback local mode while adding a separate,
fail-closed private-host mode.

The 2026-07-17 transport amendment makes an outbound Relay plus browser pairing
the ordinary Console path. Tailscale Serve remains an advanced fallback and
must not be counted as proof that a non-technical Console user has a zero-install
experience.

## Delivery Rules

- Keep `main` usable after every slice.
- Prefer one independently testable behavior per commit or PR.
- Do not expose the existing Vite development server as the product endpoint.
- Do not weaken live-runtime confirmation or Agent Gateway scope checks.
- Do not read or commit credentials, private messages, full transcripts, raw
  prompts/responses, databases, `.env`, caches, `node_modules`, `dist`, worker
  logs, or generated sample export drift.
- Use real Hermes/OpenClaw evidence for real-runtime acceptance when explicitly
  authorized and available; mock is only the offline/CI fallback and must be
  labeled.
- Continue another safe implementation, verification, docs, or packaging lane
  while builds, CI, live runtimes, or delegated checks are running.

## Lane Board

| Lane | Responsibility | Initial output |
|---|---|---|
| A. Host runtime | Production UI serving, lifecycle, health | same-origin host process |
| B. Human access | Login, session, CSRF, roles, audit | fail-closed browser auth |
| C. Console UX | Pairing, connection/setup/readiness and remote-safe UI | browser-only Relay path |
| G. Relay transport | Outbound Host tunnel, routing, replay safety and privacy | local fake Relay then deployed HTTPS Relay |
| D. Packaging | Bundle, checksums, installer, upgrade/rollback | versioned release asset |
| E. Runtime dogfood | Hermes/OpenClaw host execution and evidence | fresh real task receipt |
| F. Verification | clean-machine, remote-device, security, backup | acceptance packet |

Lanes A and B define the Host security boundary. C and G define the ordinary
remote critical path and can advance against stable API contracts; D can
prepare reproducible packaging in parallel; E and F integrate each usable
slice as it lands.

## Phase 0: Baseline and Contract Freeze

Deliverables:

- record exact branch, commit, CI state, dirty/generated drift, and release
  assets;
- add API/route inventory for the human console and Agent Gateway;
- classify routes as public health, human-session, machine-token, or local-only;
- add a threat-boundary checklist for private host mode;
- freeze the browser/Relay/Host envelope, pairing, replay, reconnect, and
  metadata-retention contracts;
- preserve current loopback one-command acceptance as a regression gate.

Verification:

```bash
git diff --check
python3 scripts/run_local_stack_smoke.py
python3 scripts/v1_5_local_product_acceptance.py --base-url http://127.0.0.1:8787
```

Exit gate: current local mode is green and the new mode has an agreed route and
credential contract.

## Phase 1: Production Host Entrypoint

Deliverables:

- add a production UI build step and same-origin static serving;
- add SPA fallback that excludes `/api/*` and health endpoints;
- add `agentops host init/start/stop/status/doctor` minimum lifecycle;
- keep runtime directories outside the repository with restrictive permissions;
- retain loopback binding by default;
- print redacted local and private-network connection information;
- add host process health and current-code/version evidence.

Verification:

- production UI build passes;
- host starts without `node_modules` at runtime;
- `/`, formal workspace routes, `/api/*`, and health routes resolve correctly;
- Ctrl-C and service stop terminate only owned processes;
- current `run_local_stack.py` behavior remains unchanged.

Exit gate: one host process can serve the production console and API locally.

## Phase 2: Human Session Security

Deliverables:

- add local bootstrap-owner initialization;
- make setup-code-authorized browser bootstrap the primary graphical path by
  handing the code from the managed installer/launcher through an immediately
  scrubbed fragment, while keeping CLI bootstrap for headless/recovery use;
- implement one-time setup code and password/passkey-ready account storage;
- use password hashing from a proven library, not custom cryptography;
- implement expiring/revocable server-side browser sessions;
- add non-enumerating login/pairing errors, attempt limits, cooldowns, bounded
  request bodies, exact Host/Origin validation, and proxy-header rejection;
- add CSRF and allowed-origin checks for state-changing browser requests;
- enforce owner/operator/approver/viewer permissions server-side;
- audit authentication, dispatch, approval, download, and admin actions;
- ensure Agent Gateway machine tokens remain a separate credential class.
- separate Host machine Worker telemetry from both Human Session routes and
  Agent-bound enrollment/Session tokens; rejected reads remain non-mutating.

Verification:

- unauthenticated reads and writes fail closed;
- expired, revoked, cross-workspace, and wrong-role sessions fail;
- CSRF and disallowed-origin smoke tests pass;
- no secret or session value appears in logs, URLs, health, or audit metadata;
- Host CLI Worker status/fleet/readiness/stuck reads succeed with the Host
  machine credential, while Agent-bound tokens fail closed without usage-state
  or ledger mutation;
- loopback developer mode has an explicit, tested compatibility policy.
- no-code Owner bootstrap remains rejected, browser handoff values do not enter
  argv/output/audit/HTTP requests, and concurrent first-owner requests create
  exactly one Owner Session.

Exit gate: a remote browser cannot read workspace data without a valid human
session and cannot perform actions outside its role.

## Phase 3: Browser-Only Remote Console

Deliverables:

- add one-time, expiring, single-use Owner-created Console pairing invitations;
- add paired-device inventory, role binding, last-seen evidence, revocation,
  and immediate Session invalidation;
- add a transport-neutral Host tunnel client, Host-generated TLS identity, and
  deterministic local L4 fake Relay for protocol tests;
- compose that fake Relay with a Host-initiated control connection, one
  Host-initiated data connection per browser session, and real Host-terminated
  TLS before any deployed endpoint work;
- add a deployed HTTPS Relay profile with a stable Console URL, Host-initiated
  connection, per-Host SNI routing, Host-side TLS termination, bounded
  connection metadata, and no authority data store;
- add replay protection, idempotent request correlation, reconnect/resume,
  backpressure, and Relay-unavailable behavior;
- add connection/setup page with host version, workspace, ledger, knowledge,
  worker, and adapter readiness;
- make normal API calls same-origin and remove hard-coded loopback assumptions
  from production UI paths;
- display `mock`, `dry-run`, `live`, `waiting approval`, and `unavailable`
  consistently;
- add session/device revocation and logout;
- ensure reconnecting the browser resumes observation without restarting work.
- retain Tailscale Serve as a separately labeled advanced private-network
  profile with Funnel disabled; do not show it in ordinary onboarding.

Verification:

- second-computer browser acceptance over the deployed Relay using only a
  modern browser;
- no Tailscale, VPN, Python, Node, Git, repository, Hermes, OpenClaw, or
  AgentOps package is installed on the Console computer;
- pairing codes are single-use, expire, are role-scoped, are omitted from
  logs/audit/URLs, and cannot be replayed;
- revoking a paired device invalidates its Human Sessions and blocks reconnect;
- Relay process/storage inspection finds no application plaintext, raw
  prompt/response, knowledge
  body, artifact body, cookie, CSRF value, invitation secret, credential, or
  Host path;
- task dispatch, run observation, approval, evaluation, audit, memory review,
  and approved artifact download work remotely;
- browser disconnect/reconnect does not interrupt the worker.

Exit gate: the second computer is a useful browser-only control console and the
operator never configures or learns a private network.

Implementation slices:

1. `3A Pairing`: schema, local Owner creation, one-time redemption, role scope,
   device/session revocation, audit, and UI.
2. `3B Transport contract`: Host connector interface, per-Host TLS/SNI identity,
   request IDs, replay and idempotency rules, local L4 fake Relay, reconnect tests.
   The bounded frame/replay primitive and a separate raw-proxy Host-only TLS
   fixture are executable in `LOCAL_L4_RELAY_TRANSPORT_ACCEPTANCE.md`. The
   Host-initiated TLS-over-tunnel composition and a disabled-by-default,
   in-process reconnect supervisor are also executable. A protected atomic
   epoch allocator now prevents connector epoch reuse across process crashes.
   An outer certificate-verifying Relay TLS channel plus inner Host-terminated
   application TLS now proves the production mutual-authentication shape
   locally. A strict disabled-by-default foreground connector process now owns
   reconnect/status/epoch lifecycle, loopback Host TLS termination, exact Host
   SNI rejection, HTTP forwarding and clean signal shutdown. Host
   initialization now creates an exact private disabled config, and Host
   status/doctor expose a bounded fail-closed connector projection without
   reading secrets. The source Host stack now starts exactly one connector child
   only for an explicitly enabled, valid private configuration; disabled or
   unconfigured state starts none, and stop/restart own its cleanup without
   changing Tailscale. Owner enable/disable controls, fresh runtime-status
   projection, certificate lifecycle, Relay-side SNI routing, credential
   provisioning, installation into the current preview, and the deployed Relay
   remain open.
3. `3C Deployed Relay`: L4 endpoint, DNS/ACME provisioning, stable per-Host
   Console origin, bounded operations metadata, deployment and rollback.
4. `3D Physical acceptance`: fresh browser-only device, real Hermes/OpenClaw
   run, disconnect/reconnect, approval, memory, artifact and logout receipt.

## Phase 4: Packaging and Lifecycle

Deliverables:

- build a versioned macOS host bundle/installer;
- install a managed user-level `AgentOps MIS.app` launcher that opens the same
  browser Workspace and never starts live workers implicitly;
- include production UI assets and Python application without local project
  data;
- include the disabled-by-default Relay connector and make **Enable remote
  Console** an explicit Owner action; do not require a separately installed
  network client;
- provide checksums, provenance, SBOM, third-party notices, uninstall, backup,
  restore, and upgrade instructions;
- add preview-first background service installation;
- reject duplicate same-adapter Worker ownership before Host startup while
  preserving an explicit `--no-workers` external-owner mode;
- implement update check, pre-migration backup, migration verification, and
  rollback instructions;
- publish actual GitHub Release assets rather than relying only on automatic
  source archives.

Verification:

- clean macOS account or VM install;
- install path contains no source-machine DB, token, config, cache, log, or
  dependency dump;
- service survives logout/reboot when explicitly installed;
- duplicate Worker ownership fails closed without opening the Host port or
  terminating the existing process;
- upgrade preserves ledger/knowledge and rollback is exercised;
- checksum and exact-commit provenance validation pass.

Exit gate: another host computer can install and operate the private-host
product without a manual repository setup.

## Phase 5: Real Runtime Closure

Deliverables:

- provide host-only Hermes/OpenClaw prerequisite checks and guided remediation;
- do not auto-install or enable runtimes in this phase;
- expose adapter readiness without exposing runtime credentials;
- execute one fresh, explicitly confirmed customer-style task through Hermes;
- execute one fresh, explicitly confirmed customer-style task through OpenClaw;
- verify task, plan, run, runtime events, tool calls, evaluations, artifacts,
  approvals where required, memories where proposed, and audit evidence;
- show the same evidence from the remote console.

Verification:

- real runtime health is distinguishable from mock readiness;
- failed or unavailable runtime produces bounded failure evidence rather than a
  false success;
- raw prompt/response and credentials are absent from ledger, logs, artifacts,
  screenshots, and commits;
- live mode cannot start without explicit operator confirmation.

Exit gate: the product demonstrates real host-side AI work controlled from the
second computer.

## Phase 6: Release Candidate Acceptance

Run the complete acceptance matrix:

- local workstation regression;
- private host startup and shutdown;
- human auth/session/role/CSRF/origin tests;
- browser-only Relay second-device workflow;
- Tailscale advanced-mode regression with Funnel disabled;
- worker persistence during console disconnect;
- real Hermes and OpenClaw receipts when authorized;
- backup, restore, migration, rollback, and clean uninstall;
- UI build and core Python smoke suites;
- `git diff --check` and artifact/secret scan;
- exact-head CI and release provenance.

Create an acceptance document containing commands, results, limitations, exact
commit, release URL, checksums, and fresh evidence IDs. Do not cite stale demo
run IDs as current proof.

## Definition of Done

The goal is complete only when:

1. The host installs from a real versioned asset and starts through a product
   command rather than repository-specific manual steps.
2. A second computer requires only a modern browser; ordinary onboarding does
   not install or explain Tailscale, a VPN client, or development dependencies.
3. Human authentication and role enforcement protect all workspace data and
   state-changing actions.
4. Ledger, knowledge, project files, secrets, and Agent execution remain on the
   host by default.
5. A remote operator completes the customer task closed loop and sees bounded
   evidence from a fresh real Hermes/OpenClaw run.
6. Local mode remains safe and usable.
7. Clean-machine, backup/restore, disconnect/reconnect, security, and release
   acceptance pass at the exact release commit.

## Deferred Work

- automatic Hermes/OpenClaw/model installation;
- full hosted MIS authority storage, SaaS multi-tenancy, and billing;
- enterprise SSO and complete enterprise RBAC;
- mobile/native desktop console;
- Notion/Dify live synchronization;
- billing, licensing, and customer provisioning.

These items may be planned in parallel but cannot be used to delay or dilute
the private local-host product closure.
