# Private Host Worker Intake Heartbeat Acceptance

## Real Finding

After the real Mini Host upgraded to
`v1.6.0-private-host-preview.37`, the Hermes and OpenClaw Worker LaunchAgents
both loaded with new processes and continued to write fresh, bounded
`task.pull` Runtime Events. The queue contained an assigned task that failed
the Intake Gate, so every poll returned `intake_blocked`.

The Fleet projection nevertheless reported both service Workers as stale. The
last `agent.heartbeat` events predated the maintenance window even though the
processes and authenticated task pulls were current. No Worker log, task body,
raw prompt/response, credential or private origin was read or retained for
this finding.

## Root Cause

`process_one_task` returned early when Intake blocked every pulled task. That
branch ran before the normal no-task heartbeat. Auto-plan success, existing
plan verification, high-risk auto-plan refusal and disabled auto-plan could
therefore all keep a healthy long-running Worker invisible to the Fleet health
projection.

## Corrective Contract

Before any Intake-blocked return, the Worker now attempts an authenticated idle
heartbeat through the same Agent Gateway boundary used by normal idle and
post-run paths.

- The summary is static and contains no task title, description, blocked gate,
  source text or count supplied by the server.
- Unchanged heartbeat requests are limited to once every 60 seconds in the
  Worker process. A status transition or completed run may force an immediate
  update.
- The server always refreshes authenticated token and Agent liveness, but adds
  heartbeat Runtime Event and Audit evidence only on a status transition or
  once every 15 minutes. This separates current Fleet health from historical
  ledger sampling.
- Repeated `task.pull` calls remain live reads, but an unchanged eligible and
  Intake-blocked queue shape adds Runtime/Audit evidence only once every 15
  minutes. A queue-state hash change records immediately; task text and task
  identifiers are not stored in the observation state.
- A rejected or unavailable blocked-path heartbeat is not treated as healthy:
  the failure is returned to the Worker loop, recorded as a Worker error and
  follows the existing bounded error backoff. The error-report heartbeat
  remains best-effort so reporting failure cannot recurse indefinitely.
- Worker state schema v2 adds `last_iteration_at`; the legacy
  `last_heartbeat_at` key remains for shape compatibility but no longer
  relabels every successful loop iteration as a remote heartbeat.
- No run starts, Runtime adapter executes, approval changes or task mutation is
  introduced.
- Fleet liveness is keyed by `(workspace_id, agent_id)`. Enrollment and Session
  activity cannot make the same Agent ID in another workspace appear fresh;
  an older unscoped Runtime Event is only a fallback when the Agent has one
  active workspace.
- Only an active Session whose scopes match the real local-config Worker
  closed-loop policy is projected as service execution capacity. This includes
  registration, heartbeat, plan/evidence, knowledge, task claim, run,
  Runtime Event, tool, artifact, memory, Evaluation and Audit permissions. A
  read-only or partial Session remains visible as enrollment/session activity
  but cannot claim a runnable Worker lane, and generic Session use is not
  treated as heartbeat.
- Heartbeat sampling state is also keyed by `(workspace_id, agent_id)`, so the
  same Agent ID in two workspaces receives independent bounded Runtime/Audit
  evidence.

## Verification

```bash
python3 -m py_compile \
  server.py \
  agentops_mis_cli/worker.py \
  agentops_mis_core/worker_fleet.py \
  scripts/worker_intake_auto_plan_smoke.py \
  scripts/worker_intake_heartbeat_fleet_smoke.py
python3 scripts/worker_intake_auto_plan_smoke.py
python3 scripts/worker_intake_heartbeat_fleet_smoke.py
python3 scripts/operator_loop_supervision_consumption_smoke.py
python3 scripts/operator_task_intake_smoke.py --isolated-fixture
python3 scripts/secret_scan_smoke.py
git diff --check
```

The focused smoke covers four early-return paths: automatic plan creation,
existing plan verification, high-risk refusal and explicitly disabled
auto-plan. It also proves that a rejected heartbeat propagates instead of being
reported healthy and that 20 immediate repeated blocked polls produce only one
heartbeat request. The isolated contract additionally mints a real restricted
Session with `tasks:read` but no heartbeat scope; its authenticated pull
succeeds and its heartbeat is rejected with `forbidden`, which propagates to
the Worker loop.

The isolated Fleet smoke uses a real short-lived Agent Gateway session and
temporary SQLite authority. Across 21 blocked iterations it makes two
heartbeat requests, keeps the Fleet state `fresh`, and adds exactly one
heartbeat Runtime Event, one heartbeat Audit row, one sampled task-pull Runtime
Event and one task-pull Audit row. It asserts both the remote-enrollment and
service-worker projections plus execution-capacity counts. A second workspace
with the same Agent ID remains stale while the primary workspace is fresh. The
second due client request refreshes liveness but is coalesced from historical
evidence. No provider or live Runtime executes. A separate 20-request
concurrent case for each of heartbeat and task pull proves the process-local,
DB-only critical sections record exactly one Runtime Event and one Audit row
rather than racing duplicate ledger decisions. The critical sections contain
no network, subprocess or Runtime adapter call.

When one local LaunchAgent also appears through its authenticated Gateway
Session, execution capacity is keyed by `(workspace_id, agent_id)` on both
paths and remains one Worker rather than an inflated count of two.
The smoke also proves that a read-only Session can pull safely without becoming
execution capacity, and that two workspaces using the same Agent ID each create
their own first heartbeat sampling record.

## Package Boundary

The real finding is bound to installed preview.37. The corrective code is
source-only until a later exact-commit package is built, published, installed
and the same service Worker fleet readback becomes fresh. Preview.37 must not
be credited with this correction.
