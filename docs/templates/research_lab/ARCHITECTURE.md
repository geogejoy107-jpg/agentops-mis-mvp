# Research Lab Template v1 architecture

Status: Candidate (`canonical=false`)

Base contract: `1bce8f9e0312df9a29635a6988b62cd297b1ab14`

Manifest candidate provenance is the exact frozen contract base. C0 must replace
it with the eventual independently reviewed domain commit and regenerate
integrity at integration; `canonical=false` prevents promotion of this staged
candidate as a release artifact.

MIS Task: `tsk_tpl_v1_research_20260810`

## Authority boundary

Research Lab owns scientific domain records only. It injects a
`ResearchCorePort` and references MIS Core Workspace, Project, Agent, Task,
Plan, Run, ToolCall, PreparedAction, Approval, Artifact, Evaluation, Memory
Review, Audit, Evidence, Identity and Permission IDs. It opens no database and
does not implement another approval, memory, event or audit ledger. Every
authoritative C0 readback crosses a purpose-separated cryptographic receipt
verifier with Audit ID, exact binding fields and revocable key identity; caller
booleans and self-computed hashes never establish Core authority.

```text
shared Template SDK / typed API / AppShell
                    |
          ResearchService + state guards
                    |
       ResearchRepository (atomic records + outbox port)
                    |
   MIS Core transaction(records, outbox events)
```

The legacy `incubator/research-lab` SQLite ledger is not copied into this
template. Its useful protocol/executor concepts were reimplemented behind the
Core port. The v0 migration maps historical records into namespaced Core-backed
records, retains source hashes, requires a shared backup and archives rather
than deletes on rollback.

## Domain and execution

Protocols are immutable content-addressed versions. A Trial represents one
scientific condition; a JobAttempt is an infrastructure execution and retries
never inflate Trial count. Local execution uses an argv-only process group,
heartbeats, cancellation, timeouts, resource limits and adoption receipts.
SSH uses strict host keys, a secret resolver, stdin-only request transfer and a
durable idempotent remote wrapper with hashed Artifact collection. Private SSH
addresses additionally require an exact, signed target-registration snapshot.
Slurm uses
Core-approved argv-only `sbatch`/`sacct`/`scancel`, scheduler IDs, arrays,
resources and receipts.

Research agents are an event-driven openJiuwen team. Each input event maps to
one role and structured output. A missing/incompatible runtime returns
`unavailable`; it never becomes mock success. The runtime is pinned to upstream
`0.1.16`. Start and resume receipts are Core-attested over their complete
documents; a completed resume additionally proves atomic output and outbox
commit.

## Evidence integrity

A numeric Claim binds protocol hash, exact code commit, dataset version,
environment lock, seed, Core Run, JobAttempt, metric Artifact, Evaluation and
reviewer. Smoke, Pilot and Search stages cannot support final Claims. Claim
Gate blocks missing baselines, mixed protocols, stale/invalid artifacts,
unverified evaluations and insufficient seeds. Invalidation propagates through
an acyclic Evidence graph to Claims and Manuscripts.
