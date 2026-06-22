# R1 Evidence — Current-Code Delta at the v1.1 Research Baseline

> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Development branch observed: `codex/agent-gateway-kb-demo`  
> Frozen research baseline: `169924acdb6a301c1c870f48449aedc76bf6fb5a`  
> Research branch: `research-open-source-base-index-v1-1`  
> Verified: 2026-06-22  
> Evidence type: static code/file review plus GitHub Actions metadata; no local Hermes/OpenClaw execution in this cycle

## Executive Delta

The external Base Index v1.0 and the previous implementation review were already stale at branch creation.

Compared with `6305b2533f7219ecdeb1fc3763e1196a25a38272`, the frozen development baseline is **116 commits ahead**. The delta contains substantial correctness and release work, including:

- GitHub Actions CI;
- Agent Plan integrity and run-start gates;
- prepared-action approval and exact-once resume tests;
- shared redaction helpers;
- exact collaborator-scope and special-character scope tests;
- Knowledge workspace policy, provenance, retrieval-quality, and incremental indexing tests;
- SQLite WAL/busy-timeout/reliability tests;
- startup and shared-mode security guards;
- license, third-party notice, minimal SBOM, and release provenance documents;
- operator action, receipt, handoff, health, audit-loop, work-package, and read-model work;
- Agent Loop engineering notes and bounded operator-loop policies.

These file additions are implementation signals, not automatic proof that every historical P0 blocker is closed. Current-head tests and behavior remain authoritative.

## GitHub Actions Truth

At commit `169924acdb6a301c1c870f48449aedc76bf6fb5a`:

- workflow: `AgentOps MIS CI`;
- run number: `132`;
- overall conclusion: `failure`;
- `UI build`: success;
- `Backend deterministic smokes`: failure;
- syntax/diff checks: success;
- offline safety smokes: success;
- isolated local server startup: success;
- failure occurred in the server-backed smoke suite.

Therefore the correct release statement is:

```text
CI exists and executes substantial deterministic gates.
The exact frozen development baseline is not green.
```

It is not acceptable to mark P0-09 complete from workflow-file presence alone.

## Historical P0 Reconciliation — Initial Status

| Item | Observed current-head evidence | Initial research status | Remaining verification |
|---|---|---|---|
| P0-00 current-head re-audit | 116-commit delta inventoried; first evidence note created | In progress | Inspect behavior and test failures lane by lane |
| P0-01 Plan author/approver separation | `agent_plan_integrity_smoke.py` rejects create-time `approved`, rejects bound Agent approval, records human approval | Candidate resolved | Confirm backend implementation and CI pass on frozen head |
| P0-02 immutable Plan and Run binding | Plan hash, verification-result hash, `verified_at`, approval-required run block, and `agent_plan_id` run start are asserted | Candidate largely resolved | Confirm plan version/supersession behavior and Delivery binding across all governed workflows |
| P0-03 reference provenance | Missing spec, missing base, unsafe path, candidate-memory authority, source hash, and visibility checks exist | Candidate largely resolved | Confirm decision references, project scope, changed/superseded document handling, and all negative tests pass |
| P0-04 prepared action exact resume | `prepared_action_approval_wall_smoke.py` asserts required preparation, action hash, checkpoint, approval, resume, consumed state, provider side-effect ID, and replay rejection | Partial / supported-path candidate resolved | Confirm all high-risk and external-write paths use the gate; runtime-internal actions remain a separate risk |
| P0-05 redaction and shared auth | Shared `agentops_mis_cli/redaction.py`; redaction, startup guard, production readiness, and shared-mode guard smokes are in CI | Candidate largely resolved | Confirm all server paths import one contract and inspect CI failure |
| P0-06 exact collaborator/workspace visibility | `collaborator_exact_scope_smoke.py` and special-character scope smoke added | Candidate resolved | Confirm production query path no longer uses approximate text matching and tests pass |
| P0-07 Knowledge ACL/provenance | Workspace/private/global visibility, `retrieval_id`, `source_hash`, `access_level`, exclusion reasons, redaction, explicit fallback quality, and incremental no-op are asserted | Candidate largely resolved | Confirm project/access-tag policy breadth, chunking, evaluation corpus, latency, and CI pass |
| P0-08 SQLite concurrency | WAL, `busy_timeout >= 5000`, foreign keys, NORMAL synchronous mode, and reliability smokes exist | Partial | Confirm concurrency workload numbers, lock/error rate, transaction boundaries, and exact-head pass |
| P0-09 CI/license/provenance | CI workflow, LICENSE, notices, SBOM and provenance docs exist | Open | Backend deterministic suite is red; secret scan/SBOM automation breadth and failure root cause need closure |

## Agent Plan Integrity Signals

The current smoke contract now checks:

```text
Agent cannot create status=approved
Candidate memory cannot be treated as authority
Approved memory can be referenced
Missing spec fails verification
Missing base fails verification
Unsafe file escape fails verification
Plan hash is present
Verification-result hash is present
High-risk Plan creates a linked pending approval
Run start is blocked before approval
Bound Agent token cannot approve the Plan
Human approval records the approver
Run start binds the approved Plan
```

