# AgentOps MIS Evaluation Scorecard v0

> Status: reviewable Lane A deliverable  
> Authority class: candidate specification  
> Canonical: no  
> GitHub Issue: #16  
> Base evidence commit: `4a4a96dc079d7d178894902626728648e73441b2`

## 1. Purpose

This scorecard defines how AgentOps MIS will be evaluated as a management information system and AI-workforce control plane. It turns release checks, runtime evidence, user acceptance, and economic validation into one governed measurement model without treating a passing test, a status transition, or a user impression as interchangeable evidence.

The scorecard is deliberately broader than model accuracy. AgentOps MIS must prove that work is completed through the intended authority chain:

```text
Project Spec / Approved Decision
-> Knowledge Retrieval
-> Agent Plan
-> Task
-> Run
-> Tool Call / Prepared Action
-> Approval
-> Artifact
-> Evaluation
-> Memory Candidate
-> Audit
```

## 2. Authority and evidence rules

| Fact | Authoritative source |
|---|---|
| Repository, branch, commit, PR, diff, CI, tests | GitHub |
| Task/run/tool/approval/artifact/evaluation/audit measurements | AgentOps MIS SQLite/API |
| Reviewed project decisions, risks, backlog, and handoff | Notion Project Ledger plus `docs/project/` |
| User-study observations and survey results | Versioned research artifact with consented, redacted summaries |
| Cost and benefit assumptions | Reviewed economic baseline; assumptions remain separate from realized values |

### Evidence levels

| Level | Meaning | Can establish a current product KPI? |
|---|---|---|
| `E1 exact_head_ci` | A check passed on the exact GitHub commit | Yes, for the tested contract only |
| `E2 versioned_acceptance` | A versioned smoke/checklist defines and has recently demonstrated an acceptance baseline | Yes, with the evidence date and limitations shown |
| `E3 live_ledger` | Aggregated runtime facts from the authoritative MIS ledger | Yes, for the measured workspace/window |
| `E4 user_study` | UAT/usability evidence from representative users | Yes, for the stated sample and scenarios |
| `E5 economic_validation` | Real cost/benefit data from a controlled pilot | Yes, for the stated pilot only |

A lower evidence level must not be silently presented as a higher one. In particular, an `E1` smoke pass does not prove zero real-world incidents, and a proposed target is not a measured baseline.

## 3. Scorecard operating rules

1. **Safety guardrails are not averaged.** One unauthorized external write or credential leak is a failure even if all other KPIs are strong.
2. **Every ratio defines its population.** Numerator, denominator, time window, scope, and exclusions must be recorded.
3. **Synthetic fixtures and real work are separated.** CI/demo tasks do not inflate customer or dogfood completion metrics.
4. **Unknown stays Unknown.** Missing live-ledger, user, or economic data is never inferred from code coverage.
5. **Privacy precedes analysis.** Store counts, durations, statuses, hashes, IDs, and short redacted summaries; do not store raw prompts, responses, secrets, private transcripts, or customer bodies by default.
6. **Scope is mandatory.** Every metric is tagged with workspace, project, environment, branch/commit where relevant, and measurement window.
7. **Targets are reviewed.** Proposed pilot targets are candidate requirements until explicitly approved.

## 4. North-star metric

### `GTCR` — Governed Task Closure Rate

**Question:** Of the governed tasks that entered execution, what proportion reached a reviewable, evidence-complete closure without an unresolved safety violation?

```text
GTCR = governed_tasks_closed_ready / governed_tasks_started
```

### Denominator: `governed_tasks_started`

Count distinct non-synthetic tasks whose first governed run started inside the measurement window and which require the AgentOps authority chain. Exclude:

- CI/smoke fixtures;
- tasks cancelled before any run started;
- imported historical records outside the window;
- explicitly ungoverned local experiments, which must be reported separately.

### Numerator: `governed_tasks_closed_ready`

A denominator task counts as closed-ready only when all applicable conditions hold:

1. the execution run is bound to a verified immutable Agent Plan and matching plan hash;
2. a verified `plan_evidence_manifest` exists;
3. required approvals are resolved, and approval-gated prepared actions are consumed exactly once or explicitly rejected;
4. required tool-call, artifact, evaluation, and audit evidence exists;
5. delivery/evidence report status is ready;
6. no unresolved high/critical safety or scope violation remains;
7. the task/delivery is in a terminal completed/accepted state backed by evidence rather than status alone.

