# Local Service Worker Dogfood Acceptance

Status: installed Host service Worker recovery and one fresh OpenClaw task accepted locally

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

The task and run both reached `completed`; the Worker returned to `idle`. The
bounded output summary identified the correct Host-initiated Relay and Host-only
TLS-key-custody constraints. The task evidence graph is a read model over MIS
ledgers and explicitly omits raw prompt, raw response and token material.

## Real Gap Found

This live run also reported knowledge retrieval quality at attention level with
`Recall@5=0.2` and `MRR=0.2`. The execution and ledger loop is accepted, but the
knowledge quality signal is not promoted to production-ready evidence. Improve
the Relay/Remote Console knowledge corpus and rerun the same governed task
before making a knowledge-grounding readiness claim.

## Remaining Boundaries

- Only OpenClaw executed a fresh task in this recovery slice; Hermes is healthy
  but did not execute a second task here.
- The physical MacBook browser Console still lacks a successful authenticated
  `/workspace` receipt for this run.
- The deployed browser-only Relay, Host connector daemon, DNS/certificate
  lifecycle and browser disconnect acceptance remain open.
- Host-local service repair is local machine state; no credential/config/plist
  is committed.
