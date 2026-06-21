# AgentOps MIS v1.5 Branch Audit and Merge Plan

> Target: `codex/agent-gateway-kb-demo`  
> Frozen audit SHA: `8d1827e00629bdca4779794121ca4a31dfa3f1e1`  
> Relative to `main`: ahead 109 / behind 0  
> Audit date: 2026-06-21

## 0. Evidence boundary

This audit distinguishes:

1. code inspected at the exact SHA;
2. acceptance evidence already committed to the repository;
3. independent execution performed by this audit.

The repository documents many passed smoke tests and real Hermes/OpenClaw run IDs. This audit did not rerun those local runtimes. The audited commit currently has no GitHub commit status checks, so historical acceptance evidence must be complemented by CI and a clean-machine release-candidate pass.

## 1. Executive decision

```text
Local demo ready:             YES
Controlled local dogfood:     YES, with documented limits
Agent Gateway v1.5 shape:     STRONG
Method Block v0:              IMPLEMENTED
Knowledge Index v0:           IMPLEMENTED
Merge ready today:            NO
Merge ready after blockers:   YES
Shared/commercial ready:      NO
```

The branch is no longer a mock-only prototype. It is a local-first AI-team control-plane candidate with a real machine interface, scoped remote workers, runtime adapters, review queues, evidence ledgers, a first Agent Work Method Block and a first local knowledge index.

The next move should not be more horizontal features. It should be correctness, security, performance, modularization and release engineering.

## 2. What the 109-commit line has achieved

### 2.1 Machine-facing Agent Gateway

- enrollment requests and issuance;
- scoped long-lived tokens stored as hashes;
- short-lived sessions;
- rotation, revocation and expiry;
- heartbeat and health state;
- workspace and Agent binding;
- task pull, claim and run lifecycle;
- tool, artifact, evaluation, memory, approval and audit writeback;
- scoped task, run, artifact, approval, memory and review-queue reads.

### 2.2 Installable CLI and worker

- `agentops` and `agentops-worker` console commands;
- dependency-free/offline build backend;
- local and remote configuration;
- doctor, status and readiness;
- once, loop and daemon modes;
- retry, backoff, session refresh and stuck recovery;
- safe service template/install/check paths;
- Mock, Hermes and OpenClaw adapters.

### 2.3 Commander and customer delivery

- local readiness;
- worker fleet and adapter readiness;
- project board and integration inbox;
- async workflow jobs;
- review queue and inline decisions;
- customer delivery board and reports;
- KB-bot project demo;
- evidence chain across run, tool, evaluation, artifact, memory, approval and audit.

### 2.4 Agent Work Method Block v0

The latest three commits add:

```text
PROJECT_SPEC.md
AGENT_WORKFLOW.md
BASE_INDEX.md
secret_registry.md
knowledge/shared/
knowledge/bases/
knowledge/runbooks/
agent_plans
knowledge_documents
knowledge_fts
knowledge search/index API
agent-plan create/list/get/verify API
CLI commands and smoke coverage
```

The method is:

```text
READ → PLAN → RETRIEVE → COMPARE → EXECUTE → VERIFY → RECORD
```

This is a meaningful advance and directly addresses the earlier problem that Agents ignored existing bases and rebuilt from scratch.

## 3. Strong architectural decisions

### 3.1 Browser for humans, machine contracts for Agents

The boundary is correct:

```text
Browser: supervision, judgment, approval, review, delivery
CLI/API/MCP: Agent execution and evidence
```

This is more stable and auditable than browser automation.

### 3.2 MIS remains the authority

Hermes, OpenClaw, Dify, Notion, Pixel Office and other systems remain runtime, connector or visual layers. Task, run, approval, memory, evaluation, artifact and audit authority stays in MIS.

### 3.3 Remote Agent identity is capability-scoped

Workspace, Agent, scope, expiry, heartbeat and session state are first-class. This is the correct foundation for customer machines, GPU workers, BYOC and a future Marketplace.

### 3.4 Failure is recorded rather than hidden

A failed runtime can still produce error classification, evaluation and audit evidence. That is an enterprise-control-plane property, not a demo trick.

### 3.5 Method and knowledge are now product surfaces

The project has moved beyond prose-only instructions. Specs, knowledge, plans and verification are exposed through the Agent Gateway and CLI.

