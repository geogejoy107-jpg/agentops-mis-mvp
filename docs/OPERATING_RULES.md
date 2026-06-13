# AgentOps MIS Delivery Operating Rules

## Objective

Finish a presentable AgentOps MIS project package today, while allowing parallel Codex threads and branches to accelerate work without corrupting the demo, research narrative, or project memory.

## Current Deadline Context

Class presentation is limited to 10 minutes. The suggested structure is:

- Project introduction: 2 minutes
- System planning, analysis and design: 3 minutes
- Business value and model: 1 minute
- Project highlights: 1 minute
- Frontend/backend demo: 2 minutes

Report and system demo deadline shown in class material: July 3, 23:29.

## Workstreams

### Main Thread

Owns integration and final judgment.

- Keeps the local `agentops-mis-mvp` workspace runnable.
- Reviews and merges outputs from subthreads.
- Updates project memory only for stable decisions.
- Runs final smoke tests.
- Produces final user-facing summary.

### Research Thread

Owns evidence and narrative.

- Uses `gpt-research` source files.
- Uses `broad-community-research` for any new web/community search.
- Produces concise citations, product positioning, competitor framing and risks.
- Does not edit runtime code.

### Architecture Thread

Owns architecture, schema and governance.

- Updates architecture diagrams, object model, API spec and report sections.
- Converts research into implementable control-plane decisions.
- Does not change frontend styling.

### Integration Thread

Owns adapters and data import.

- Implements safe OpenClaw/Hermes/Notion import/export scripts.
- Stores only structured metadata, hashes, status, counts, durations and references.
- Does not ingest credentials, private messages, full transcripts or raw command bodies.

### QA Thread

Owns verification.

- Runs smoke tests, API checks and browser checks.
- Reports bugs with exact file paths and reproduction steps.
- Does not redesign product scope.

## Branch Rules

- Branch names use `codex/` prefix.
- One branch per workstream when work is substantial:
  - `codex/mis-research-pack`
  - `codex/mis-architecture-pack`
  - `codex/mis-integration-notion`
  - `codex/mis-qa-smoke`
- Prefer disjoint write scopes:
  - research: `docs/*`, `outputs/*`
  - architecture: `docs/*`, `sql/*`
  - integration: `server.py`, `scripts/*`, `.env.example`, `docs/API_SPEC.md`
  - frontend: `static/*`
- Merge order:
  1. research/docs
  2. architecture/schema
  3. backend/integration
  4. frontend
  5. QA fixes

## Merge Gates

Before a branch can be merged:

- `python3 -m py_compile server.py scripts/*.py` must pass when scripts exist.
- Local service must start or existing service must answer `/api/dashboard/metrics`.
- New APIs must be documented in `docs/API_SPEC.md`.
- Privacy boundary must be stated for any connector.
- No credential, token, private message body or full transcript may be committed.
- Demo path must remain usable from `README.md`.

## Parallelism Rules

Parallelize:

- research reading
- document drafting
- visual QA
- adapter exploration
- test writing

Do not parallelize conflicting edits to:

- `server.py`
- `static/app.js`
- `sql/schema.sql`
- project memory

## Pro Model Rules

Use Pro/deeper models for:

- broad market research
- canonical schema v2
- Agent IAM / policy architecture
- delegated-execution ledger design
- connector/skill marketplace threat model
- pricing and commercial positioning

Use normal coding model for:

- endpoint implementation
- import/export scripts
- dashboard tables
- smoke tests
- report assembly

## Reporting Cadence

During long runs:

- Main thread reports progress every meaningful milestone.
- Subthreads return short findings and changed file paths.
- Final summary must include what changed, verification, remaining gaps and next action.

## Today Scope Lock

Today is not for polishing UI. Today is for:

- report content
- architecture
- operating rules
- Notion connection foundation
- runnable demo
- presentation story

Figma/UI refinement can start after this package is stable.
