# Template + Base Switching Spec

## Concept

AgentOps MIS treats a workspace as a set of canonical local bases plus optional external bases. A template package describes the agent roles, task schema, memory schema, quality gates and approval policy for a use case. The same template can preview bindings to Notion, W&B, Plane, Docmost or Mattermost without moving the canonical ledger.

## Canonical Bases

- `base_local_tasks`
- `base_local_memory`
- `base_local_templates`

## External Bases

- Notion memory/tasks/templates: dry-run connector in v1.2.1.
- W&B observability: planned.
- Plane tasks: planned.
- Docmost knowledge: planned.
- Mattermost ops communication: planned.

## Template Packages

Seeded packages:

- AI software team
- Research and report workflow
- Course project presentation
- Agent operations governance

## Migration Preview

`POST /api/migration/preview` returns:

- Migratable fields.
- Non-migratable local ledger fields.
- Field downgrades.
- Permission changes.
- Required human confirmations.
- Rollback plan.

No external data is written by migration preview.
