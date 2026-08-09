# ADR: Template Platform v1 shared production contract

Status: Candidate contract freeze

Canonical: false

Base: `origin/main@99ce51d693f1d646ea84acc2f7f376bde1a95a9a`

## Decision

AgentOps MIS remains the sole authority for Workspace, Project, Agent, Task,
Plan, Run, ToolCall, PreparedAction, Approval, Artifact, Evaluation, Memory
Review, Audit, Evidence, Project Delta, Identity and Permission. Templates may
own domain records but only reference those Core identities.

The v1 shared contract versions are:

```yaml
template_manifest_version: template-manifest/v1
shared_api_version: template-platform-api/v1
event_schema_version: template-event/v1
runtime_contract_version: openjiuwen-runtime/v1
migration_contract_version: template-migration/v1
profile_contract_version: product-profile/v1
```

The machine-readable schemas and dependency-free semantic validator live under
`template_runtime/`. JSON Schema establishes portable shape validation; Python
validation additionally enforces Core authority and template namespace rules.

## Identity and namespaces

- Published package identity: `publisher + template_id + version`.
- Workspace installation identity: `workspace_id + template_id`, with one
  active version and immutable historical receipts.
- Template IDs use lowercase snake case.
- Every workflow, agent, skill, tool, policy, evaluator, UI extension, report,
  fixture, migration and permission ID begins with `<template_id>.`.
- Events use `<template_id>.<event_name>` and carry workspace, correlation,
  idempotency, sequence and evidence fields.
- Files use `templates/<template_id>/`, `profiles/<profile_id>/`,
  `tests/templates/<template_id>/` and `docs/templates/<template_id>/`.

## Lifecycle and side effects

The state machine in `template_runtime.contracts` is the shared lifecycle
authority. Install, activation, upgrade, migration, rollback and uninstall have
explicit execution, readback and receipt-pending states. Separate Approval is
required where policy requires it. Failure/rejection/expiry states are explicit;
no transition implies success. Historical records are archived, not silently
deleted.

External effects follow `prepare -> approval -> execute once -> readback ->
receipt`. Domain templates cannot implement a second approval, memory, event,
or audit ledger.

## Shared openJiuwen runtime boundary

`openjiuwen-runtime/v1` is first-party MIS integration around an exactly pinned
upstream distribution. It must provide provider/model routing, Agent and
JiuwenSwarm team/skill lifecycle, allow/ask/deny tools, MIS PreparedAction and
Approval mapping, structured outputs, interrupt/resume/restart/reconcile,
transactional runtime events, token/cost/latency, and secret/raw-content
redaction. Missing or incompatible upstreams report unavailable/degraded/failed
and never fall back to mock success.

## Domain path ownership

Research may write only:

- `templates/research_lab/**`
- `profiles/bdci_2026_research/**`
- `profiles/research_lab_full/**`
- `tests/templates/research_lab/**`
- `docs/templates/research_lab/**`

Career may write only:

- `templates/career_sim/**`
- `profiles/bdci_2026_career/**`
- `tests/templates/career_sim/**`
- `docs/templates/career_sim/**`

Quant may write only:

- `templates/quant_research/**`
- `profiles/bdci_2026_quant/**`
- `tests/templates/quant_research/**`
- `docs/templates/quant_research/**`

All `agentops_mis_core/**`, `agentops_mis_runtime/**`, `agentops_mis_cli/**`,
`template_runtime/**`, shared server/UI/migrations and shared ADR paths are C0
owned. A domain line requests changes instead of editing these paths.

## Required gates

Before domain merge: manifest/schema/semantic validation, namespace and Core
authority negative tests, profile validation, path-scope review, permissions,
secret scan, domain migrations, restart/recovery and line E2E.

Before release: real install/activate/disable/upgrade/rollback/uninstall,
transactional outbox replay/DLQ, shared runtime, UI/API/CLI, old Research data
migration, cross-template isolation, security/SBOM, exact-head real Research,
Career and Quant integrations, MIS ledger readback and verified release receipt.

Real GPU, official Career simulator, official Quant data and governed deployment
access are external-resource gates. They remain truthful blocker lanes while all
independent implementation and tests continue; mocks cannot satisfy them.
