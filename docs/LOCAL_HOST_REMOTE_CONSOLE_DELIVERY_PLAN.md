# Local Host + Remote Console Delivery Plan

This plan implements `docs/LOCAL_HOST_REMOTE_CONSOLE_SPEC.md` as small,
verifiable slices. It preserves loopback local mode while adding a separate,
fail-closed private-host mode.

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
| C. Console UX | Connection/setup/readiness and remote-safe UI | zero-install browser path |
| D. Packaging | Bundle, checksums, installer, upgrade/rollback | versioned release asset |
| E. Runtime dogfood | Hermes/OpenClaw host execution and evidence | fresh real task receipt |
| F. Verification | clean-machine, remote-device, security, backup | acceptance packet |

Lanes A and B define the critical path. C can begin against stable API contracts;
D can prepare reproducible packaging in parallel; E and F integrate each usable
slice as it lands.

## Phase 0: Baseline and Contract Freeze

Deliverables:

- record exact branch, commit, CI state, dirty/generated drift, and release
  assets;
- add API/route inventory for the human console and Agent Gateway;
- classify routes as public health, human-session, machine-token, or local-only;
- add a threat-boundary checklist for private host mode;
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
- implement one-time setup code and password/passkey-ready account storage;
- use password hashing from a proven library, not custom cryptography;
- implement expiring/revocable server-side browser sessions;
- add CSRF and allowed-origin checks for state-changing browser requests;
- enforce owner/operator/approver/viewer permissions server-side;
- audit authentication, dispatch, approval, download, and admin actions;
- ensure Agent Gateway machine tokens remain a separate credential class.

Verification:

- unauthenticated reads and writes fail closed;
- expired, revoked, cross-workspace, and wrong-role sessions fail;
- CSRF and disallowed-origin smoke tests pass;
- no secret or session value appears in logs, URLs, health, or audit metadata;
- loopback developer mode has an explicit, tested compatibility policy.

Exit gate: a remote browser cannot read workspace data without a valid human
session and cannot perform actions outside its role.

## Phase 3: Private-Network Console

Deliverables:

- add Tailscale Serve setup/status guidance and a copyable console URL;
- add connection/setup page with host version, workspace, ledger, knowledge,
  worker, and adapter readiness;
- make normal API calls same-origin and remove hard-coded loopback assumptions
  from production UI paths;
- display `mock`, `dry-run`, `live`, `waiting approval`, and `unavailable`
  consistently;
- add session/device revocation and logout;
- ensure reconnecting the browser resumes observation without restarting work.

Verification:

- second-computer browser acceptance over the private network;
- no Python, Node, Git, repository, Hermes, or OpenClaw is installed on the
  console computer;
- task dispatch, run observation, approval, evaluation, audit, memory review,
  and approved artifact download work remotely;
- browser disconnect/reconnect does not interrupt the worker.

Exit gate: the second computer is a useful zero-install control console.

## Phase 4: Packaging and Lifecycle

Deliverables:

- build a versioned macOS host bundle/installer;
- include production UI assets and Python application without local project
  data;
- provide checksums, provenance, SBOM, third-party notices, uninstall, backup,
  restore, and upgrade instructions;
- add preview-first background service installation;
- implement update check, pre-migration backup, migration verification, and
  rollback instructions;
- publish actual GitHub Release assets rather than relying only on automatic
  source archives.

Verification:

- clean macOS account or VM install;
- install path contains no source-machine DB, token, config, cache, log, or
  dependency dump;
- service survives logout/reboot when explicitly installed;
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
- private-network second-device workflow;
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
2. A second computer requires only a browser and private-network access.
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
- public hosted SaaS and multi-tenancy;
- enterprise SSO and complete enterprise RBAC;
- mobile/native desktop console;
- Notion/Dify live synchronization;
- billing, licensing, and customer provisioning.

These items may be planned in parallel but cannot be used to delay or dilute
the private local-host product closure.