### Source and cadence

- Authoritative source: AgentOps MIS SQLite/API plus `operator evidence-report` semantics.
- Scope: per workspace/project and aggregate local dogfood.
- Cadence: rolling 7 days, rolling 30 days, and milestone snapshot.
- Owner: Product owner + Evaluation steward.
- Initial target: establish a clean baseline before setting a production target.

## 5. Zero-tolerance guardrails

| Metric ID | Definition | Target | Authoritative source |
|---|---|---:|---|
| `SAFE-EXT-01` | Unauthorized external side effects | `0` | Prepared actions, tool calls, approvals, audit |
| `SAFE-SEC-01` | Credential/secret disclosure events in governed surfaces | `0` | Security evaluations and audit |
| `SAFE-SCOPE-01` | Confirmed workspace/project/agent scope breaches | `0` | Gateway/audit/security incident records |
| `SAFE-PLAN-01` | Runs started without an applicable verified plan | `0` | Runs, plans, plan verification |
| `SAFE-APPR-01` | Agent self-approval or approval-role bypass events | `0` | Plans, approvals, audit actors |
| `SAFE-REPLAY-01` | Prepared-action duplicate side effects/replays | `0` | Prepared actions, side-effect IDs, audit |
| `SAFE-DATA-01` | Raw private prompt/response/customer body persisted contrary to policy | `0` | Storage audit and redaction evaluation |

A guardrail must report both test-gate status and observed live incident count. A passing synthetic test does not substitute for live incident measurement.

## 6. KPI portfolio

### 6.1 Technical reliability and responsiveness

| Metric ID | Metric | Formula / unit | Initial target |
|---|---|---|---|
| `TECH-CI-01` | Exact-head required-check pass rate | successful required checks / required checks | `100%` |
| `TECH-DB-01` | SQLite locked/busy failure count | count per window | `0` |
| `TECH-READ-01` | Ordinary control-plane read p95 | milliseconds | `<150 ms` |
| `TECH-SCOPE-01` | Scoped queue/knowledge read p95 | milliseconds | `<200 ms` |
| `TECH-WORK-01` | Workflow accepted latency | milliseconds | `<300 ms` |
| `TECH-APPR-01` | Approval decision latency | milliseconds | `<300 ms` |
| `TECH-CMD-01` | Useful command-center summary latency | milliseconds | `<1,000 ms` |
| `TECH-UI-01` | AI Employees initial API reads | request count | `<=32` |
| `TECH-REC-01` | Recovery success rate | recovered failures / eligible recovery attempts | baseline first |

### 6.2 Governance and evidence integrity

| Metric ID | Metric | Formula / unit | Initial target |
|---|---|---|---|
| `GOV-PLAN-01` | Verified-plan run rate | governed runs with verified matching plan / governed runs | `100%` |
| `GOV-EVID-01` | Evidence-ready delivery rate | deliveries with ready evidence report / governed deliveries | baseline first |
| `GOV-MANI-01` | Verified manifest coverage | governed runs with verified plan-evidence manifest / governed runs | `100%` |
| `GOV-APPR-01` | Exact prepared-action coverage | high-risk external actions using prepared-action gate / eligible actions | `100%` |
| `GOV-PROV-01` | Provenance coverage | evidence items with source ID/path/hash/scope / evidence items requiring provenance | `100%` |
| `GOV-REMED-01` | Evidence remediation first-pass success | gaps closed on first explicit remediation / remediation attempts | baseline first |

### 6.3 Workflow effectiveness

| Metric ID | Metric | Formula / unit | Initial target |
|---|---|---|---|
| `FLOW-GTCR-01` | Governed Task Closure Rate | closed-ready governed tasks / governed tasks started | baseline first |
| `FLOW-CYCLE-01` | Governed task cycle time | median and p95 from first governed run to closure | baseline first |
| `FLOW-WAIT-01` | Approval wait share | approval-wait duration / total task cycle duration | baseline first |
| `FLOW-RETRY-01` | Retry rate | runs with retry / governed runs | baseline first |
| `FLOW-HUMAN-01` | Human intervention rate | tasks needing unplanned human recovery / governed tasks | baseline first |
| `FLOW-STALE-01` | Stale-run recovery age | median/p95 time from stale detection to resolution | baseline first |

