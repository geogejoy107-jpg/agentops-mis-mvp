# Production Customer-Delivery Approval Owner Schema Assumptions

The production `POST /api/mis/agent-gateway/approvals/request` owner is
TypeScript/Postgres code. It does not create or alter schema at request time
and it never falls back to Python in production.

## Required Migration State

Integration must apply the schema lane in this order:

1. `20260724_current_main_commercial_baseline.sql`
2. `20260719_workspace_read_models_v2.sql`
3. `20260719_approval_kind_bindings_v4.sql`
4. `20260724_customer_delivery_run_unique_v5.sql`

Other commercial migrations may run between these files when required by their
declared dependencies. This owner specifically depends on:

- Agent Gateway token and session tables with workspace, agent, scope, status,
  expiry, parent-token, and last-used fields.
- current-main Agent Plan fields `plan_version`, `plan_hash`, `verified_at`, and
  `verification_result_hash`.
- Run fields `agent_plan_id` and `plan_hash`.
- Plan-evidence manifest fields `plan_hash`, `verification_result_hash`,
  `status`, and `verification_json`.
- workspace-bound audit rows from schema v2.
- `approvals.approval_kind` and the v4 immutable binding/evidence-seal triggers.
- partial unique index `idx_approvals_customer_delivery_run_unique` from v5.

The executable assumptions live in
`ui/next-app/src/server/controlPlane/customerDeliverySchema.ts`. A production
request fails closed with `customer_delivery_schema_not_ready` when any
required column, trigger, or unique index is absent.

## Ownership Boundary

- Free Local may proxy only when both deployment mode `free_local` and
  control-plane mode `proxy` are explicitly configured.
- Production resolves the specific Next route before the catch-all and calls
  the TypeScript/Postgres owner directly.
- Production never starts or proxies the Python API for this operation.
- Schema migrations remain owned by the independent schema integration lane.
