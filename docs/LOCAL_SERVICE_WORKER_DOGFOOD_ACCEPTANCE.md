# Local Service Worker Dogfood Acceptance

Status: installed Host service Worker recovery and fresh OpenClaw/Hermes tasks accepted locally

## Scope

This acceptance uses the installed Private Host at literal loopback. It repairs
the local Hermes and OpenClaw LaunchAgent credential binding, proves both are
fresh Agent Gateway service Workers, and dispatches one low-risk review task to
the long-running OpenClaw Worker. It does not use a repository server, a mock
adapter or a direct probe.

No credential, private message, full transcript, raw prompt, raw response,
Worker log, database row dump or local service file is stored in this document.
The existing Tailscale Serve profile was not changed.

## Recovery

The installed services were present but repeatedly exited because their local
credential file was bound to an obsolete loopback Host origin. A dedicated
Host Worker config was created outside the repository with owner-only `0600`
permissions and an exact origin/workspace binding to the installed Host. The
existing general CLI config was not overwritten.

Both `local_stack` service templates were regenerated with:

- `credential_source=local_config`;
- no token in the plist;
- short-lived Agent Gateway sessions;
- `--confirm-run` for Hermes/OpenClaw;
- launchd `KeepAlive` restart policy;
- the installed `agentops-worker` entrypoint and managed package directory.

The services were explicitly restarted. Two obsolete `daemon` services that
targeted a dead development port were unloaded and their plist files retained
locally as disabled backups rather than deleted.

## Fresh Readback

The installed Host then reported:

| Check | Result |
|---|---:|
| active service Workers | 2 |
| execution-capacity Workers | 2 |
| active remote sessions | 2 |
| stale service Workers | 0 |
| unverified process claims | 0 |
| Hermes adapter | ready |
| OpenClaw adapter | ready |

The OpenClaw service Worker automatically claimed and completed:

| Evidence | Reference / count |
|---|---|
| task | `tsk_3547f49a694a` |
| run | `run_gw_89b425c911e4` |
| Agent Plan | `plan_095f331ab1a82576` |
| verified plan-evidence manifest | `pem_8d981e5a7d6c55cb` |
| tool calls | 1 |
| runtime events | 8 |
| evaluations | 1 |
| artifacts | 1 |
| memory candidates | 1 |
| audit events | 8 |

The Hermes service Worker then independently claimed and completed:

| Evidence | Reference / count |
|---|---|
| task | `tsk_d0db920fc1cd` |
| run | `run_gw_b472aac7db01` |
| Agent Plan | `plan_981f8adf805bec31` |
| verified plan-evidence manifest | `pem_88f1ee10747ef435` |
| tool calls | 1 |
| runtime events | 8 |
| evaluations | 1 |
| artifacts | 1 |
| memory candidates | 1 |
| audit events | 8 |

The task and run both reached `completed`; the Worker returned to `idle`. The
bounded output summary identified the correct Host-initiated Relay and Host-only
TLS-key-custody constraints. The task evidence graph is a read model over MIS
ledgers and explicitly omits raw prompt, raw response and token material.

## Real Gap Found

The OpenClaw run reported knowledge retrieval quality at attention level with
`Recall@5=0.2` and `MRR=0.2`. Both Runtime summaries also described the service
loop as unverified even though the fresh Fleet readback showed two active
service Workers and zero stale service Workers. The execution and ledger loops
are accepted; the task-bound knowledge and operations-evidence context is not
fresh enough for a production grounding claim. Improve the Relay/Remote
Console corpus and inject current Fleet/service readback into governed task
context before repeating this acceptance.

The source Worker now adds a bounded current-process execution fact immediately
after a successful Agent Gateway task claim. It tells the Runtime that the
current process is active and the current claim succeeded, while explicitly
refusing to infer launchd/systemd ownership; historical service receipt/readback
remains visible as separate governance evidence. `worker_prompt_profile_smoke.py`
proves that stale historical service fields and a successful current claim can
coexist without exposing prompt, response, token, or service-template material.
This correction still requires an installed-package upgrade and a fresh real
Hermes/OpenClaw rerun before closing the live grounding gap.

## Remaining Boundaries

- The physical MacBook browser Console still lacks a successful authenticated
  `/workspace` receipt for this run.
- The deployed browser-only Relay, Host connector daemon, DNS/certificate
  lifecycle and browser disconnect acceptance remain open.
- Host-local service repair is local machine state; no credential/config/plist
  is committed.