### 6.4 Knowledge quality

| Metric ID | Metric | Formula / unit | Initial target |
|---|---|---|---|
| `KNOW-R5-01` | Recall@5 | relevant queries with expected item in top 5 / test queries | `>=0.95` |
| `KNOW-MRR-01` | Mean reciprocal rank | mean reciprocal rank across approved test set | `>=0.90` |
| `KNOW-P95-01` | Local retrieval p95 | milliseconds | `<200 ms`; current smoke budget is tighter |
| `KNOW-PROV-01` | Retrieval provenance coverage | results with path/hash/scope/retrieval ID / returned results | `100%` |
| `KNOW-SCOPE-01` | Unauthorized retrieval count | confirmed unauthorized results | `0` |
| `KNOW-FRESH-01` | Index freshness lag | source update to searchable version, minutes | baseline first |

### 6.5 User acceptance and usability

These metrics require Lane B evidence and must remain Unknown until representative UAT occurs.

| Metric ID | Metric | Formula / unit | Proposed pilot target |
|---|---|---|---|
| `USER-TASK-01` | Scenario completion rate | completed scenarios / attempted scenarios | `>=85%` |
| `USER-FTS-01` | Time to first governed success | median minutes | baseline first |
| `USER-REC-01` | User recovery success | recovered error scenarios / attempted recovery scenarios | `>=80%` |
| `USER-SUS-01` | System Usability Scale | 0–100 | `>=70` candidate target |
| `USER-CSAT-01` | Task-level CSAT | 1–5 | `>=4.0` candidate target |

### 6.6 Economic and operational value

These metrics require Lane D/pilot evidence and must remain assumptions until measured.

| Metric ID | Metric | Formula / unit | Initial target |
|---|---|---|---|
| `ECON-HUMAN-01` | Human minutes per governed closure | human active minutes / closed-ready task | baseline first |
| `ECON-API-01` | Model/API cost per governed closure | attributable model/API cost / closed-ready task | baseline first |
| `ECON-AUDIT-01` | Audit preparation time | minutes to produce accepted evidence packet | baseline first |
| `ECON-REWORK-01` | Rework rate | reopened or redone deliveries / deliveries | baseline first |
| `ECON-TCO-01` | Five-year TCO model | CapEx + OpEx + migration + training + transition | assumption register first |
| `ECON-ROI-01` | Realized pilot ROI | (validated benefit - validated cost) / validated cost | do not set before pilot |

## 7. Measurement windows and segmentation

Minimum dimensions:

- `environment`: CI, local demo, dogfood, customer pilot;
- `workspace_id` and `project_id` where applicable;
- `runtime_adapter`: mock, Hermes, OpenClaw, Codex, other;
- `risk_level`;
- `task_template` or workflow type;
- `branch` and `commit` for code-dependent evidence;
- `window_start` and `window_end`;
- `synthetic` boolean.

Aggregate metrics must retain drill-down to these dimensions without exposing raw private content.

## 8. Reporting cadence

- **Per commit/PR:** exact-head CI, release guardrails, retrieval/performance acceptance.
- **Weekly dogfood:** GTCR, governance coverage, cycle/wait/retry/recovery, incident counts.
- **Per UAT round:** scenario completion, time to first success, recovery, SUS, CSAT.
- **Monthly/pilot milestone:** human effort, API cost, audit preparation, rework, TCO/ROI assumptions and realized evidence.

## 9. Current baseline

The first baseline is recorded in `docs/evaluation/EVALUATION_BASELINE_2026-06-22.md`. It intentionally separates exact-head CI facts, versioned acceptance evidence, and metrics that are not yet measurable from the available authoritative sources.

## 10. Exit criteria for Lane A

Lane A is ready for review when:

1. the scorecard, machine-readable dictionary, baseline, and handoff exist on an isolated branch;
2. every metric names its formula, source, scope, owner/cadence, target state, and privacy boundary;
3. exact-head evidence is linked and unsupported values are Unknown;
4. zero-tolerance guardrails are explicit;
5. a draft PR and Notion candidate task preserve the evidence trail;
6. no runtime behavior, release priority, or canonical state has changed.
