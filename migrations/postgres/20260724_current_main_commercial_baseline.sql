-- First-party PostgreSQL baseline for the minimum current-main commercial
-- Worker/Human authority graph. This is explicit production DDL; it is not
-- generated from the local SQLite schema at bootstrap time.

CREATE TABLE IF NOT EXISTS agentops_schema_migrations (
    component TEXT NOT NULL,
    version TEXT NOT NULL,
    schema_contract TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    CONSTRAINT agentops_schema_migrations_pkey PRIMARY KEY(component),
    CONSTRAINT agentops_schema_migrations_checksum_check
        CHECK(checksum ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CONSTRAINT users_pkey PRIMARY KEY(user_id)
);

CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    description TEXT,
    runtime_type TEXT NOT NULL,
    model_provider TEXT,
    model_name TEXT,
    status TEXT NOT NULL,
    permission_level TEXT NOT NULL,
    allowed_tools TEXT NOT NULL,
    budget_limit_usd REAL NOT NULL DEFAULT 0,
    owner_user_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT agents_pkey PRIMARY KEY(agent_id),
    CONSTRAINT agents_runtime_type_check CHECK(
        runtime_type IN (
            'mock','claude_code','codex','openhands','crewai','langgraph',
            'openclaw','hermes'
        )
    ),
    CONSTRAINT agents_status_check
        CHECK(status IN ('idle','running','paused','error','disabled')),
    CONSTRAINT agents_owner_user_id_fkey
        FOREIGN KEY(owner_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    title TEXT NOT NULL,
    description TEXT,
    requester_id TEXT,
    owner_agent_id TEXT,
    collaborator_agent_ids TEXT DEFAULT '[]',
    status TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    due_date TEXT,
    acceptance_criteria TEXT,
    risk_level TEXT NOT NULL,
    budget_limit_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT tasks_pkey PRIMARY KEY(task_id),
    CONSTRAINT tasks_status_check CHECK(
        status IN (
            'backlog','planned','running','waiting_approval','blocked',
            'completed','failed','canceled'
        )
    ),
    CONSTRAINT tasks_risk_level_check
        CHECK(risk_level IN ('low','medium','high','critical')),
    CONSTRAINT tasks_requester_id_fkey
        FOREIGN KEY(requester_id) REFERENCES users(user_id),
    CONSTRAINT tasks_owner_agent_id_fkey
        FOREIGN KEY(owner_agent_id) REFERENCES agents(agent_id)
);

-- agent_plans and runs intentionally form a two-way authority binding. Create
-- the plan side first, then add its run foreign key after runs exists.
CREATE TABLE IF NOT EXISTS agent_plans (
    plan_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    task_id TEXT,
    run_id TEXT,
    agent_id TEXT NOT NULL,
    task_understanding TEXT NOT NULL,
    referenced_specs_json TEXT NOT NULL DEFAULT '[]',
    referenced_memories_json TEXT NOT NULL DEFAULT '[]',
    referenced_bases_json TEXT NOT NULL DEFAULT '[]',
    proposed_files_to_change_json TEXT NOT NULL DEFAULT '[]',
    risk_level TEXT NOT NULL,
    approval_required INTEGER NOT NULL DEFAULT 0,
    execution_steps_json TEXT NOT NULL DEFAULT '[]',
    verification_plan TEXT,
    rollback_plan TEXT,
    status TEXT NOT NULL,
    plan_version INTEGER NOT NULL DEFAULT 1,
    plan_hash TEXT,
    verified_at TEXT,
    verification_result_hash TEXT,
    approval_id TEXT,
    approved_by_user_id TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT agent_plans_pkey PRIMARY KEY(plan_id),
    CONSTRAINT agent_plans_risk_level_check
        CHECK(risk_level IN ('low','medium','high','critical')),
    CONSTRAINT agent_plans_status_check CHECK(
        status IN ('draft','submitted','approved','rejected','superseded')
    ),
    CONSTRAINT agent_plans_task_id_fkey
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    CONSTRAINT agent_plans_agent_id_fkey
        FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    runtime_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_ms INTEGER,
    input_summary TEXT,
    output_summary TEXT,
    model_provider TEXT,
    model_name TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    error_type TEXT,
    error_message TEXT,
    trace_id TEXT,
    parent_run_id TEXT,
    delegation_id TEXT,
    approval_required INTEGER NOT NULL DEFAULT 0,
    agent_plan_id TEXT,
    plan_hash TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT runs_pkey PRIMARY KEY(run_id),
    CONSTRAINT runs_task_id_fkey
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    CONSTRAINT runs_agent_id_fkey
        FOREIGN KEY(agent_id) REFERENCES agents(agent_id),
    CONSTRAINT runs_parent_run_id_fkey
        FOREIGN KEY(parent_run_id) REFERENCES runs(run_id),
    CONSTRAINT runs_agent_plan_id_fkey
        FOREIGN KEY(agent_plan_id) REFERENCES agent_plans(plan_id)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='agent_plans'::regclass
      AND conname='agent_plans_run_id_fkey'
  ) THEN
    ALTER TABLE agent_plans
    ADD CONSTRAINT agent_plans_run_id_fkey
    FOREIGN KEY(run_id) REFERENCES runs(run_id);
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_version TEXT NOT NULL DEFAULT 'v1',
    tool_category TEXT NOT NULL,
    normalized_args_json TEXT NOT NULL DEFAULT '{}',
    target_resource TEXT,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    result_summary TEXT,
    side_effect_id TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT tool_calls_pkey PRIMARY KEY(tool_call_id),
    CONSTRAINT tool_calls_tool_category_check CHECK(
        tool_category IN (
            'browser','github','file','shell','email','notion','discord',
            'database','mcp','custom'
        )
    ),
    CONSTRAINT tool_calls_risk_level_check
        CHECK(risk_level IN ('low','medium','high','critical')),
    CONSTRAINT tool_calls_run_id_fkey
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
    CONSTRAINT tool_calls_agent_id_fkey
        FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    tool_call_id TEXT,
    requested_by_agent_id TEXT,
    approver_user_id TEXT,
    decision TEXT NOT NULL,
    reason TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    CONSTRAINT approvals_pkey PRIMARY KEY(approval_id),
    CONSTRAINT approvals_decision_check
        CHECK(decision IN ('pending','approved','rejected','expired')),
    CONSTRAINT approvals_task_id_fkey
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    CONSTRAINT approvals_run_id_fkey
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
    CONSTRAINT approvals_tool_call_id_fkey
        FOREIGN KEY(tool_call_id) REFERENCES tool_calls(tool_call_id),
    CONSTRAINT approvals_requested_by_agent_id_fkey
        FOREIGN KEY(requested_by_agent_id) REFERENCES agents(agent_id),
    CONSTRAINT approvals_approver_user_id_fkey
        FOREIGN KEY(approver_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS prepared_actions (
    action_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    tool_call_id TEXT,
    approval_id TEXT NOT NULL,
    requested_by_agent_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    normalized_args_json TEXT NOT NULL DEFAULT '{}',
    target_resource TEXT,
    risk_level TEXT NOT NULL,
    policy_version TEXT NOT NULL DEFAULT 'approval-wall-v1',
    checkpoint_json TEXT NOT NULL DEFAULT '{}',
    action_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL,
    provider_side_effect_id TEXT,
    result_summary TEXT,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    consumed_at TEXT,
    expires_at TEXT,
    CONSTRAINT prepared_actions_pkey PRIMARY KEY(action_id),
    CONSTRAINT prepared_actions_risk_level_check
        CHECK(risk_level IN ('low','medium','high','critical')),
    CONSTRAINT prepared_actions_status_check CHECK(
        status IN ('prepared','approved','rejected','consumed','expired')
    ),
    CONSTRAINT prepared_actions_task_id_fkey
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    CONSTRAINT prepared_actions_run_id_fkey
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
    CONSTRAINT prepared_actions_tool_call_id_fkey
        FOREIGN KEY(tool_call_id) REFERENCES tool_calls(tool_call_id),
    CONSTRAINT prepared_actions_approval_id_fkey
        FOREIGN KEY(approval_id) REFERENCES approvals(approval_id),
    CONSTRAINT prepared_actions_requested_by_agent_id_fkey
        FOREIGN KEY(requested_by_agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS prepared_action_execution_leases (
    lease_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    requested_by_agent_id TEXT NOT NULL,
    action_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    completed_at TEXT,
    failure_reason TEXT,
    CONSTRAINT prepared_action_execution_leases_pkey PRIMARY KEY(lease_id),
    CONSTRAINT prepared_action_execution_leases_action_id_key UNIQUE(action_id),
    CONSTRAINT prepared_action_execution_leases_status_check
        CHECK(status IN ('executing','completed','failed')),
    CONSTRAINT prepared_action_execution_leases_action_id_fkey
        FOREIGN KEY(action_id) REFERENCES prepared_actions(action_id),
    CONSTRAINT prepared_action_execution_leases_requested_by_agent_id_fkey
        FOREIGN KEY(requested_by_agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    canonical_text TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    project_id TEXT,
    task_id TEXT,
    agent_id TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    review_status TEXT NOT NULL,
    owner_user_id TEXT,
    ttl_review_due_at TEXT,
    supersedes_memory_id TEXT,
    access_tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT memories_pkey PRIMARY KEY(memory_id),
    CONSTRAINT memories_scope_check CHECK(scope IN ('task','project','org')),
    CONSTRAINT memories_memory_type_check CHECK(
        memory_type IN (
            'policy','sop','decision','commitment','risk','failure_case',
            'project_context','customer_preference','agent_lesson',
            'artifact_summary','loop_record'
        )
    ),
    CONSTRAINT memories_source_type_check CHECK(
        source_type IN ('chat','email','meeting','github','notion','run_log','manual')
    ),
    CONSTRAINT memories_review_status_check CHECK(
        review_status IN ('candidate','approved','rejected','stale','superseded')
    ),
    CONSTRAINT memories_task_id_fkey
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    CONSTRAINT memories_agent_id_fkey
        FOREIGN KEY(agent_id) REFERENCES agents(agent_id),
    CONSTRAINT memories_owner_user_id_fkey
        FOREIGN KEY(owner_user_id) REFERENCES users(user_id),
    CONSTRAINT memories_supersedes_memory_id_fkey
        FOREIGN KEY(supersedes_memory_id) REFERENCES memories(memory_id)
);

CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    evaluator_type TEXT NOT NULL,
    score REAL NOT NULL,
    pass_fail TEXT NOT NULL,
    rubric_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT evaluations_pkey PRIMARY KEY(evaluation_id),
    CONSTRAINT evaluations_evaluator_type_check
        CHECK(evaluator_type IN ('human','rule','llm_mock')),
    CONSTRAINT evaluations_pass_fail_check CHECK(pass_fail IN ('pass','fail')),
    CONSTRAINT evaluations_task_id_fkey
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    CONSTRAINT evaluations_run_id_fkey
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
    CONSTRAINT evaluations_agent_id_fkey
        FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    artifact_type TEXT NOT NULL,
    title TEXT NOT NULL,
    uri TEXT,
    summary TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT artifacts_pkey PRIMARY KEY(artifact_id),
    CONSTRAINT artifacts_task_id_fkey
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    CONSTRAINT artifacts_run_id_fkey
        FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    before_hash TEXT,
    after_hash TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    tamper_chain_hash TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT audit_logs_pkey PRIMARY KEY(audit_id),
    CONSTRAINT audit_logs_actor_type_check
        CHECK(actor_type IN ('user','agent','system'))
);

CREATE TABLE IF NOT EXISTS runtime_connectors (
    runtime_connector_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    profile_name TEXT,
    base_url TEXT,
    binary_path TEXT,
    status TEXT NOT NULL,
    allow_real_run INTEGER NOT NULL DEFAULT 0,
    require_confirm_run INTEGER NOT NULL DEFAULT 1,
    trust_status TEXT NOT NULL DEFAULT 'trusted',
    trust_note TEXT,
    trust_updated_at TEXT,
    observation_level TEXT NOT NULL DEFAULT 'ledger_summary_only',
    capability_manifest_json TEXT NOT NULL DEFAULT '{}',
    capability_policy_hash TEXT,
    last_health_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT runtime_connectors_pkey PRIMARY KEY(runtime_connector_id)
);

CREATE TABLE IF NOT EXISTS runtime_events (
    runtime_event_id TEXT NOT NULL,
    runtime_connector_id TEXT,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    run_id TEXT,
    task_id TEXT,
    agent_id TEXT,
    model_name TEXT,
    latency_ms INTEGER,
    prompt_hash TEXT,
    input_summary TEXT,
    output_summary TEXT,
    error_message TEXT,
    raw_payload_hash TEXT,
    created_at TEXT NOT NULL,
    CONSTRAINT runtime_events_pkey PRIMARY KEY(runtime_event_id),
    CONSTRAINT runtime_events_runtime_connector_id_fkey
        FOREIGN KEY(runtime_connector_id)
        REFERENCES runtime_connectors(runtime_connector_id),
    CONSTRAINT runtime_events_run_id_fkey
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
    CONSTRAINT runtime_events_task_id_fkey
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    CONSTRAINT runtime_events_agent_id_fkey
        FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS agent_gateway_tokens (
    token_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    label TEXT,
    heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 300,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT,
    last_used_at TEXT,
    last_heartbeat_at TEXT,
    CONSTRAINT agent_gateway_tokens_pkey PRIMARY KEY(token_id),
    CONSTRAINT agent_gateway_tokens_token_hash_key UNIQUE(token_hash),
    CONSTRAINT agent_gateway_tokens_status_check
        CHECK(status IN ('active','revoked','expired')),
    CONSTRAINT agent_gateway_tokens_agent_id_fkey
        FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS agent_gateway_sessions (
    session_id TEXT NOT NULL,
    session_hash TEXT NOT NULL,
    parent_token_id TEXT,
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    last_used_at TEXT,
    CONSTRAINT agent_gateway_sessions_pkey PRIMARY KEY(session_id),
    CONSTRAINT agent_gateway_sessions_session_hash_key UNIQUE(session_hash),
    CONSTRAINT agent_gateway_sessions_status_check
        CHECK(status IN ('active','revoked','expired')),
    CONSTRAINT agent_gateway_sessions_parent_token_id_fkey
        FOREIGN KEY(parent_token_id) REFERENCES agent_gateway_tokens(token_id),
    CONSTRAINT agent_gateway_sessions_agent_id_fkey
        FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS agent_gateway_enrollment_requests (
    request_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT,
    runtime_type TEXT NOT NULL,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    reason TEXT,
    status TEXT NOT NULL,
    token_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decided_at TEXT,
    CONSTRAINT agent_gateway_enrollment_requests_pkey PRIMARY KEY(request_id),
    CONSTRAINT agent_gateway_enrollment_requests_status_check
        CHECK(status IN ('pending','approved','rejected','issued')),
    CONSTRAINT agent_gateway_enrollment_requests_approval_id_fkey
        FOREIGN KEY(approval_id) REFERENCES approvals(approval_id),
    CONSTRAINT agent_gateway_enrollment_requests_task_id_fkey
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    CONSTRAINT agent_gateway_enrollment_requests_run_id_fkey
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
    CONSTRAINT agent_gateway_enrollment_requests_token_id_fkey
        FOREIGN KEY(token_id) REFERENCES agent_gateway_tokens(token_id)
);

CREATE TABLE IF NOT EXISTS plan_evidence_manifests (
    manifest_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    plan_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    mismatch_policy TEXT NOT NULL,
    expected_steps_json TEXT NOT NULL DEFAULT '[]',
    tool_call_ids_json TEXT NOT NULL DEFAULT '[]',
    evaluation_ids_json TEXT NOT NULL DEFAULT '[]',
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    audit_ids_json TEXT NOT NULL DEFAULT '[]',
    plan_hash TEXT,
    verification_result_hash TEXT,
    status TEXT NOT NULL,
    verification_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT plan_evidence_manifests_pkey PRIMARY KEY(manifest_id),
    CONSTRAINT plan_evidence_manifests_mismatch_policy_check
        CHECK(mismatch_policy IN ('block','warn')),
    CONSTRAINT plan_evidence_manifests_status_check
        CHECK(status IN ('submitted','verified','warning','blocked')),
    CONSTRAINT plan_evidence_manifests_plan_id_fkey
        FOREIGN KEY(plan_id) REFERENCES agent_plans(plan_id),
    CONSTRAINT plan_evidence_manifests_task_id_fkey
        FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    CONSTRAINT plan_evidence_manifests_run_id_fkey
        FOREIGN KEY(run_id) REFERENCES runs(run_id),
    CONSTRAINT plan_evidence_manifests_agent_id_fkey
        FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner_agent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks(workspace_id);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON runs(agent_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_runs_workspace ON runs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_runs_agent_plan ON runs(agent_plan_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_risk ON tool_calls(risk_level);
CREATE INDEX IF NOT EXISTS idx_approvals_decision ON approvals(decision);
CREATE INDEX IF NOT EXISTS idx_prepared_actions_approval
ON prepared_actions(approval_id);
CREATE INDEX IF NOT EXISTS idx_prepared_actions_run ON prepared_actions(run_id);
CREATE INDEX IF NOT EXISTS idx_prepared_actions_hash
ON prepared_actions(action_hash);
CREATE INDEX IF NOT EXISTS idx_prepared_action_leases_status
ON prepared_action_execution_leases(status,started_at);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(review_status);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
CREATE INDEX IF NOT EXISTS idx_audit_entity
ON audit_logs(entity_type,entity_id);
CREATE INDEX IF NOT EXISTS idx_runtime_events_connector
ON runtime_events(runtime_connector_id);
CREATE INDEX IF NOT EXISTS idx_agent_gateway_tokens_agent
ON agent_gateway_tokens(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_gateway_tokens_status
ON agent_gateway_tokens(status);
CREATE INDEX IF NOT EXISTS idx_agent_plans_task ON agent_plans(task_id);
CREATE INDEX IF NOT EXISTS idx_agent_plans_agent ON agent_plans(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_plans_workspace
ON agent_plans(workspace_id,created_at);
CREATE INDEX IF NOT EXISTS idx_agent_plans_hash ON agent_plans(plan_hash);
CREATE INDEX IF NOT EXISTS idx_plan_evidence_plan
ON plan_evidence_manifests(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_evidence_run
ON plan_evidence_manifests(run_id);
CREATE INDEX IF NOT EXISTS idx_plan_evidence_agent
ON plan_evidence_manifests(agent_id);
