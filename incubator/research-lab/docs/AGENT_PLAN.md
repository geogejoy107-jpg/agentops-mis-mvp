# Agent Plan — standalone Research Lab SSH v0.3

```text
Repository: geogejoy107-jpg/agentops-mis-mvp
Reference branch: codex/agent-gateway-kb-demo
Reference commit: 264bee3e8357a74677b1d3421e5e92f129a4eefc
Intended incubator branch: incubator/research-lab-ssh-v0-3
Current milestone: v1.5 READY_TO_MERGE; do not insert into the release line
Current objective: extend the independently usable Research Lab with guarded SSH execution
Relevant approved decisions: D-001 through D-006
Open P0/P1 items: P0-11, P1-05, P1-06
Risks / unknowns: real SSH/GPU evidence is pending; external app write availability must be verified separately
```

```yaml
task_understanding: >-
  Preserve the path-isolated Research Lab and implement the next independently useful lane:
  bounded SSH experiment execution with profile provenance, safe staging, remote evidence
  collection and fail-closed uncertainty handling.
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
  - H-OSBI-001
referenced_bases:
  - Python asyncio
  - SQLite WAL
  - OpenSSH client
  - MLflow / DVC / Slurm as later adapters
proposed_files_to_change:
  - incubator/research-lab/** only
risk_level: medium
approval_required: false
execution_steps:
  - define non-secret SSH server profile registry
  - freeze server capability snapshot into the protocol hash
  - build deterministic allowlisted staging archives
  - execute and collect through a transport adapter
  - persist remote job reference and executor evidence
  - block profile drift and unknown remote state
  - update CLI, reports, examples, docs and tests
verification_plan:
  - compile package/examples/tests
  - preserve v0.2 local behavior
  - loopback SSH end-to-end with bounded concurrency
  - profile-drift negative test
  - traversal/secret/sync-path negative tests
  - remote interruption fail-closed test
  - package, patch and checksum verification
rollback_plan: >-
  Delete the incubator branch/directory or revert the v0.3 patch. No production MIS
  code, schema, UI or canonical project state is touched.
```
