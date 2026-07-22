# AgentOps MIS Current Context Snapshot

> Status date: 2026-07-23
> Repository: `geogejoy107-jpg/agentops-mis-mvp`
> Local checkout: `agentops-mis-commercial-handoff-status-mainline`
> Development line: `codex/local-host-remote-console`
> Implementation baseline summarized: `706af7d2d2c0256cbc6912013e4b70e16b3ae43e`
> Snapshot commit: derive from `git rev-parse HEAD`
> Review surface: Draft PR `#104`
> Release status: active source development; not a release claim

This snapshot is the current compact continuation point. It supersedes the
operational branch, commit, CI, and next-action fields in the older
`PROJECT_STATE.md` and `HANDOFF.md`; those files remain historical governance
baselines until they are fully reconciled.

## Product Position

AgentOps MIS is a local-first control plane that lets humans assign, supervise,
approve, evaluate, and retain evidence for work executed by AI runtimes on the
same machine or through governed remote Workers.

## Authority And Memory Model

```text
Versioned spec / approved decision
-> workspace Knowledge Index + approved Memory
-> Agent Plan
-> Task / Run / Tool Call
-> Approval / Artifact / Evaluation
-> Memory Candidate / Audit
```

- Git and GitHub own code, branch, commit, PR, diff, and CI facts.
- AgentOps MIS owns runtime, approval, evidence, evaluation, and audit facts.
- Versioned project documents and reviewed Notion entries own approved project
  decisions and handoffs.
- Current tasks may use bounded workspace Knowledge plus approved Memory.
- Old Codex conversations are non-authoritative source material. They are not a
  substitute for project context and are eligible for expiry after their
  durable Project Delta has been captured.

No credential, private message, transcript, raw prompt, or raw response was
read or copied to produce this snapshot.

## Verified Committed Source

The current committed line contains these latest product slices:

- `0057efa` and `75857b4`: bounded workspace-scoped context packets from
  versioned Knowledge summaries plus approved Memory, with hash/ID/count
  receipts instead of source bodies.
- `0adbc9f`: workspace-authoritative governed Memory behavior.
- `136779e`: bounded Worker Sessions release their resources cleanly.
- `706af7d`: Run Detail exposes a Project Context Receipt so a human can verify
  which governed context was used without exposing its body.

Real, explicitly confirmed local dogfood produced:

- OpenClaw Run `run_gw_ba8013a9aa17`;
- Hermes Run `run_gw_5387a296a361`;
- eight governed context blocks per Run, including three approved seed Memory
  references;
- compact Run, Tool, Evaluation, Runtime Event, Audit, artifact, approval, and
  candidate-memory evidence with raw input/output omitted.

Hermes candidate `mem_gw_80af5cdbee359296` remains pending Human review. Agent
output therefore has not silently become canonical project knowledge.

## Installed Host Versus Source

The installed Private Host is preview.41 at exact commit
`0adbc9fb9bb569b68f226914705114fc8cbcf0f8`. It does not contain every source
change at committed HEAD and must not be used as evidence for newer behavior.

Local dogfood found that preview.41 could exhaust its file-descriptor budget
during sustained API polling because Python's SQLite transaction context did
not close connections. A controlled Host recovery restored readiness. No
database, credential, prompt, response, transcript, or Docker data was removed.

## Current Uncommitted Work

The worktree intentionally contains an uncommitted reliability slice:

- `db_session()` closes server-managed SQLite connections while preserving
  commit and rollback semantics;
- all server-managed `with db()` call sites use the managed lifecycle;
- a focused lifecycle smoke, CI entry, acceptance note, and merge-readiness
  gate were added;
- the Worker daemon resilience smoke now waits for daemon-state convergence
  after task completion.

Focused SQLite lifecycle, pragma, concurrency, compile, secret-scan, and diff
checks passed during development. An isolated rerun of the Worker daemon smoke
later timed out before the task completed, so this worktree is not yet accepted,
committed, packaged, or attributed to the installed Host.

## CI Truth

- Exact committed-head push run `29949180220` was green.
- PR run `29949184920` had green Python/UI portions but failed the backend lane
  in `worker_daemon_resilience_smoke.py`.
- The current uncommitted work has no exact-head CI evidence.

Historical green CI does not close the current worktree. Re-run focused local
verification, commit, push, and require exact new push/PR checks before release.

## Storage And Session Retention

- Docker data is outside this cleanup and must not be deleted automatically.
- The current Codex task
  `019ec0ec-14bf-7243-a145-8b5659f0193a` is retained for continuation.
- Selected completed session files may be deleted only after this snapshot and
  the retention acceptance record exist and pass a no-secret/diff check.
- Session cleanup uses file metadata only; raw JSONL bodies are not inspected.
- Deleting an expired session removes chat-resume capability for that session,
  not Git code, approved Memory, MIS ledger evidence, or this snapshot.

See [`CODEX_SESSION_RETENTION_ACCEPTANCE.md`](./CODEX_SESSION_RETENTION_ACCEPTANCE.md).

## Open Gates

1. Diagnose and stabilize the isolated Worker daemon completion timeout.
2. Re-run SQLite lifecycle and Worker resilience verification on current source.
3. Commit and push the reliability slice; require exact-head CI.
4. Package and install a later Host only after the storage preflight has at
   least 2 GiB available.
5. Exercise sustained Workspace/API polling and prove bounded SQLite handles.
6. Repeat real governed-memory OpenClaw/Hermes dogfood on the exact installed
   package.
7. Complete physical remote-browser acceptance from the second Mac when that
   endpoint is reachable.

## Next Single Action

Finish the Worker daemon smoke investigation on an isolated temporary database,
then run the focused SQLite/Worker verification set before committing the
current reliability slice.

## Project Delta

```yaml
type: ContextSnapshot
title: Current local Host, governed Memory, CI, and reliability truth
status: ActiveDevelopment
priority: P0
module: Project Governance
repository: geogejoy107-jpg/agentops-mis-mvp
branch: codex/local-host-remote-console
commit: 706af7d2d2c0256cbc6912013e4b70e16b3ae43e
updates: PROJECT_STATE.md and HANDOFF.md operational fields
evidence: Git history, exact CI run identities, bounded MIS runtime receipts, and local verification
next_action: stabilize Worker daemon smoke, verify current source, then commit and push
```
