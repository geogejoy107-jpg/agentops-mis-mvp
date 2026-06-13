# Research To Product Traceability

## Research Themes

- Agent observability and run ledger.
- Human-in-the-loop approvals and quality gates.
- Organizational memory with review status and provenance.
- Agent IAM, non-human identity and audit.
- External work bases such as Notion, task tools and observability tools.

## Implemented In v1.2.1

- Run ledger: `runs`, `tool_calls`, `runtime_events`.
- Quality gates: rule-based evaluations for imported/probe/demo runs.
- Human approval model: `approvals` and high-risk tool statuses.
- Memory governance: `memories` with candidate/approved/rejected states.
- Audit: `audit_logs` with before/after hashes and metadata hashes.
- External bases: `bases`, `connectors`, `connector_scopes`, `sync_events`.
- Template portability: `template_packages`, `template_bindings`, `migration_runs`.

## Deliberately Deferred

- Multi-tenant RBAC.
- Production OAuth.
- Connector marketplace trust registry.
- Append-only cryptographic ledger enforcement.
- Postgres migrations.
- Next.js visual redesign.

## Demo Claim Boundary

The demo proves the control-plane shape and local safety posture. It does not claim production-grade SaaS governance yet.
