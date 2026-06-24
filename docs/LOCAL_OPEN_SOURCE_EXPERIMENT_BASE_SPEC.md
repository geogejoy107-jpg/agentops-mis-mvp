# Local Open Source Experiment Base Spec

## Purpose

The local Open Source Experiment Base turns open-source references and runtime
experiments into reviewable AgentOps MIS evidence. It is a local-first product
surface for deciding what to borrow, what to adapt, what to reject, and what
must remain first-party MIS authority code.

This is not a new runtime and not a third task authority. It uses the existing
Agent Work Method Block, Knowledge Index, Agent Gateway, Agent Plan,
Evaluation Case, Artifact, Memory, and Audit surfaces.

## Positioning

One sentence:

> AgentOps MIS can borrow open-source tooling and methods, but every experiment
> must land as scoped local MIS evidence before it changes product direction.

## Authority Boundary

Open-source projects may provide:

- UI and workflow reference patterns.
- Runtime adapter ideas.
- Retrieval, CI, packaging, and security tooling.
- Experiment inputs and comparison baselines.
- Local-only demo inspiration.

Open-source projects must not own:

- workspace identity
- agent identity
- tasks
- runs
- approvals
- prepared actions
- memories
- evaluations
- artifacts
- audit logs
- delivery status
- commercial/customer authority

When an experiment uses an external project, MIS stores only summary, hashes,
safe ids, source refs, evaluation results, memory candidates, and audit
metadata. Raw prompts, raw responses, private transcripts, credentials,
customer files, and third-party asset dumps are not experiment evidence.

## Local Layers

### 1. Reference Atlas

Primary files:

- `docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md`
- `docs/OPEN_SOURCE_UI_REFERENCE_ATLAS.md`
- `docs/RESEARCH_REFERENCES.md`
- `docs/THIRD_PARTY_NOTICES.md`
- `docs/RELEASE_PROVENANCE.md`

Role:

Define what can be studied, what can be borrowed, and what must remain
reference-only.

### 2. Knowledge Base

Primary paths:

- `knowledge/shared/`
- `knowledge/bases/`
- `knowledge/runbooks/`
- `GET /api/knowledge/search`
- `GET /api/agent-gateway/knowledge/evidence-packet`
- `agentops knowledge search`
- `agentops knowledge evidence-packet`

Role:

Make reference notes searchable by agents while preserving provenance and raw
content omission. The knowledge index is local SQLite FTS5 first; embeddings
and vector databases remain later upgrades.

### 3. Experiment Intake

Every local experiment should have:

- a short experiment id
- source reference
- borrowed idea
- first-party MIS module touched
- authority boundary preserved
- expected evidence
- rollback or rejection rule

Suggested id shape:

```text
exp_os_<project>_<topic>_<yyyymmdd>
```

### 4. Agent Plan and Evidence Binding

Experiments that change code or product behavior must use:

- `agentops agent-plan create`
- `agentops agent-plan verify`
- `agentops plan-evidence create`
- `agentops plan-evidence verify`

The plan must name referenced specs, knowledge/base notes, intended files,
verification commands, risk level, and rollback plan.

### 5. Evaluation Case Loop

Experiments should become reusable checks when they expose a product risk or
repeatable product behavior:

- `agentops eval propose-case`
- `agentops eval approve-case`
- `agentops eval run-cases`
- `agentops eval case-runs`
- `agentops eval remediate-case-run`

Evaluation cases are the local regression bridge between "we learned this from
an experiment" and "the product keeps this behavior green."

### 6. Runtime Experiment Lane

Existing local runtime experiment surfaces:

- `scripts/openclaw_v1_experiment.py`
- `agentops workflow hermes-openclaw-loop`
- `scripts/hermes_openclaw_loop.py`
- `scripts/customer_worker_real_runtime_acceptance.py`
- `scripts/local_runtime_acceptance.py`

Rules:

- Live Hermes/OpenClaw/Agnesfallback runs require explicit confirmation.
- Runtime outputs are ledger-summary-only unless a route explicitly allows a
  prepared-action exact-resume path.
- Experiments must record run/tool/evaluation/runtime/audit evidence or stay
  labeled as research notes, not product proof.

### 7. Local Readiness and Release Gate

Operators should use:

```bash
agentops local readiness
python3 scripts/local_open_source_experiment_base_smoke.py
python3 scripts/open_source_adoption_boundary_smoke.py
python3 scripts/knowledge_retrieval_quality_smoke.py
python3 scripts/evaluation_case_candidate_smoke.py
```

The first command checks the running local product. The smoke commands check
that the local open-source/experiment base remains wired into code, CLI, docs,
and CI.

## Experiment Lifecycle

```text
INTAKE
  -> record source reference and hypothesis
KNOWLEDGE
  -> add or update safe base note / runbook / reference doc
PLAN
  -> create and verify Agent Plan when code/product behavior changes
EXECUTE
  -> run local smoke, mock worker, or explicitly confirmed runtime experiment
EVALUATE
  -> submit evaluation or propose evaluation case
RECORD
  -> artifact summary/hash, memory candidate, audit evidence
DECIDE
  -> adopt as first-party code, keep as reference-only, reject, or defer
```

## Recommended Local Experiment Types

| Type | Example | Required evidence |
| --- | --- | --- |
| Runtime adapter | OpenClaw/Hermes probe or worker loop | run, tool call, evaluation, runtime event, audit |
| UI reference | Plane/Langfuse/Star Office pattern | reference note, UI smoke, license/provenance proof |
| Retrieval method | FTS5 quality baseline, repo-map localization | knowledge evidence packet, retrieval quality smoke |
| Governance method | LangGraph checkpoint, Agent Plan binding | Agent Plan, prepared-action/evidence manifest smoke |
| Customer workflow | Knowledge Q&A bot, UI review task | task/run/artifact/evaluation/approval/audit |

## Acceptance For v1

- Open-source adoption boundary is documented and checked.
- Knowledge base has shared rules, base notes, and runbook entries.
- CLI exposes knowledge, evaluation case, Agent Plan, plan-evidence, and local
  readiness commands.
- Runtime experiment scripts are present and confirmation-gated.
- Evaluation case APIs and CLI commands are present.
- CI runs a local open-source experiment base smoke without live providers.
- No experiment path requires tokens, raw private transcripts, third-party asset
  dumps, node_modules, dist, local DBs, or generated runtime artifacts.

## Non-Goals

- No hosted SaaS claims.
- No automatic external web ingestion.
- No new vector database requirement.
- No third-party UI asset adoption for commercial use.
- No Dify/Notion live sync as part of this base.
- No replacement of MIS authority objects with an open-source framework.

## Next Version Ideas

- Add an `/api/experiments/local-base/status` read-only endpoint.
- Add a browser Experiment Base page that reads existing local readiness,
  knowledge, evaluation case, and artifact APIs.
- Add a structured `experiments/` directory for curated local experiment
  manifests.
- Add optional current-source research refresh through approved search tools,
  still requiring human review before memory or product adoption.
