# Agent Plan — Research Lab provenance integrity v0.3.1

```text
Repository: geogejoy107-jpg/agentops-mis-mvp
Target branch: main
Verified target commit: 34ee0301fa1e49c6f48c481727a197797744f122
Working branch: incubator/research-lab-ssh-v0-3
Current milestone: v1.5 merged; keep P0 gates green while productization continues
Current objective: upload the complete standalone module and absorb provenance patterns without authority transfer
Relevant approved decisions: D-001 through D-006
Open P0/P1 items: P0-11; P1-05; P1-06
Risks / unknowns: real SSH/GPU evidence is pending; optional adapters are not yet integrated
```

```yaml
task_understanding: >-
  Complete the path-isolated Research Lab source slice and adapt selected MLflow,
  DVC, Hydra, Slurm/Submitit, and Optuna concepts into first-party provenance and
  adapter boundaries without moving scientific governance into an external system.
referenced_specs:
  - docs/project/PROJECT_STATE.md
  - docs/project/DECISIONS.md
  - docs/project/BACKLOG.md
  - docs/project/HANDOFF.md
  - AGENTS.md
  - PROJECT_SPEC.md
  - AGENT_WORKFLOW.md
  - BASE_INDEX.md
  - docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md
referenced_memories:
  - P-RLAB-001
  - E-RLAB-SSH-001
  - H-OSBI-001
referenced_bases:
  - SQLite WAL
  - Python asyncio
  - OpenSSH
  - MLflow Tracking
  - DVC experiment/data/model versioning
  - Hydra multirun and resolved config
  - Slurm job arrays
  - Submitit executor/checkpoint patterns
  - Optuna ask/tell
proposed_files_to_change:
  - incubator/research-lab/**
  - .github/workflows/research-lab-incubator.yml
risk_level: medium
approval_required: false
execution_steps:
  - finish and test ProvenanceSpec
  - bind code/data/model/environment/resolved-config references to the protocol hash
  - require provenance for strict scientific stages
  - propagate frozen hashes into local and SSH runtime actuals
  - upload complete standalone source and tests
  - add path-scoped CI
  - update GitHub PR and Notion evidence
verification_plan:
  - compile package/examples/tests
  - run all deterministic tests
  - execute one local confirmatory CLI workflow
  - verify strict provenance negative cases
  - verify PR diff stays under incubator plus dedicated workflow
rollback_plan: >-
  Revert the v0.3.1 commits or delete the incubator branch. The module never writes
  directly into the MIS production database or changes canonical project state.
```

## Open-source adoption record

```text
Reference: MLflow Tracking
Borrowed idea: separate runs, models, datasets, metrics, and stable external IDs
First-party module touched: ProvenanceSpec and future TrackerAdapter boundary
Authority boundary preserved: Research Lab owns protocol, Trial, deviation, and claim gate
Verification: provenance tests and external-ID-only design

Reference: DVC / Hydra
Borrowed idea: explicit versioned inputs and fully resolved sweep configuration
First-party module touched: provenance datasets/models/environment/resolved_config
Authority boundary preserved: references are frozen metadata, not external scientific authority
Verification: canonical hashes and strict-stage negative tests

Reference: Slurm / Submitit / Optuna
Borrowed idea: scheduler identities, bounded arrays, executor abstraction, ask/tell separation
First-party module touched: future SchedulerAdapter and SearchController
Authority boundary preserved: Trial/JobAttempt and claim eligibility remain local first-party state
Verification: design contract only in this slice; no integration claim
```
