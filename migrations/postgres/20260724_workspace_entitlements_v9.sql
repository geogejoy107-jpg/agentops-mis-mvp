-- Workspace commercial capabilities and quotas are Postgres-owned. Missing
-- rows remain intentionally unprovisioned so expansion checks fail closed.

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

CREATE TABLE IF NOT EXISTS workspace_entitlements (
    workspace_id TEXT NOT NULL,
    edition TEXT NOT NULL,
    status TEXT NOT NULL,
    capabilities_json JSONB NOT NULL DEFAULT '{}'::JSONB,
    max_agents INTEGER NOT NULL,
    max_active_enrollments INTEGER NOT NULL,
    max_active_sessions_per_agent INTEGER NOT NULL,
    max_monthly_runs INTEGER NOT NULL,
    max_monthly_cost_usd NUMERIC(18,6) NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_by_user_id TEXT,
    CONSTRAINT workspace_entitlements_pkey PRIMARY KEY(workspace_id),
    CONSTRAINT workspace_entitlements_workspace_id_check
        CHECK(workspace_id <> ''),
    CONSTRAINT workspace_entitlements_edition_check CHECK(
        edition IN (
            'free_local','pro_workspace','team_governance','enterprise_byoc'
        )
    ),
    CONSTRAINT workspace_entitlements_status_check CHECK(
        status IN ('active','inactive','suspended','expired')
    ),
    CONSTRAINT workspace_entitlements_capabilities_object_check
        CHECK(jsonb_typeof(capabilities_json)='object'),
    CONSTRAINT workspace_entitlements_enrollment_capability_check CHECK(
        NOT capabilities_json ? 'enrollment_issue'
        OR jsonb_typeof(capabilities_json->'enrollment_issue')='boolean'
    ),
    CONSTRAINT workspace_entitlements_session_capability_check CHECK(
        NOT capabilities_json ? 'session_issue'
        OR jsonb_typeof(capabilities_json->'session_issue')='boolean'
    ),
    CONSTRAINT workspace_entitlements_run_capability_check CHECK(
        NOT capabilities_json ? 'run_start'
        OR jsonb_typeof(capabilities_json->'run_start')='boolean'
    ),
    CONSTRAINT workspace_entitlements_max_agents_check
        CHECK(max_agents >= 0),
    CONSTRAINT workspace_entitlements_max_active_enrollments_check
        CHECK(max_active_enrollments >= 0),
    CONSTRAINT workspace_entitlements_max_active_sessions_check
        CHECK(max_active_sessions_per_agent >= 0),
    CONSTRAINT workspace_entitlements_max_monthly_runs_check
        CHECK(max_monthly_runs >= 0),
    CONSTRAINT workspace_entitlements_max_monthly_cost_check
        CHECK(max_monthly_cost_usd >= 0),
    CONSTRAINT workspace_entitlements_effective_window_check
        CHECK(expires_at IS NULL OR expires_at > effective_at),
    CONSTRAINT workspace_entitlements_update_order_check
        CHECK(updated_at >= created_at),
    CONSTRAINT workspace_entitlements_updated_by_user_id_fkey
        FOREIGN KEY(updated_by_user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_entitlements_updated_by_v9
ON workspace_entitlements(updated_by_user_id)
WHERE updated_by_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_gateway_tokens_workspace_usage_v9
ON agent_gateway_tokens(workspace_id,status,agent_id,expires_at);

CREATE INDEX IF NOT EXISTS idx_gateway_sessions_workspace_usage_v9
ON agent_gateway_sessions(workspace_id,agent_id,status,expires_at);

CREATE INDEX IF NOT EXISTS idx_runs_workspace_monthly_usage_v9
ON runs(workspace_id,started_at)
INCLUDE(cost_usd);