This is materially stronger than the earlier v0 Plan evidence contract.

Open research question: whether every governed execution path is forced through the same contract, especially legacy/mock paths, manually recorded Runs, loop lanes, external integrations, and future Swarm child runs.

## Prepared Action Signals

The prepared-action smoke now expresses the desired state machine:

```text
unprepared high-risk external action -> rejected
prepare action -> action hash + checkpoint + idempotency key
request approval -> pending
approve -> resume required
resume exact action -> consumed + provider side-effect ID
replay -> 409 prepared_action_already_consumed
```

This supports moving the Base Index entry for durable approval from `NOT_IMPLEMENTED` to `PARTIAL` or `IMPLEMENTED_FOR_SUPPORTED_PATHS`, not to universal `IMPLEMENTED`.

## Knowledge and Retrieval Signals

The current knowledge-policy smoke asserts:

- redaction before searchable output;
- exclusion of raw-customer paths;
- explicit FTS5 versus fallback mode;
- fallback-quality warning and searched-field disclosure;
- incremental no-op indexing;
- workspace-private and global visibility;
- retrieval IDs and source hashes;
- access-level and raw-content-omitted metadata.

The next Base Index version should therefore distinguish:

```text
Knowledge governance/provenance v0: implemented or partial
Heading-aware chunking and retrieval evaluation: partial
Repo Map and hybrid retrieval: not yet proven
Enterprise multi-tenant knowledge plane: not proven
```

## Loop and Swarm Boundary

The current delta includes Agent Loop engineering notes, operator advance-loop policy, loop audit and self-check smokes, and the existing supervised Hermes/OpenClaw loop.

This remains a **bounded, supervised loop/harness** unless evidence proves:

- dynamic team assembly;
- distributed workers across machines;
- swarm-level task allocation and negotiation;
- shared swarm state and fault recovery;
- skill evolution governance;
- a JiuwenSwarm adapter emitting normalized MIS parent/child run evidence.

No such adapter is established by the files reviewed in this initial lane. JiuwenSwarm remains `PILOT` / `NOT_INTEGRATED` pending R4.

## Base Index Status Changes Suggested by R1

| Base or capability | v1.1 research decision | Integration status at frozen baseline | Note |
|---|---|---|---|
| GitHub Actions | ADOPT_NOW | IMPLEMENTED, failing current run | Keep as release gate; investigate backend suite |
| SQLite FTS5 | ADOPT_NOW | IMPLEMENTED | Preserve local-first baseline |
| SQLite WAL/busy timeout | ADOPT_NOW | IMPLEMENTED candidate | Verify reliability benchmark pass |
| Shared redaction library | ADOPT_NOW | IMPLEMENTED candidate | Verify server/worker/CLI full adoption |
| Durable prepared-action approval | ADOPT_NOW | PARTIAL / supported paths | Do not overclaim universal runtime governance |
| Agent Plan integrity contract | ADOPT_NOW | PARTIAL to substantial | Verify universal execution enforcement and supersession |
| Knowledge workspace/provenance | ADOPT_NOW | PARTIAL to substantial | Chunking/Repo Map/hybrid remain later work |
| Operator loop harness | REFERENCE / INTERNAL | IMPLEMENTED internal path | Not a general distributed Swarm |
| JiuwenSwarm | PILOT | NOT_INTEGRATED | R4 must verify current upstream and adapter design |
| License/provenance/SBOM docs | ADOPT_NOW | PARTIAL | Documentation exists; release automation/gates need proof |

## Immediate R1 Next Actions

1. Identify the exact failing command in CI run 132 and record it as release evidence.
2. Inspect the backend implementations behind Plan, Prepared Action, Knowledge scope, collaborator scope, redaction, and SQLite tests.
3. Verify whether the research branch's own draft PR receives CI, noting that the workflow push filter only lists `main` and `codex/**`, while pull-request events should still execute.
4. Update the consolidated Base Registry with the statuses above only after evidence review.

## Project Delta

```yaml
type: Evidence
title: Current-code delta shows major P0 implementation progress but frozen HEAD CI remains red
status: Implemented
priority: P0
module: Research
summary: >-
  The 169924ac development baseline is 116 commits beyond 6305b253 and contains
  concrete Plan integrity, prepared-action, knowledge scope, redaction, SQLite,
  CI, license, provenance, operator-loop, and performance evidence. Current CI
  exists but fails in the server-backed backend smoke suite.
source: GitHub compare, repository files, and Actions run 132
repository: geogejoy107-jpg/agentops-mis-mvp
branch: research-open-source-base-index-v1-1
commit: 169924acdb6a301c1c870f48449aedc76bf6fb5a
duplicate_of: null
updates: P0-00 current-head re-audit; external Base Index v1.0 implementation statuses
supersedes: prior statement that current HEAD had no GitHub Actions run
conflicts_with: null
owner: research agents
next_action: isolate the backend CI failure and continue Harness/Loop/Swarm evidence lanes
canonical: false
```
