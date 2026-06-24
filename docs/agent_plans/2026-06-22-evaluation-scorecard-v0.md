# Agent Plan — Evaluation Scorecard v0

> GitHub Issue: #16  
> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Base branch: `codex/agent-gateway-kb-demo`  
> Plan-creation base: `4a4a96dc079d7d178894902626728648e73441b2`  
> Refreshed execution base: `4baa35e80ffadd8b120f376da246bf23850d3e05`  
> Exact refreshed-base CI run: `27960175149` — success  
> Work branch: `research/evaluation-scorecard-v0`  
> Risk: `low`  
> Approval required: `false` for documentation-only execution  
> Owner authorization: user explicitly requested starting the lane and improving project memory

## Task understanding

Complete Lane A from Notion proposal `P-EVAL-001` by producing a versioned, reviewable evaluation scorecard and current-head baseline. The result must distinguish measured evidence from targets and unknowns, preserve the authority split, and avoid runtime or release-priority changes.

## Referenced specs

- `docs/project/PROJECT_STATE.md`
- `docs/project/DECISIONS.md` — D-001 through D-006
- `docs/project/BACKLOG.md`
- `docs/project/HANDOFF.md`
- `AGENTS.md`
- `PROJECT_SPEC.md`
- `AGENT_WORKFLOW.md`
- `BASE_INDEX.md`
- `docs/V1_5_MERGE_READINESS_CHECKLIST.md`
- `docs/RELEASE_EVIDENCE_PACKET.md`
- GitHub Issue #16

## Referenced memories

- Notion `P-EVAL-001` — MIS parallel evaluation, UAT, and implementation-readiness proposal.
- Notion research note `3876adfd-d920-81bd-bd2a-e3e2d112e2e6`.

Both are candidate context, not canonical authority.

## Referenced bases

- GitHub repository and exact-head CI for code/test facts.
- AgentOps MIS SQLite/API for future run/tool/approval/artifact/evaluation/audit measurements.
- Notion Project Ledger for candidate project memory and review state.
- Course PDF sources for evaluation-method rationale.

## Proposed files to change

- `docs/evaluation/EVALUATION_SCORECARD_V0.md`
- `docs/evaluation/EVALUATION_METRIC_DICTIONARY_V0.yaml`
- `docs/evaluation/EVALUATION_BASELINE_2026-06-22.md`
- `docs/project/EVALUATION_SCORECARD_HANDOFF.md`

Canonical project-state files are intentionally out of scope.

## Relationship check

- `updates`: Notion proposal `P-EVAL-001`, Lane A.
- `supports`: P0 keep-green evidence, P1-03 Command Center BFF, P1-06 retrieval evaluation, future Research Lab Template.
- `duplicate_of`: none found in repository, open issues, or Project Ledger.
- `conflicts_with`: D-006 only if implementation expands runtime/UI behavior on the frozen release branch; this branch is documentation/evidence only.

## Execution steps

1. Define scorecard governance rules and the north-star metric.
2. Define zero-tolerance safety guardrails separately from averaged KPIs.
3. Define technical, governance, workflow, knowledge, user, and economic metrics.
4. Provide formulas, scope, units, authority source, owner, cadence, target, and privacy policy.
5. Record current-head evidence from GitHub and versioned release documents.
6. Mark metrics that require live AgentOps/customer data as `Unknown / not yet measured`.
7. Add task-specific handoff and open a draft PR.
8. Update Notion candidate memory with exact issue, branch, commit, PR, verification, and next action.

## Verification plan

- Every metric has an unambiguous ID and definition.
- Ratio metrics define numerator, denominator, inclusion window, and exclusion rules.
- Each metric names its authoritative source; no source is used outside its authority domain.
- Current values are supported by exact-head CI or versioned evidence.
- Unknown data is not guessed.
- Safety failures remain count metrics with target zero and cannot be hidden in averages.
- No credentials, raw prompts/responses, private transcripts, customer bodies, or runtime logs are added.
- Changed files remain documentation-only and exclude canonical project-state files.

## Rollback plan

Close the draft PR and abandon `research/evaluation-scorecard-v0`. Revert or supersede the Notion candidate task while retaining the evidence history. No runtime state or customer data is changed.
