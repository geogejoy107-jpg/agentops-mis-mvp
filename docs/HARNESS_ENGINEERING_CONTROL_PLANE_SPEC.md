# Harness Engineering Control Plane Spec

## Purpose

This spec translates Harness engineering research into enforceable AgentOps MIS
product constraints.

The goal is not to turn AgentOps MIS into a CI/CD clone. The goal is to build a
local-first harness where human operators steer work, agents execute through
typed packets, and every important action becomes verifiable MIS evidence.

## External References

This spec is grounded in the existing research brief:

- `docs/research/HARNESS_ENGINEERING_RESEARCH_BRIEF.md`
- `docs/HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md`

Primary source references used by that brief:

- Harness Open Source repository: `https://github.com/harness/harness`
- Harness Open Source product page: `https://www.harness.io/open-source`
- Harness Policy As Code docs:
  `https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/`
- Harness Services docs:
  `https://developer.harness.io/docs/continuous-delivery/x-platform-cd-features/services/services-overview/`
- Harness Internal Developer Portal docs:
  `https://developer.harness.io/docs/internal-developer-portal/overview`
- Harness IDP System entity docs:
  `https://developer.harness.io/docs/internal-developer-portal/catalog/data-model/system-entity`
- Harness IDP Environment management docs:
  `https://developer.harness.io/docs/internal-developer-portal/environment-management/environments`
- Harness Open Source docs:
  `https://developer.harness.io/docs/open-source/overview`
- OpenAI Harness Engineering field report:
  `https://openai.com/index/harness-engineering/`

## One-Sentence Positioning

AgentOps MIS is a human-AI work delivery control plane: humans approve intent
and risk, agents execute bounded work, and MIS owns the task/run/approval/
evidence/audit ledger.

## Control-Plane Boundary

Harness-style tooling can inspire the delivery surface, but it must not own the
MIS authority model.

First-party AgentOps MIS authority remains:

- workspace
- agent
- task
- agent plan
- run
- tool call
- prepared action
- approval
- runtime event
- evaluation
- memory candidate
- artifact
- delivery report
- audit log

External systems may provide source control, CI, artifacts, hosted developer
environments, runtime execution, traces, or model calls. MIS may ingest only
redacted summaries, stable IDs, source URIs, hashes, counters, and provenance.
Raw prompts, raw responses, credentials, private messages, full transcripts and
local DB contents must not become committed evidence.

## Harness Engineering Principles For AgentOps MIS

### 1. Agents Need A Harness, Not Raw Access

Agents should not infer workflow order from raw CRUD endpoints or browser UI.
They should receive typed, compact packets:

- project/work packet
- loop supervision packet
- agent work packet decision
- plan evidence manifest
- launch packet
- runtime readiness packet
- approval/resume packet
- evidence/report packet

Each packet must include enough IDs, hashes, allowed commands and verification
commands for an agent to act without long chat history.

### 2. Repository Knowledge Is Product Infrastructure

Repository-local docs, specs, runbooks, smokes and acceptance records are part
of the product harness. They are not secondary prose.

Required properties:

- source files are versioned in repo;
- specs point to executable smokes where possible;
- acceptance docs name the exact command evidence;
- stale or unsafe claims are caught by static gates;
- the current worktree can be inspected without external chat transcripts.

### 3. Policy Decisions Must Be First-Class

AgentOps MIS does not need OPA/Rego as a v1.x dependency, but every meaningful
gate should look like a policy decision:

- policy id
- policy version
- target entity
- normalized arguments or summary hash
- decision
- enforcement point
- evidence references
- audit output

Future OPA/Cedar integration is allowed only as a policy adapter. It must not
replace Agent Plan, Approval Wall, scope enforcement, or audit authority.

### 4. Work Delivery Graph Is A Read Model

The Harness Software Delivery Knowledge Graph idea maps to a local MIS work
delivery graph:

```text
workspace -> agent -> task -> agent_plan -> run -> tool_call
          -> prepared_action -> approval -> runtime_event
          -> evaluation -> artifact -> memory_candidate -> audit_log
```

For v1.x this graph is a read model over existing MIS ledgers and hashes, not a
new source of truth.

Harness service/environment/catalog separation maps to AgentOps MIS as a
control-plane split:

- `task`: requested customer or internal work;
- `agent`: accountable worker identity;
- `runtime_connector`: execution location such as Hermes, OpenClaw, Dify,
  local CLI or future remote server;
