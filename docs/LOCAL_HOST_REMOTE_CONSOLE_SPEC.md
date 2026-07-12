# AgentOps MIS Local Host + Remote Console Product Spec

Status: proposed implementation baseline  
Target: v1.6 local private host  
Scope: single-owner or trusted small-team deployment

## 1. Product Goal

Turn AgentOps MIS into a two-surface local product:

- one trusted computer runs the MIS control plane, SQLite ledger, knowledge
  index, project files, Hermes/OpenClaw adapters, and worker daemons;
- another computer uses a zero-install browser console to create tasks,
  supervise work, approve actions, review evidence, and download approved
  deliverables.

The remote console is not an Agent runtime and does not receive the host's
model credentials, knowledge corpus, database, raw prompts, or raw responses.

## 2. Current Baseline

The current `v1.0.0-local` release provides a source release and a foreground
one-command local stack. It is suitable for a developer-operated loopback
installation, but it is not yet a consumer installer or remote-console product.

Known baseline constraints:

- `scripts/run_local_stack.py` intentionally rejects a non-loopback backend;
- the beta React UI is run through the Vite development server;
- non-loopback backend mode has a fail-closed API/admin-key gate, but there is
  no complete human browser login/session flow;
- the GitHub release currently has no packaged `.dmg`, `.pkg`, `.zip`, or
  signed installer asset;
- Hermes/OpenClaw installation and model provisioning remain host-side manual
  prerequisites.

These constraints must not be bypassed by simply binding the current developer
stack to `0.0.0.0`.

## 3. Deployment Model

```text
Remote browser console
  -> private encrypted network / HTTPS
  -> AgentOps MIS host entrypoint
       -> human session and authorization
       -> Python control plane and Agent Gateway
       -> SQLite authority ledger
       -> Markdown + FTS knowledge index
       -> artifact store
       -> Hermes/OpenClaw worker daemons
```

### Host computer

The host owns and executes:

- workspace, actor, task, run, tool-call, approval, evaluation, memory, and
  audit state;
- local knowledge documents and indexes;
- project working directories and approved artifacts;
- runtime connectors, worker processes, runtime credentials, and secrets;
- backup, restore, retention, and update operations.

### Console computer

The console may:

- sign in and select an authorized workspace;
- create, edit, dispatch, pause, cancel, and review tasks;
- select an available team template or runtime adapter;
- observe workers, jobs, runs, events, evaluations, and health;
- approve or reject prepared actions, memories, and deliverables;
- download explicitly approved artifacts and reports.

The console must not:

- run Hermes/OpenClaw merely by loading the page;
- receive runtime API keys, enrollment tokens, database files, or unrestricted
  filesystem paths;
- read raw prompts, raw responses, private messages, or full transcripts;
- directly mutate the ledger outside authenticated MIS APIs;
- become an alternative authority store.

## 4. Product Modes

### Local workstation mode

- Default mode.
- Binds to loopback only.
- Preserves the current safe mock/live-confirmation behavior.
- Does not require remote access configuration.

### Private host mode

- Explicit opt-in through a separate `agentops host` command or equivalent
  launcher profile.
- Serves the production-built React console and APIs from one origin.
- Remains loopback behind a recommended private-network proxy when possible.
- Requires human authentication before any workspace data is returned.
- Requires explicit confirmation before enabling live Hermes/OpenClaw workers.

### Hosted/public mode

Out of scope for this version. Public internet exposure, multi-tenant SaaS,
billing, tenant provisioning, enterprise SSO, and anonymous enrollment require
a separate commercial security architecture and must not be inferred from
private host mode.

## 5. Network Strategy

### Recommended v1 path: Tailscale Serve

The host application remains on loopback. Tailscale provides the encrypted
device network and HTTPS entrypoint. The product must print the exact local and
private-console URLs after startup without exposing credentials in either URL.

This is preferred over opening LAN router ports or directly binding the Python
server to every interface.

### Optional trusted-LAN path

A LAN binding may be added only after the same human authentication, CSRF,
origin checks, rate limits, and fail-closed startup checks pass. The launcher
must require an explicit `--allow-lan` confirmation and display a warning that
LAN is not equivalent to public hosted mode.

### Prohibited default

- no automatic router port forwarding;
- no default `0.0.0.0` binding;
- no unauthenticated remote dashboard;
- no API key embedded in query strings or generated console URLs.

## 6. Application Serving Model

Private host mode must use a production UI build, not the Vite development
server. The preferred v1 implementation is same-origin serving:

```text
https://<private-host>/                 React console
https://<private-host>/api/...          MIS API
https://<private-host>/health           redacted health
```

Requirements:

- browser routes use SPA fallback without swallowing `/api/*` errors;
- API calls use relative URLs by default;
- no CORS wildcard is required for the standard console path;
- static files use content hashes and conservative cache headers;
- health endpoints expose no token, secret, raw content, or private path;
- WebSocket or SSE, if added later, uses the same authenticated session.

## 7. Human Authentication and Authorization

The existing Agent Gateway token is a machine credential and must not be reused
as the normal browser credential.

Minimum private-host authentication:

- one bootstrap owner created locally on the host;
- one-time setup code displayed only in the host terminal;
- password or passkey enrollment after first login;
- server-side, expiring, revocable browser session;
- `HttpOnly`, `Secure`, and `SameSite` cookie when served over HTTPS;
- CSRF protection for state-changing browser requests;
- audit events for login, logout, failed login, session revoke, approval, task
  dispatch, artifact download, and administrative configuration change;
- roles at minimum: `owner`, `operator`, `approver`, and `viewer`;
- workspace authorization enforced server-side, never only hidden in the UI.

Machine workers continue to use scoped enrollment/session tokens bound to
`agent_id`, `workspace_id`, expiry, and permission scopes.

## 8. Data and Privacy Boundary

By default, all durable state remains on the host:

- SQLite database;
- knowledge source files and index;
- runtime credentials;
- worker logs;
- project worktrees;
- generated artifacts before explicit download.

The remote browser may cache only static application assets and an opaque
session cookie. Sensitive responses should use `Cache-Control: no-store`.
Artifact download must be an authenticated, audited, ID-based operation; the
browser must never receive arbitrary host paths.

Raw prompts, raw model responses, credentials, private messages, and full
transcripts remain excluded from committed project state and ordinary MIS
ledger records.

## 9. Operator Experience

### Host first run

Target flow:

```bash
curl -fsSL <verified-release-installer> | sh
agentops host init
agentops host start
```

The initializer performs preflight checks, creates local runtime directories
with restrictive permissions, builds or installs the production UI, creates the
owner setup code, and prints local/private URLs. It must not install or enable
Hermes/OpenClaw without a separate explicit action.

### Console first run

Target flow:

1. Open the private HTTPS URL in a browser.
2. Enter the one-time setup or invitation code.
3. Establish the owner/operator account.
4. See host, ledger, knowledge index, and worker readiness.
5. Dispatch a safe task or explicitly confirm a live runtime task.

No Git, Python, Node, repository clone, or Agent runtime is required on the
console computer.

### Host lifecycle commands

Proposed commands:

```text
agentops host init
agentops host start
agentops host stop
agentops host restart
agentops host status
agentops host logs
agentops host doctor
agentops host backup
agentops host update --check
agentops host console-url
agentops host session revoke
```

Commands that install services, change network exposure, enable live workers,
restore data, or update binaries remain preview-first and confirmation-gated.

## 10. Runtime and Knowledge Behavior

- Hermes/OpenClaw execute only on the host or an explicitly enrolled remote
  worker machine, never in the browser console.
- A console task is written to MIS first, then claimed through Agent Gateway.
- Every product claim about real execution requires run, runtime-event,
  evaluation, artifact, plan-evidence, and audit records.
- Live runtime remains opt-in and visibly labeled `live`, `dry-run`, `mock`,
  `waiting approval`, or `unavailable`.
- Knowledge retrieval runs on the host and returns bounded evidence identifiers
  and citations; ordinary console views do not return the entire corpus.
- Approved memories enter the host authority store only after the configured
  human/evaluation gate.

## 11. Packaging and Update Contract

The first distributable may be an unsigned developer preview, but its status
must be explicit. A release is not considered packaged merely because GitHub
automatically provides source archives.

Minimum release assets:

- versioned host bundle or installer for macOS;
- SHA-256 checksum file;
- software bill of materials and third-party notices;
- install, uninstall, backup, restore, and upgrade instructions;
- clean-machine acceptance evidence;
- release provenance tied to an exact Git commit;
- no DB, `.env`, token, cache, `node_modules`, `dist`, or local runtime logs.

Updates must preserve the database by default, run schema preflight, create a
verified backup before migration, and support rollback to the previous binary
and schema-compatible state.

## 12. Functional Acceptance

The private-host slice is accepted only when all items pass:

1. A clean host can install from a versioned release asset without cloning the
   repository manually.
2. `agentops host start` starts the production UI, API, ledger, knowledge index,
   and selected workers or reports an actionable failure.
3. A second computer with no project dependencies can open the console through
   the private-network URL and authenticate.
4. Unauthenticated API and UI data requests fail closed.
5. The remote console can create a task, observe claim/execution, approve a
   prepared action, review evaluation/audit evidence, and download an approved
   artifact.
6. Hermes or OpenClaw can execute one explicitly confirmed task on the host and
   write the complete bounded evidence chain to MIS.
7. Disconnecting the console does not stop the host worker or lose the task.
8. Restarting the host preserves ledger and knowledge state.
9. Backup and restore pass against an isolated test database.
10. No credential, database, raw prompt/response, private transcript, generated
    cache, or dependency directory appears in the release or Git diff.

## 13. Non-Goals

- automatic Hermes/OpenClaw/model installation in the first slice;
- public SaaS or direct internet exposure;
- multi-tenant billing and customer provisioning;
- complete enterprise RBAC or external identity provider integration;
- moving the knowledge corpus or model execution to the console computer;
- Notion/Dify live synchronization;
- mobile-native or Electron/Tauri desktop clients;
- universal interception of every internal runtime tool action.

## 14. Future Expansion

After private-host acceptance:

- optional guided Hermes/OpenClaw installation and health repair;
- signed/notarized macOS installer and background service;
- Windows/Linux host installers;
- PWA installation for the console;
- invitation and device management UI;
- secret manager integration;
- multiple workspaces with stronger isolation;
- customer-hosted and vendor-hosted deployment profiles.

