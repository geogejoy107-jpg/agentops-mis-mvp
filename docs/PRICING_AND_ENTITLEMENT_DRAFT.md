# Pricing And Entitlement Draft

This draft is a product boundary, not a billing integration. Commercial
migration should add local edition/capability gates before any external payment
provider. Local development and Free Local must remain runnable without network
billing calls.

## Free Local

- Single local workspace.
- SQLite ledger.
- Mock runtime, OpenClaw import, Hermes health, Notion dry-run.
- Manual export only.
- Local-only admin/dev mode.
- No hosted multi-tenant features.

## Pro Workspace

- Multiple projects.
- Runtime connector profiles.
- Notion confirmed export and richer external base sync.
- Demo/report templates.
- Longer audit retention.
- Configurable customer task templates.
- Local license/edition config before billing integration.

## Team Governance

- RBAC.
- Approval policies.
- Connector scopes.
- Agent performance reviews.
- Quality gate dashboards.
- Shared organizational memory review.
- Workspace isolation enforcement.
- Scoped agent sessions and enrollment approval policies.

## Enterprise / BYOC

- Self-host or private cloud.
- SSO.
- Postgres.
- Retention controls.
- Signed audit exports.
- Custom runtime and tool connector SDK.
- Private connector trust registry.
- Backup/restore and deployment health evidence.
- No raw secrets, raw prompts, raw model responses, or private transcripts by default.

## Metering Candidates

- Managed agents.
- Monthly runs.
- Tool calls.
- External connector sync events.
- Retained audit events.
- Evaluation jobs.

## Enforcement Order

1. Read-only edition status and capability matrix.
2. Fail-closed gates for clearly commercial capabilities.
3. Audit evidence for blocked/allowed gated actions.
4. Local license/config file or signed entitlement document.
5. Billing provider integration only after the product gates are stable.