## 4. Merge blockers

## B0-1: Agent Plan is not yet a hard execution contract

**Severity: Blocker**

Current state:

- an Agent can create an `agent_plan`;
- plan verification checks whether several fields are non-empty;
- the run schema does not bind execution to an immutable plan hash;
- task claim, run start, worker execution and delivery approval do not universally require a verified plan;
- the repository's own Method Block document calls out this bypass.

An Agent can therefore create a valid-looking plan and execute a different path.

### Required fix

Add or enforce:

```text
plan_hash
plan_version
verified_at
verification_result_hash
approved_by
approved_at
agent_plan_id on run/work package
tool/file scope derived from plan
execution-vs-plan evidence comparison
```

Real execution must reject:

```text
missing plan
failed plan verification
superseded plan
plan/run Agent mismatch
plan/task mismatch
changed plan after approval
execution outside declared scope
```

## B0-2: Agent can self-submit an approved plan

**Severity: Blocker**

The plan-create endpoint accepts caller-provided status including `approved`, and the CLI exposes `approved` as a creation choice. A scoped Agent with `agent_plans:write` can therefore create its own plan already marked approved.

### Required fix

- Agent write scope may create `draft` or `submitted` only.
- Only a human/admin/policy role may transition to `approved` or `rejected`.
- Approval transition must be append-only and audited.
- High/critical plans require a real approval object, not only `approval_required=1`.
- Plan status must not be a free input to the create endpoint.

## B0-3: Plan verification validates presence, not provenance

**Severity: High**

Current checks verify that lists such as referenced specs, memories and bases are non-empty. They do not prove that:

- a spec path exists;
- a memory ID exists and is visible;
- a memory is approved rather than candidate/rejected;
- a base ID exists;
- a file path belongs to the permitted repository/workspace;
- the references were actually retrieved during this task.

### Required fix

- resolve every reference to a canonical object;
- reject nonexistent and inaccessible references;
- require approved memory for authority;
- store content/version hashes;
- attach retrieval query/result IDs;
- verify file scope and base constraints;
- return a signed/hashed verification result that the run consumes.

## B0-4: Approval is still not durable action pause/resume

**Severity: Blocker for real side effects**

Generic approval currently changes ledger state and may call `complete_run()`. It does not universally persist and later execute an exact prepared action.

Missing primitives:

```text
prepared_action
normalized arguments
action hash
policy version
checkpoint
resume token
idempotency key
consumed_at
provider side-effect ID
```

### Required fix or restriction

Preferred: implement durable prepared-action resume.

Minimum v1.5 alternative: explicitly call the existing mechanism ledger/delivery approval, prohibit generic external side effects and avoid claims that a tool was executed after approval.

## B0-5: Runtime internal tool behavior is opaque to MIS

**Severity: Blocker for commercial use**

Hermes/OpenClaw execution is currently summarized as one `agent_worker.<adapter>` tool call. The record can be low risk even when the runtime internally uses shell, files, Git, network or external APIs.

`--confirm-run` authorizes starting the runtime; it is not per-action governance.

### Required fix

- publish a runtime capability manifest;
- classify actual task/adapter risk rather than fixed low risk;
- define sandbox, workdir, network and secret boundaries;
- ingest runtime tool events where available;
- restrict shared/commercial mode when tool events are unavailable;
- route external writes through guarded MIS tools.

## B0-6: Worker redaction is not strong enough

**Severity: Blocker**

The server now has a shared-style full-text redaction helper, but the worker still has a separate marker-replacement implementation that can leave the secret value behind or behave inconsistently with mixed case.

### Required fix

- one redaction library for server, CLI, worker and tests;
- value-aware patterns;
- redact before truncate;
- known-secret corpus and fuzz/property tests;
- raw adapter output hash-only by default.

## B0-7: Shared deployment is fail-open

**Severity: Blocker for network/shared deployment**

Current local-development behavior allows:

- all Agent Gateway scopes when no gateway key is configured;
- open admin enrollment endpoints when no admin key is configured;
- unauthenticated browser/local APIs;
- worker start/stop and approval operations through local APIs.

This is acceptable only while strictly bound to loopback.

### Required fix

If the server binds to a non-loopback address:

```text
require explicit non-loopback opt-in
require gateway authentication
require admin authentication
reject local_dev_no_token
show a blocking doctor/readiness error
```

Commercial release additionally needs user authentication, RBAC, CSRF/CORS, rate limiting, TLS/reverse proxy and tenant membership.

## B0-8: Collaborator authorization uses substring LIKE

**Severity: High**

Multiple task/run/artifact/approval/memory queries use JSON text with `LIKE '%agent_id%'`. Similar IDs can collide, such as one ID being a prefix of another.

### Required fix

Use either:

```text
task_collaborators(task_id, agent_id, workspace_id)
```

or exact SQLite JSON-array comparison through `json_each`.

Add regressions for similar and special-character IDs.

## B0-9: Knowledge search has no workspace or ACL isolation

**Severity: High for multi-customer use**

The v0 index is a repository-wide Markdown index. `knowledge_documents` contains scope metadata, but search does not filter by workspace, Agent, access tags or tenant policy.

This is acceptable for one local repository and one trusted project. It is not a multi-tenant knowledge service.

### Required fix

- add workspace/project/access metadata;
- distinguish public project doctrine from private customer memory;
- enforce authorization before retrieval;
- never expose candidate/rejected memory as authority;
- separate repo-global docs from customer documents;
- add access tests before remote customer use.

## B0-10: No automated CI on the audited HEAD

**Severity: Merge Blocker**

The audited commit has no status checks. The repository contains many smoke scripts, but they are not automatically required before merge.

Minimum CI:

```text
syntax and diff check
core deterministic smoke
Agent Gateway scope/session/workspace tests
Method Block smoke
review queue smoke
redaction and production-readiness tests
worker package/retry/recovery tests
KB/customer workflow smoke
UI build
secret scan
```

Live Hermes/OpenClaw tests should remain protected local/manual jobs.

## B0-11: SQLite is not configured for current concurrency

**Severity: High**

The DB factory still enables only foreign keys. The application now combines threaded HTTP, workers, workflow jobs, heartbeat, review queues and many UI reads.

### Required fix

```sql
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA synchronous=NORMAL;
```

Also require short transactions and no model/network/subprocess call while a write transaction is held.

## B0-12: License and provenance are incomplete

**Severity: High for public/commercial release**

Package metadata says proprietary local MVP, while the public repository has no root license. The product also references or integrates multiple open-source bases and non-commercial visual assets.

### Required fix

- root license;
- matching package metadata;
- third-party notices;
- source repository/version/license/use records;
- SBOM;
- UI/icon/art provenance;
- explicit exclusion of non-commercial Pixel Office assets from commercial builds.

## 5. Important non-blocking issues

### H1: Knowledge retrieval is full-document and minimally ranked

The v0 index is useful, but currently:

- one FTS row represents a full Markdown file;
- no heading-aware chunks;
- no token budget;
- no retrieval provenance object;
- no test set with Recall@k/MRR;
- Chinese tokenization may be weak for long phrases;
- fallback LIKE only sees title/path/summary rather than full body.

Next step:

```text
heading-aware chunks
incremental metadata
query log
retrieval result IDs
Chinese/English test corpus
Repo Map
optional hybrid retrieval only after baseline
```

### H2: Scoped review queue filters after a global top-N fetch

The endpoint avoids returning invisible items, but global truncation can starve a workspace and distort counts. Scope should be applied in SQL before limit, with cursor pagination and scoped totals.

### H3: Generic worker success is infrastructure success, not acceptance success

The worker primarily checks adapter execution and can score success as pass. A true project closeout needs:

- required Artifact schema;
- acceptance evaluator;
- independent verifier or human gate;
- partial/needs-input states;
- evidence completeness gate.

### H4: Core files are monolithic

Approximate scale at this audit point:

```text
server.py                         ~10k lines
agentops_mis_cli/agentops.py      ~1.8k lines
agentops_mis_cli/worker.py        ~1.3k lines
AIEmployees.tsx                   >1.3k lines
liveApi.ts                        >2.2k lines
```

Use behavior-preserving extraction, not a stack rewrite.

### H5: AI Employees initial data fan-out is excessive

The page loads many aggregate endpoints and daemon logs together. This can cause slow first paint, repeated SQLite aggregation and all-or-nothing loading.