- `workspace/project`: authority scope;
- `environment`: local demo, dogfood, hosted alpha, customer machine or
  external server context;
- `run/evaluation/audit/artifact`: evidence chain and product claim boundary.

This split should guide open-source-base and experimental-branch intake:
borrow tools and execution contexts, but reimplement or adapt authority
transitions inside MIS.

### 5. Async Commander Mode Is Product Behavior

The product should support the same operating model used to build it:

- multiple safe lanes can be active at once;
- slow runtime/CI/subagent work does not block unrelated verification;
- each lane has a typed packet, owner, state, next command and evidence;
- completed lane evidence can be merged without waiting for every lane.

This should eventually be visible in the Command Center and Agent Gateway
work-packet APIs, not only in Codex chat behavior.

## Execution Contract

Before a governed agent run can become product evidence, the chain must be
legible:

```text
READ
-> PLAN
-> RETRIEVE
-> COMPARE
-> EXECUTE
-> VERIFY
-> RECORD
```

Minimum required readback for Hermes/OpenClaw/OpenClaw-agent dogfood:

- task id and workspace id;
- selected agent id and runtime connector id;
- agent plan id and immutable plan hash;
- work packet decision id/kind/hash;
- runtime trust/readiness state;
- approval/prepared-action state for external side effects;
- run id and tool/evaluation/runtime/audit evidence counts;
- artifact/report ids or explicit "no artifact expected";
- safety readback proving token/prompt/response omission.

## Approval Wall Requirements

Harness-style inline approvals are useful only if AgentOps MIS preserves exact
prepared-action semantics.

The required shape is:

```text
prepared action
-> normalized args
-> action hash
-> checkpoint
-> human/policy approval
-> resume exact action
-> execute once
-> provider result summary/hash
-> audit
```

Generic approval buttons must not be marketed as exact tool-action governance.

## Execution Constraints Layer

The companion execution constraint layer is
`docs/HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md`. It converts this
control-plane doctrine into the machine-consumable contract for agent work:

- required work packet fields;
- READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD gate
  evidence;
- policy decision shape;
- Approval Wall exact-action proof;
- real-runtime proof standards;
- async lane management;
- UI versus CLI/API/MCP responsibility split;
- public product-claim limits.

Use that file when building or reviewing a concrete worker, adapter, CLI/API
packet, or MCP-facing agent surface.

## Runtime Adapter Requirements

Hermes, OpenClaw, Dify, Harness-like systems and future external workers are
runtime adapters, not MIS authorities.

Every adapter must declare:

- observation level;
- live execution requirements;
- approval requirements;
- external write capabilities;
- runtime event ingestion support;
- redaction behavior;
- trust status;
- manual verification command;
- product-claim limit.

Opaque runtimes may execute tasks, but AgentOps MIS must label them as
summary-only until internal tool events are available.

## Local-First Product Slices

The near-term sequence should stay small and verifiable:

1. Bind `agent_work_packet_decision_v1` into `runs/start` for Hermes/OpenClaw.
2. Add a local work delivery graph readback over existing ledger tables.
3. Expose a CLI/API/MCP packet for that graph.
4. Dogfood one real local task through Hermes/OpenClaw with explicit approval
   and summary/hash evidence.
5. Promote verified lessons to memory candidates, never directly to approved
   memory.

Commercial hosted deployment, billing, multi-tenant RBAC expansion, and broad
third-party platform migration remain later lanes unless explicitly
reauthorized.

## Non-Goals

- Do not vendor Harness Open Source into AgentOps MIS.
- Do not replace MIS tasks/runs/approvals/audit with CI/CD pipeline objects.
- Do not add OPA/Rego as a v1.x runtime dependency.
- Do not store raw prompts, raw responses, credentials, private messages, full
  transcripts, DB snapshots or local generated exports.
- Do not claim universal per-action governance for opaque runtimes that do not
  emit internal runtime events.

## Acceptance Requirements

This spec is accepted when:

- it is present at `docs/HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md`;
- the execution layer is present at
  `docs/HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md`;
- `scripts/harness_engineering_control_plane_smoke.py` passes;
- `scripts/harness_engineering_execution_constraints_smoke.py` passes;
- the smoke is included in CI offline safety smokes;
- the smoke is included in `scripts/release_evidence_packet_smoke.py`;
- the release evidence docs list the smoke command;
- no DB, env, token, cache, `dist`, `node_modules` or generated artifact is
  committed.
