# Evaluation Baseline — 2026-06-22

> Baseline scope: AgentOps MIS v1.5 development line  
> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Branch: `codex/agent-gateway-kb-demo`  
> Exact evaluated commit: `4a4a96dc079d7d178894902626728648e73441b2`  
> GitHub Actions run: `27958721483` (`AgentOps MIS CI`, run 326)  
> Baseline method: exact-head GitHub evidence plus versioned acceptance evidence  
> Live AgentOps MIS/customer dataset access in this work cycle: unavailable

## 1. Executive baseline

The exact development HEAD had both required CI jobs complete successfully:

| Required check | Exact-head result |
|---|---|
| Backend deterministic smokes | success |
| UI build | success |

The versioned merge-readiness checklist is marked `READY_TO_MERGE`. This baseline does not replace the strict runtime-derived release packet or claim that a later commit remains green.

## 2. Measured and versioned acceptance evidence

| Metric ID | Baseline | Evidence level | Source | Qualification |
|---|---:|---|---|---|
| `TECH-CI-01` Exact-head required-check pass rate | `2 / 2 = 100%` | `E1` | GitHub Actions run `27958721483` | Exact commit only |
| Release checklist state | `READY_TO_MERGE` | `E2` | `docs/V1_5_MERGE_READINESS_CHECKLIST.md` | Strict release packet remains runtime-derived |
| `TECH-DB-01` SQLite locked/busy failures | `0` in acceptance concurrency baseline | `E2` | Merge-readiness checklist and SQLite smokes | Not a live operational incident count |
| SQLite concurrent read acceptance | `100` concurrent reads pass | `E2` | `scripts/sqlite_reliability_smoke.py` contract | Isolated local acceptance |
| SQLite concurrent short-write acceptance | `20` concurrent writes pass | `E2` | `scripts/sqlite_reliability_smoke.py` contract | Isolated local acceptance |
| Mixed SQLite path acceptance | heartbeat + knowledge + queue + approval pass | `E2` | Versioned checklist | Isolated local acceptance |
| `TECH-UI-01` Initial AI Employees API reads | `29`, budget `<=32` | `E2` | `scripts/ai_employees_responsiveness_smoke.py` contract | Versioned acceptance baseline |
| Core command-center readiness | under `1.5 s` budget | `E2` | Responsiveness smoke/checklist | Exact observed number is not stored in this baseline |
| Critical command-center endpoint | under `1 s` budget | `E2` | Responsiveness smoke/checklist | Exact observed number is not stored in this baseline |
| Background panel completion | under `2 s` budget | `E2` | Responsiveness smoke/checklist | Exact observed number is not stored in this baseline |
| `KNOW-R5-01` Recall@5 | `1.0` | `E2` | `scripts/knowledge_retrieval_quality_smoke.py` versioned baseline | Five-query bilingual set; not a broad customer corpus |
| `KNOW-MRR-01` MRR | `1.0` | `E2` | Retrieval-quality smoke/checklist | Same bounded test set |
| `KNOW-P95-01` Local retrieval p95 | `<20 ms` | `E2` | Retrieval-quality smoke/checklist | Isolated local run across 85+ documents |
| Retrieval provenance contract | path + hash + scope + retrieval ID required | `E2` | Knowledge acceptance checklist | Live coverage ratio not yet aggregated |

## 3. Guardrail status: test evidence versus live measurement

A guardrail has two separate fields:

1. **Acceptance gate** — does the exact-head test suite enforce the contract?
2. **Observed live incidents** — how many violations occurred in actual dogfood/customer work?

| Guardrail | Acceptance gate on exact-head CI | Observed live incidents |
|---|---|---|
| Unverified-plan run prevention | pass through deterministic suite | `Unknown` |
| Agent self-approval prevention | pass through deterministic suite | `Unknown` |
| Prepared-action exact-once/replay prevention | pass through deterministic suite | `Unknown` |
| External connector/runtime inventory gate | pass through deterministic suite | `Unknown` |
| Redaction/secret safety | pass through deterministic suite | `Unknown` |
| Workspace/collaborator scope isolation | pass through deterministic suite | `Unknown` |
| Knowledge scope isolation | pass through deterministic suite | `Unknown` |

`Unknown` is intentional. GitHub can prove the tested contract passed; only the AgentOps MIS ledger or an incident register can prove live event counts.

## 4. Metrics currently Unknown

The following values cannot be honestly computed from GitHub code/test evidence alone:

### Live governance and workflow

- `FLOW-GTCR-01` Governed Task Closure Rate.
- `GOV-PLAN-01` Verified-plan run rate.
- `GOV-MANI-01` Verified plan-evidence manifest coverage.
- `GOV-APPR-01` Exact prepared-action coverage in real work.
- `GOV-PROV-01` Live evidence provenance coverage.
- Governed task cycle time, approval wait share, retry rate, unplanned human intervention, and stale-run recovery age.

Required source: AgentOps MIS SQLite/API over a named workspace, project, environment, and measurement window.

### User acceptance

- representative scenario completion rate;
- time to first governed success;
- recovery success;
- SUS;
- CSAT.

Required source: Lane B UAT with representative roles, scenarios, sample definition, and redacted research artifact.

### Economic value

- human minutes per governed closure;
- model/API cost per governed closure;
- audit preparation time;
- rework avoided;
- realized TCO/ROI.

Required source: Lane D/pilot economic baseline. No ROI claim is supported yet.

## 5. Baseline quality and limitations

1. The repository branch advanced substantially during the day; this baseline is pinned to one exact commit.
2. The CI result is authoritative for tests, not for live operational incidents.
3. Retrieval quality is based on a small bilingual deterministic set and must be extended before broader quality claims.
4. UI responsiveness values are acceptance budgets and recent passing ranges; the exact latency distribution is not persisted here.
5. No raw prompts, responses, credentials, customer bodies, or private transcripts were collected for this baseline.
6. Hosted SaaS, unattended high-impact actions, billing, and enterprise production fleet claims remain out of scope.

## 6. Next measurement action

Run a read-only Lane A data-extraction pass against an explicitly selected local dogfood AgentOps MIS database/API and produce only aggregate counts, durations, statuses, IDs, and hashes. Before that access exists, the live-ledger fields remain `Unknown` rather than estimated.