Recommended:

- a lightweight command-center BFF/read model;
- independent panel loading;
- logs on demand;
- pagination/cursors;
- short read-model cache;
- fewer refresh-wide requests.

### H6: API and migration contracts need versioning

Move stable machine contracts toward `/api/v1`, OpenAPI schemas, a migration version table and explicit compatibility rules.

## 6. Updated P0 assessment

| P0 | Current judgment |
|---|---|
| Agent Method Block | v0 implemented; hard enforcement, immutable plan and role-separated approval still missing |
| Shared Knowledge Index | v0 implemented; ACL, chunking, retrieval evaluation and Repo Map still missing |
| Real Local Runtime | local dogfood achieved; runtime internal tools, durable steps and production supervision remain |
| Approval Wall | review/ledger layer achieved; exact prepared-action resume remains missing |
| Local Coding Template | still missing worktree, localization, patch/test artifacts, independent verifier and merge gate |

## 7. Performance plan

Measure before further optimization:

```text
server cold start
local readiness p50/p95
worker status p50/p95
local/scoped review queue p50/p95
knowledge search p50/p95 and Recall@5
workflow accepted latency
approval decision latency
Agent Employees initial request count
time to first useful panel
SQLite locked/busy count
```

Initial targets:

```text
ordinary control-plane API p95    <150 ms
scoped queue/search p95           <200 ms
workflow acceptance               <300 ms
approval decision                 <300 ms
useful command-center summary     <1 s
SQLite lock errors                0
```

Model execution time is reported separately from control-plane latency.

## 8. Recommended hardening PR sequence

```text
PR-A plan-integrity-and-role-separation
PR-B redaction-and-secret-safety
PR-C non-loopback-auth-guard
PR-D collaborator-and-knowledge-scope-correctness
PR-E sqlite-wal-and-performance-baseline
PR-F approval-contract-and-runtime-capabilities
PR-G CI-and-release-gates
PR-H license-and-third-party-provenance
```

After blockers:

```text
PR-I module extraction
PR-J command-center read model
PR-K knowledge chunks/retrieval evaluation/Repo Map
PR-L local coding project template
```

## 9. Merge strategy

Do not merge the full line to `main` without a release candidate.

1. Freeze an exact SHA.
2. Apply blocker fixes in reviewable PRs.
3. Require CI on the exact candidate.
4. Run a clean-machine install/build/mock closure.
5. Run optional protected Hermes/OpenClaw live acceptance.
6. Verify migration and rollback.
7. Tag `v1.5.0-rc1`.
8. Merge with accurate README and product claims.

Preserve functional history or grouped commits. Avoid one opaque squash of all 109 commits.

## 10. Public claim boundary

### Safe to demonstrate

- local/remote Agent enrollment;
- scoped token/session and heartbeat;
- Agent Gateway CLI/API;
- Mock/Hermes/OpenClaw worker execution;
- async workflow and commander inbox;
- Method Block and FTS5 knowledge search;
- Agent Plan creation and verification as a v0 workflow;
- evidence ledger, review queue and customer delivery;
- failures and recovery;
- Pixel Office as a visualizer.

### Must be qualified

- Approval Wall: review/ledger approval, not yet universal prepared-action resume;
- Knowledge: local repo index v0, not enterprise multi-tenant RAG;
- Agent Plan: method evidence v0, not yet a hard immutable execution contract;
- Multi-Agent team: bounded worker lanes, not full autonomous swarm;
- Commercialization: local-first release candidate, not production SaaS.

### Must not be promised yet

- direct public deployment;
- per-action governance for every runtime tool;
- exactly-once external side effects;
- complete tenant isolation;
- production-grade shared secret access;
- full coding project delivery and merge automation;
- production Agent marketplace.

## 11. Final judgment

The branch demonstrates real technical and product progress. Its strongest differentiators are now:

```text
machine-facing Agent Gateway
scoped remote workers
cross-runtime evidence ledger
commander/review workflow
Agent Work Method Block
local knowledge index
```

The branch is strategically strong but has crossed the complexity threshold where adding more features without hardening will reduce reliability.

Final decision:

```text
Current status: NOT_READY_TO_MERGE
Next status after blockers and CI: READY_FOR_RC
Target after clean RC: READY_TO_MERGE
```
