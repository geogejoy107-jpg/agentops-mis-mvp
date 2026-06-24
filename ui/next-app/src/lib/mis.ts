"use client";

export type DashboardMetrics = {
  agents_total?: number;
  agents_running?: number;
  tasks_completed_total?: number;
  total_cost_usd?: number;
  failure_rate?: number;
  pending_approvals?: number;
  stale_or_due_memories?: number;
  recent_runs?: RunSummary[];
  task_status_distribution?: { status?: string; count?: number }[];
  top_cost_agents?: { agent_id?: string; name?: string; cost_usd?: number }[];
  runtime_health?: {
    provider?: string;
    status?: string;
    detail?: string;
    last_error?: string | null;
    configured?: boolean;
  }[];
  openclaw_import?: {
    agents?: number;
    cron_jobs?: number;
    enabled_cron_jobs?: number;
    cron_runs?: number;
    cron_tasks?: number;
  };
};

export type TaskSummary = {
  task_id: string;
  title: string;
  description?: string;
  status: string;
  priority?: string;
  risk_level?: string;
  owner_agent_id?: string | null;
  acceptance_criteria?: string;
  budget_limit_usd?: number;
  created_at?: string;
  updated_at?: string;
};

export type RunSummary = {
  run_id: string;
  task_id?: string;
  agent_id?: string;
  runtime_type?: string;
  status: string;
  duration_ms?: number | null;
  input_summary?: string | null;
  output_summary?: string | null;
  error_message?: string | null;
  cost_usd?: number;
  started_at?: string;
  created_at?: string;
};

export type ToolCallSummary = {
  tool_call_id: string;
  run_id?: string;
  agent_id?: string;
  tool_name?: string;
  tool_version?: string;
  tool_category?: string;
  normalized_args_json?: string;
  target_resource?: string;
  risk_level?: string;
  status?: string;
  result_summary?: string;
  side_effect_id?: string | null;
  started_at?: string;
  ended_at?: string | null;
  created_at?: string;
};

export type EvaluationSummary = {
  evaluation_id: string;
  task_id?: string;
  run_id?: string;
  agent_id?: string;
  evaluator_type?: string;
  score?: number;
  pass_fail?: string;
  rubric_json?: string;
  notes?: string | null;
  created_at?: string;
};

export type RuntimeConnectorSummary = {
  runtime_connector_id?: string;
  connector_id?: string;
  provider?: string;
  connector_type?: string;
  profile_name?: string;
  base_url?: string;
  binary_path?: string;
  status?: string;
  allow_real_run?: number | boolean;
  require_confirm_run?: number | boolean;
  trust_status?: string;
  trust_note?: string | null;
  trust_updated_at?: string | null;
  last_health_at?: string | null;
  last_error?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type RuntimeConnectorTrustResponse = {
  connector?: RuntimeConnectorSummary;
  token_omitted?: boolean;
};

export type NotionConnectorSummary = {
  connector_id?: string;
  base_id?: string;
  provider?: string;
  auth_type?: string;
  status?: string;
  last_checked_at?: string | null;
  last_error?: string | null;
  dry_run_default?: number | boolean;
  writeback_allowed?: number | boolean;
  created_at?: string;
  updated_at?: string;
};

export type NotionStatus = {
  provider?: string;
  configured?: boolean;
  has_token?: boolean;
  has_parent_page_id?: boolean;
  has_database_id?: boolean;
  workspace_private_export?: boolean;
  export_mode?: string;
  dry_run_default?: boolean;
  writeback_allowed?: boolean;
  last_sync?: string | null;
  last_error?: string | null;
  notion_version?: string;
  connectors?: NotionConnectorSummary[];
};

export type NotionPreview = {
  provider?: string;
  status?: NotionStatus;
  report?: {
    title?: string;
    markdown?: string;
    block_count?: number;
  };
  tasks?: TaskSummary[];
  memory_candidates?: MemorySummary[];
  write_behavior?: string;
};

export type NotionExportResult = {
  provider?: string;
  dry_run?: boolean;
  created?: boolean;
  configured?: boolean;
  requires_confirm_export?: boolean;
  sync_event_id?: string;
  markdown?: string;
  block_count?: number;
  error?: string;
  capability?: string;
  required_edition?: string;
  current_edition?: string;
  billing_call_performed?: boolean;
  live_execution_performed?: boolean;
  token_omitted?: boolean;
};

export type ApprovalSummary = {
  approval_id: string;
  decision: string;
  task_id?: string;
  run_id?: string;
  tool_call_id?: string;
  requested_by_agent_id?: string;
  reason?: string;
  expires_at?: string;
  decided_at?: string | null;
};

export type MemorySummary = {
  memory_id: string;
  scope: string;
  memory_type: string;
  canonical_text: string;
  source_type?: string;
  confidence?: number;
  review_status: string;
  task_id?: string | null;
  agent_id?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type AuditSummary = {
  audit_id: string;
  actor_type: string;
  actor_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  created_at?: string;
};

export type AgentSummary = {
  agent_id: string;
  name: string;
  role?: string;
  description?: string;
  runtime_type?: string;
  model_provider?: string;
  model_name?: string;
  status?: string;
  permission_level?: string;
  allowed_tools?: string[] | string;
  budget_limit_usd?: number;
  owner_user_id?: string;
  created_at?: string;
  updated_at?: string;
};

export type AgentPerformancePayload = {
  agent: AgentSummary;
  total_runs?: number;
  completed_runs?: number;
  failures?: number;
  success_rate?: number;
  avg_duration_ms?: number;
  total_cost_usd?: number;
  approval_required_count?: number;
  recent_error_types?: { error_type?: string; count?: number }[];
  recent_runs?: RunSummary[];
};

export type ReadinessGate = {
  id?: string;
  label?: string;
  status?: string;
  ok?: boolean;
  detail?: string;
  summary?: string;
  next_action?: string;
  action?: string;
};

export type SecurityReadinessSummary = {
  provider?: string;
  status?: string;
  production_ready?: boolean;
  production_requested?: boolean;
  auth_mode?: string;
  contract?: string;
  gates?: ReadinessGate[];
  next_actions?: string[];
  safety?: {
    read_only?: boolean;
    live_execution_performed?: boolean;
    token_omitted?: boolean;
    raw_prompt_omitted?: boolean;
  };
  token_omitted?: boolean;
};

export type LocalReadinessPayload = {
  provider?: string;
  operation?: string;
  status?: string;
  ok?: boolean;
  workspace_id?: string;
  gates?: ReadinessGate[];
  evidence?: Record<string, number | boolean>;
  adapter_readiness?: {
    recommended_adapter?: string;
    ready_adapters?: string[];
    live_ready_adapters?: string[];
    unavailable_adapters?: string[];
    blocked_adapters?: string[];
  };
  worker_fleet_health?: {
    overall?: string;
    contract?: string;
    gates?: ReadinessGate[];
    recommended_actions?: string[];
    token_omitted?: boolean;
  };
  security_production_readiness?: SecurityReadinessSummary;
  docs?: { id?: string; path?: string; exists?: boolean }[];
  deployment_checks?: Record<string, boolean | string | number>;
  ui_routes?: Record<string, string>;
  next_actions?: string[];
  contract?: string;
  live_execution_performed?: boolean;
  token_omitted?: boolean;
  error?: string;
};

export type DeploymentReadinessPayload = {
  provider?: string;
  operation?: string;
  contract_id?: string;
  generated_at?: string;
  status?: string;
  ok?: boolean;
  deployment_ready?: boolean;
  workspace_id?: string;
  edition?: string;
  gates?: ReadinessGate[];
  next_actions?: string[];
  local?: Record<string, boolean | string | number | undefined>;
  security?: Record<string, boolean | string | number | undefined>;
  storage?: Record<string, boolean | string | number | undefined>;
  backup_restore?: Record<string, boolean | string | number | undefined>;
  signed_audit_export?: Record<string, boolean | string | number | undefined>;
  retention?: Record<string, boolean | string | number | undefined>;
  enterprise_byoc?: Record<string, boolean | string | number | undefined>;
  enterprise_controls?: Record<string, boolean | string | number | undefined>;
  contracts?: string[];
  safety?: Record<string, boolean | string | number | undefined>;
  live_execution_performed?: boolean;
  token_omitted?: boolean;
  error?: string;
};

export type EnterpriseControlsPayload = {
  provider?: string;
  operation?: string;
  contract_id?: string;
  generated_at?: string;
  status?: string;
  ok?: boolean;
  edition?: string;
  entitlement_ready?: boolean;
  sso?: Record<string, boolean | string | number | undefined>;
  private_connector_policy?: {
    registry_configured?: boolean;
    trust_policy_configured?: boolean;
    total_connectors?: number;
    active_connectors?: number;
    connector_refs?: { connector_id?: string; provider?: string; status?: string }[];
    raw_config_omitted?: boolean;
    client_secret_omitted?: boolean;
  };
  safety?: Record<string, boolean | string | number | undefined>;
  live_execution_performed?: boolean;
  token_omitted?: boolean;
  error?: string;
};

export type AuditRetentionPolicyPayload = {
  provider?: string;
  operation?: string;
  contract_id?: string;
  generated_at?: string;
  status?: string;
  ok?: boolean;
  policy_ready?: boolean;
  dry_run?: boolean;
  delete_supported?: boolean;
  workspace_id?: string;
  edition?: string;
  policy?: Record<string, boolean | string | number | string[] | undefined>;
  counts?: Record<string, boolean | string | number | undefined | null>;
  entitlement?: Record<string, boolean | string | number | undefined>;
  gates?: ReadinessGate[];
  next_actions?: string[];
  blocked_reasons?: string[];
  safety?: Record<string, boolean | string | number | undefined>;
  live_execution_performed?: boolean;
  billing_call_performed?: boolean;
  delete_performed?: boolean;
  rows_deleted?: number;
  token_omitted?: boolean;
  error?: string;
};

export type AuditRetentionControlsPayload = {
  provider?: string;
  operation?: string;
  contract_id?: string;
  generated_at?: string;
  status?: string;
  ok?: boolean;
  controls_ready?: boolean;
  workspace_id?: string;
  edition?: string;
  config?: Record<string, boolean | string | number | undefined>;
  retention_windows?: Record<string, boolean | string | number | undefined>;
  controls?: Record<string, boolean | string | number | string[] | undefined>;
  legal_hold_summary?: Record<string, boolean | string | number | unknown[] | undefined>;
  entitlement?: Record<string, boolean | string | number | undefined>;
  gates?: ReadinessGate[];
  next_actions?: string[];
  blocked_reasons?: string[];
  safety?: Record<string, boolean | string | number | undefined>;
  live_execution_performed?: boolean;
  billing_call_performed?: boolean;
  delete_supported?: boolean;
  delete_performed?: boolean;
  rows_deleted?: number;
  token_omitted?: boolean;
  error?: string;
};

export type WorkerStatusSummary = {
  provider?: string;
  status?: string;
  worker_count?: number;
  running_workers?: number;
  recent_completed_runs?: number;
  pending_worker_tasks?: number;
  stuck_worker_tasks?: number;
  stuck_tasks?: WorkerStuckTask[];
  remote_worker_count?: number;
  active_remote_enrollments?: number;
  fresh_remote_enrollments?: number;
  stale_remote_enrollments?: number;
  active_remote_sessions?: number;
  fleet_health?: {
    overall?: string;
    contract?: string;
    gates?: ReadinessGate[];
    recommended_actions?: string[];
    token_omitted?: boolean;
  };
  daemons?: WorkerDaemonStatusSummary[];
  adapter_readiness?: {
    recommended_adapter?: string;
    ready_adapters?: string[];
    live_ready_adapters?: string[];
    unavailable_adapters?: string[];
    blocked_adapters?: string[];
  };
};

export type WorkerDaemonStatusSummary = {
  adapter?: string;
  agent_id?: string;
  running?: boolean;
  status?: string;
  worker_status?: string;
  pid?: number | null;
  started_at?: string | null;
  stopped_at?: string | null;
  poll_interval?: number;
  max_tasks?: number;
  processed?: number;
  iteration?: number;
  error_count?: number;
  last_exit_note?: string;
};

export type WorkerStuckTask = TaskSummary & {
  age_sec?: number;
  threshold_sec?: number;
  running_run_id?: string | null;
  running_run_started_at?: string | null;
  stuck_reason?: string;
};

export type WorkerAdapterReadinessSummary = {
  provider?: string;
  status?: string;
  contract?: string;
  summary?: {
    recommended_adapter?: string;
    ready_adapters?: string[];
    live_ready_adapters?: string[];
    unavailable_adapters?: string[];
    blocked_adapters?: string[];
    review_required_adapters?: string[];
  };
  adapters?: Record<string, {
    adapter?: string;
    ok?: boolean;
    readiness?: string;
    trust_status?: string;
    requires_confirm_run?: boolean;
    recommended_action?: string;
    token_omitted?: boolean;
  }>;
  live_execution_performed?: boolean;
  token_omitted?: boolean;
};

export type WorkerFleetLane = {
  lane_id?: string;
  lane_type?: string;
  adapter?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  workspace_id?: string | null;
  runtime_type?: string | null;
  status?: string;
  health?: string;
  heartbeat_state?: string | null;
  session_state?: string | null;
  active_session_count?: number;
  last_seen_at?: string | null;
  expires_at?: string | null;
  scope_count?: number;
  workload?: Record<string, unknown>;
  next_action?: string;
  safe_ref?: string | null;
  token_omitted?: boolean;
  session_id_omitted?: boolean;
  token_id_omitted?: boolean;
};

export type WorkerFleetPayload = {
  provider?: string;
  operation?: string;
  status?: string;
  summary?: {
    lane_count?: number;
    lane_counts?: Record<string, number>;
    health_counts?: Record<string, number>;
    local_daemon_count?: number;
    running_local_daemons?: number;
    remote_worker_count?: number;
    fresh_remote_enrollments?: number;
    stale_remote_enrollments?: number;
    never_seen_remote_enrollments?: number;
    active_remote_sessions?: number;
    stuck_worker_tasks?: number;
    stuck_workflow_jobs?: number;
    recommended_adapter?: string;
  };
  lanes?: WorkerFleetLane[];
  next_actions?: string[];
  contract?: string;
  safety?: {
    read_only?: boolean;
    live_execution_performed?: boolean;
    token_omitted?: boolean;
    session_id_omitted?: boolean;
    raw_prompt_omitted?: boolean;
  };
  token_omitted?: boolean;
  live_execution_performed?: boolean;
  error?: string;
};

export type WorkerFleetHygienePayload = {
  provider?: string;
  operation?: string;
  status?: string;
  threshold_sec?: number;
  enrollment_age_sec?: number;
  summary?: {
    stuck_tasks?: number;
    stale_never_seen_enrollments?: number;
    actions_available?: number;
    released_tasks?: number;
    revoked_enrollments?: number;
    errors?: number;
  };
  stuck_tasks?: WorkerStuckTask[];
  stale_never_seen_enrollments?: AgentGatewayEnrollmentSummary[];
  recommended_actions?: string[];
  safety?: {
    read_only?: boolean;
    requires_confirm_cleanup?: boolean;
    live_execution_performed?: boolean;
    token_omitted?: boolean;
  };
  applied?: boolean;
  released_tasks?: { task_id?: string; released_runs?: string[] }[];
  revoked_enrollments?: { token_id?: string; token_ref?: string; agent_id?: string | null; sessions_revoked?: number }[];
  errors?: Record<string, unknown>[];
  error?: string;
  token_omitted?: boolean;
  live_execution_performed?: boolean;
};

export type OperatorExecutionModePayload = {
  provider?: string;
  operation?: string;
  status?: string;
  workspace_id?: string;
  selected_adapter?: string;
  adapter_route?: {
    adapter?: string;
    execution_path?: string;
    readiness?: string;
    trust_status?: string;
    requires_confirm_run?: boolean;
    live_ready?: boolean;
    confirm_run_wall?: {
      required?: boolean;
      satisfied?: boolean;
      reason?: string;
      flag?: string;
      server_executes_live_without_confirm?: boolean;
    };
    prepared_action_wall?: {
      required_for_live_customer_worker?: boolean;
      pending_actions?: number;
      approved_actions?: number;
      resume_command?: string;
      server_executes_prepared_action_without_approval?: boolean;
    };
    recommended_command?: string;
    connector_id?: string | null;
    token_omitted?: boolean;
  };
  summary?: {
    recommended_adapter?: string;
    ready_adapters?: string[];
    live_ready_adapters?: string[];
    review_required_adapters?: string[];
    blocked_adapters?: string[];
    unavailable_adapters?: string[];
    pending_approvals?: number;
    active_async_jobs?: number;
    prepared_actions_waiting_approval?: number;
    approved_prepared_actions?: number;
    worker_status?: string;
    running_daemons?: number;
    stuck_worker_tasks?: number;
  };
  gates?: ReadinessGate[];
  next_actions?: string[];
  contract?: string;
  safety?: {
    read_only?: boolean;
    ledger_mutated?: boolean;
    daemon_started?: boolean;
    adapter_executed?: boolean;
    live_execution_performed?: boolean;
    token_omitted?: boolean;
    raw_prompt_omitted?: boolean;
  };
  live_execution_performed?: boolean;
  token_omitted?: boolean;
  error?: string;
};

export type WorkerDispatchResult = {
  provider?: string;
  dry_run?: boolean;
  ok?: boolean;
  adapter?: string;
  agent_id?: string;
  task_id?: string;
  duration_ms?: number;
  worker_result?: {
    ok?: boolean;
    processed?: number;
    results?: Array<{
      ok?: boolean;
      task_id?: string;
      run_id?: string;
      plan_id?: string;
      plan_evidence_manifest_id?: string;
      plan_evidence_status?: string;
      plan_evidence_pass?: boolean;
      processed?: boolean;
      error?: string;
    }>;
    token_omitted?: boolean;
  };
  error?: string | null;
};

export type WorkerTaskReleaseResult = {
  released?: boolean;
  task?: TaskSummary;
  released_runs?: string[];
  token_omitted?: boolean;
  error?: string | null;
  message?: string | null;
};

export type WorkerDaemonResult = {
  provider?: string;
  ok?: boolean;
  already_running?: boolean;
  adapter?: string;
  daemon?: WorkerDaemonStatusSummary;
  daemons?: WorkerDaemonStatusSummary[];
  previous?: WorkerDaemonStatusSummary;
  stopped?: { provider?: string; ok?: boolean; daemons?: WorkerDaemonStatusSummary[] };
  error?: string | null;
  token_omitted?: boolean;
};

export type AgentGatewaySessionSummary = {
  session_id?: string;
  session_ref?: string;
  session_id_omitted?: boolean;
  parent_token_id?: string;
  parent_token_ref?: string;
  parent_token_id_omitted?: boolean;
  workspace_id?: string;
  agent_id?: string;
  status?: string;
  session_state?: string;
  scopes?: string[];
  scope_count?: number;
  created_at?: string;
  expires_at?: string;
  revoked_at?: string | null;
  last_used_at?: string | null;
};

export type AgentGatewaySessionsPayload = {
  sessions?: AgentGatewaySessionSummary[];
  workspace_id?: string | null;
  valid_scopes?: string[];
  token_omitted?: boolean;
  error?: string;
};

export type AgentGatewayEnrollmentSummary = {
  token_id?: string;
  token_ref?: string;
  workspace_id?: string;
  agent_id?: string;
  runtime_type?: string;
  scopes?: string[];
  scope_count?: number;
  status?: string;
  label?: string;
  heartbeat_timeout_sec?: number;
  created_at?: string;
  expires_at?: string;
  revoked_at?: string | null;
  last_used_at?: string | null;
  last_heartbeat_at?: string | null;
  heartbeat_state?: string;
};

export type AgentGatewayEnrollmentListPayload = {
  enrollments?: AgentGatewayEnrollmentSummary[];
  workspace_id?: string | null;
  valid_scopes?: string[];
  token_omitted?: boolean;
  error?: string;
};

export type AgentGatewayEnrollmentRequestInput = {
  agent_id: string;
  name: string;
  role?: string;
  runtime_type: string;
  workspace_id?: string;
  label?: string;
  scopes: string[];
  ttl_days?: number;
  heartbeat_timeout_sec?: number;
  reason?: string;
};

export type AgentGatewayEnrollmentPolicyPreview = {
  provider?: string;
  operation?: string;
  status?: string;
  workspace_id?: string;
  runtime_type?: string;
  policy?: string;
  risk_level?: string;
  approval_recommended?: boolean;
  recommended_path?: string;
  scope_count?: number;
  scopes?: string[];
  invalid_scopes?: string[];
  privileged_scopes?: string[];
  worker_write_scopes?: string[];
  missing_worker_scopes?: string[];
  gates?: ReadinessGate[];
  next_actions?: string[];
  safety?: {
    read_only?: boolean;
    ledger_mutated?: boolean;
    live_execution_performed?: boolean;
    token_omitted?: boolean;
    raw_prompt_omitted?: boolean;
  };
  token_omitted?: boolean;
  live_execution_performed?: boolean;
};

export type AgentGatewayEnrollmentRequestResult = {
  request?: {
    request_id?: string;
    approval_id?: string;
    task_id?: string;
    run_id?: string;
    workspace_id?: string;
    agent_id?: string;
    name?: string;
    runtime_type?: string;
    status?: string;
    scopes?: string[];
  };
  approval?: ApprovalSummary;
  token_issued?: boolean;
  token_omitted?: boolean;
  error?: string;
};

export type CustomerProjectSummary = {
  project_id: string;
  title: string;
  status: string;
  task_count?: number;
  completed_tasks?: number;
  run_count?: number;
  completed_runs?: number;
  pending_approvals?: number;
  artifact_count?: number;
  delivery_artifact_id?: string | null;
  report_artifact_id?: string | null;
  approval_ids?: string[];
  report_url?: string;
  ui_report_url?: string;
  safe_defaults?: Record<string, unknown>;
};

export type CustomerProjectIndexPayload = {
  projects: CustomerProjectSummary[];
  total?: number;
  limit?: number;
  safe_defaults?: Record<string, unknown>;
};

export type CustomerDeliveryBoardItem = {
  delivery_id: string;
  status: string;
  title: string;
  task_id?: string | null;
  run_id?: string | null;
  artifact_id?: string | null;
  project_id?: string | null;
  summary?: string;
  ui_report_url?: string | null;
  pending_approval_ids?: string[];
  evaluation_summary?: { count?: number; failed?: number; latest_score?: number | null };
  delivery_approval_gate?: {
    required?: boolean;
    pass?: boolean;
    status?: string;
    manifest_id?: string | null;
    message?: string;
  };
  evidence?: Record<string, number>;
  next_action?: string;
};

export type CustomerDeliveryBoardPayload = {
  provider?: string;
  operation?: string;
  status?: string;
  summary?: {
    deliveries?: number;
    ready?: number;
    waiting_approval?: number;
    in_progress?: number;
    needs_attention?: number;
    pending_approvals?: number;
    artifacts?: number;
    verified_plan_evidence_manifests?: number;
  };
  deliveries: CustomerDeliveryBoardItem[];
  safety?: {
    read_only?: boolean;
    ledger_mutated?: boolean;
    live_execution_performed?: boolean;
    token_omitted?: boolean;
  };
  token_omitted?: boolean;
};

export type CustomerProjectReportPayload = {
  project_id: string;
  status: string;
  markdown: string;
  counts?: {
    tasks?: number;
    runs?: number;
    completed_runs?: number;
    failed_runs?: number;
    tool_calls?: number;
    approvals?: number;
    pending_approvals?: number;
    evaluations?: number;
    memories?: number;
    artifacts?: number;
    agent_plans?: number;
    plan_evidence_manifests?: number;
    verified_plan_evidence_manifests?: number;
  };
  execution_evidence?: {
    agent_plans?: number;
    plan_evidence_manifests?: number;
    verified_plan_evidence_manifests?: number;
    blocked_plan_evidence_manifests?: number;
    warning_plan_evidence_manifests?: number;
    tasks_missing_agent_plan?: number;
    low_risk_tasks_missing_verified_plan_evidence?: number;
    approval_gated_tasks?: number;
    manifest_ids?: string[];
    verified_manifest_ids?: string[];
    recent_manifests?: Array<{
      manifest_id?: string;
      plan_id?: string;
      task_id?: string;
      run_id?: string;
      agent_id?: string;
      status?: string;
      mismatch_policy?: string;
    }>;
    contract?: string;
  };
  artifact_id?: string | null;
  report_artifact_id?: string | null;
  approval_ids?: string[];
  safe_defaults?: Record<string, unknown>;
  error?: string | null;
};

export type CommercialEntitlementGate = {
  capability?: string;
  required_edition?: string;
  enabled?: boolean;
  status?: string;
  enforcement?: string;
};

export type CommercialEntitlementStatus = {
  provider?: string;
  operation?: string;
  status?: string;
  edition?: string;
  edition_label?: string;
  edition_source?: string;
  workspace_id?: string;
  capabilities?: Record<string, boolean>;
  gates?: CommercialEntitlementGate[];
  safety?: {
    read_only?: boolean;
    live_execution_performed?: boolean;
    token_omitted?: boolean;
    billing_call_performed?: boolean;
  };
  token_omitted?: boolean;
  live_execution_performed?: boolean;
};

export type CommercialReleaseStatusPayload = {
  provider?: string;
  operation?: string;
  contract_id?: string;
  status?: string;
  workspace_id?: string;
  generated_at?: string;
  ci_safe?: boolean;
  read_only?: boolean;
  release_complete?: boolean;
  commercial_handoff_allowed?: boolean;
  ready_to_merge?: boolean;
  git_state?: {
    branch?: string;
    head?: string;
    upstream?: string;
    ahead?: number | null;
    behind?: number | null;
    worktree_clean?: boolean;
    tracked_dirty_count?: number;
    untracked_count?: number;
    dirty_count?: number;
  };
  source_documents?: {
    path?: string;
    contract_id?: string;
    status?: string;
  }[];
  promotion_preflight?: {
    contract_id?: string;
    status?: string;
    release_promotion_allowed?: boolean;
    release_grade_update_allowed?: boolean;
    promotion_requires?: Record<string, boolean | string | number | null>;
    source_contracts?: string[];
    known_blockers?: string[];
    required_commands?: string[];
    must_not_use?: string[];
  };
  promotion_packet?: {
    contract_id?: string;
    status?: string;
    ci_safe?: boolean;
    read_only?: boolean;
    packet_requires?: Record<string, boolean | string | number | null>;
    source_contracts?: string[];
    required_commands?: string[];
    must_not_use?: string[];
  };
  current_evidence_status?: {
    contract_id?: string;
    status?: string;
    gate_count?: number;
    ready_gate_count?: number;
    gates_requiring_current_evidence?: string[];
    gates_with_local_receipts?: string[];
    gates_with_release_grade_receipts?: string[];
    exact_head_ci_verified?: boolean;
    static_exact_head_ci_verified?: boolean;
    effective_exact_head_ci_verified?: boolean;
    exact_head_ci_source?: string;
    remote_sync_verified?: boolean;
    clean_worktree_verified?: boolean;
    postgres_required?: boolean;
    browser_required?: boolean;
    real_runtime_required?: boolean;
    heavy_evidence_not_executed_by_default?: boolean;
  };
  receipt_summary?: {
    gates_with_local_receipts?: string[];
    gates_with_release_grade_receipts?: string[];
    gates_missing_local_receipts?: string[];
    exact_head_ci_verified?: boolean;
    remote_sync_verified?: boolean;
    clean_worktree_verified?: boolean;
  };
  external_exact_head_ci?: {
    contract_id?: string;
    checked?: boolean;
    network_called?: boolean;
    external_check_requested?: boolean;
    exact_head_ci_verified?: boolean;
    status?: string;
    head?: string;
    head_matches_current?: boolean;
    run_id?: string;
    workflow?: string;
    url?: string;
    required_jobs_success?: boolean;
    job_gaps?: string[];
    error?: string;
    command?: string;
    required_for_promotion?: boolean;
  };
  commands?: {
    include_external_ci_evidence?: string;
    strict_promotion?: string;
    exact_head_ci?: string;
    promotion_packet?: string;
    strict_promotion_packet?: string;
    release_status_external_ci_api?: string;
  };
  blockers?: string[];
  safety?: {
    read_only?: boolean;
    ci_safe?: boolean;
    live_execution_performed?: boolean;
    network_called?: boolean;
    token_omitted?: boolean;
    raw_prompt_omitted?: boolean;
    raw_response_omitted?: boolean;
    private_transcripts_omitted?: boolean;
    billing_call_performed?: boolean;
  };
  token_omitted?: boolean;
  live_execution_performed?: boolean;
};

export type StorageBackendStatus = {
  provider?: string;
  status?: string;
  selected_backend?: string;
  active_backend?: string;
  mode?: string;
  writes_allowed?: boolean;
  reason?: string;
  required_edition?: string;
  required_env?: string[];
  supported_backends?: string[];
  fallback_performed?: boolean;
  token_omitted?: boolean;
  contract?: string;
  contracts?: string[];
  write_allowlist?: StorageBackendWriteRoute[];
  next_proof?: string;
  sqlite?: {
    db_path?: string;
    dependency?: string;
    free_local_default?: boolean;
  };
  postgres?: {
    available_as_runtime_dependency?: boolean;
    dsn_configured?: boolean;
    required_edition?: string;
    server_backend_routable?: boolean;
    read_only_http_routable?: boolean;
    write_http_routable?: boolean;
    free_local_dependency?: boolean;
  };
  runtime_write_gate?: {
    status?: string;
    required_backend?: string;
    contracts?: string[];
    allowlisted_routes?: StorageBackendWriteRoute[];
    required_action_types?: Array<{
      provider?: string;
      action_type?: string;
    }>;
    exact_resume_required?: boolean;
    approval_decision?: string;
    non_fixed_runtime_writes?: string;
    live_execution_performed?: boolean;
    token_omitted?: boolean;
  };
  checks?: Record<string, boolean>;
};

export type StorageBackendWriteRoute = {
  method?: string;
  path?: string;
  row_gated?: boolean;
};

export type CustomerTaskTemplate = {
  template_id: string;
  name?: string;
  name_en?: string;
  workflow?: string;
  scenario?: string;
  status?: string;
  risk_level?: string;
  priority?: string;
  description?: string;
  default_title?: string;
  default_description?: string;
  default_acceptance?: string;
  agent_roles?: string[];
  required_approvals?: string[];
  safe_defaults?: Record<string, unknown>;
  entrypoint?: string;
};

export type CustomerTaskTemplateListPayload = {
  templates: CustomerTaskTemplate[];
  safe_defaults?: Record<string, unknown>;
};

export type BaseRecord = {
  base_id: string;
  provider?: string;
  category?: string;
  storage_mode?: string;
  status?: string;
  display_name?: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
};

export type BaseCapability = {
  base_id: string;
  tasks?: number | boolean;
  comments?: number | boolean;
  artifacts?: number | boolean;
  metrics?: number | boolean;
  webhooks?: number | boolean;
  oauth?: number | boolean;
  writeback?: number | boolean;
  permissions?: number | boolean;
  audit?: number | boolean;
  realtime?: number | boolean;
  notes?: string | null;
};

export type BasesPayload = {
  bases: BaseRecord[];
  capabilities: BaseCapability[];
};

export type TemplatePackage = {
  template_id: string;
  name?: string;
  scenario?: string;
  description?: string;
  status?: string;
  default_bases_json?: string;
  swappable_bases_json?: string;
  agent_roles_json?: string;
  task_schema_json?: string;
  memory_schema_json?: string;
  quality_gates_json?: string;
  approval_policy_json?: string;
  created_at?: string;
  updated_at?: string;
};

export type TemplateBinding = {
  binding_id?: string;
  template_id?: string;
  base_id?: string;
  workspace_id?: string;
  status?: string;
  mapping_json?: string;
  created_at?: string;
};

export type MigrationPreviewPayload = {
  template_id?: string;
  from_base?: BaseRecord | null;
  to_base?: BaseRecord | null;
  template?: TemplatePackage | null;
  migratable_objects?: string[];
  non_migratable_objects?: string[];
  field_downgrades?: Array<{ field?: string; strategy?: string }>;
  permission_changes?: string[];
  requires_human_confirmation?: string[];
  rollback?: string[];
  token_omitted?: boolean;
  error?: string;
};

export type WorkflowJob = {
  job_id: string;
  workspace_id?: string;
  workflow_type?: string;
  status?: string;
  template_id?: string | null;
  adapter?: string | null;
  confirm_run?: boolean | number;
  title?: string | null;
  input_summary?: string | null;
  request_hash?: string | null;
  result_task_id?: string | null;
  result_run_id?: string | null;
  result_artifact_id?: string | null;
  error_message?: string | null;
  created_at?: string;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at?: string;
  result?: {
    provider?: string;
    workflow?: string;
    ok?: boolean;
    task_id?: string;
    run_id?: string;
    artifact_id?: string;
    approval_id?: string;
    plan_evidence_manifest_id?: string;
    evidence?: Record<string, number>;
    error?: string | null;
  };
  raw_request_omitted?: boolean;
  token_omitted?: boolean;
};

export type WorkflowJobListPayload = {
  jobs: WorkflowJob[];
  workspace_id?: string;
  token_omitted?: boolean;
};

export type CustomerWorkerPreparedAction = {
  prepared_action_id: string;
  workspace_id?: string;
  task_id?: string | null;
  run_id?: string | null;
  tool_call_id?: string | null;
  approval_id?: string | null;
  approval_decision?: string | null;
  approval_expires_at?: string | null;
  approval_decided_at?: string | null;
  requested_by_agent_id?: string | null;
  action_type?: string;
  provider?: string;
  target_resource?: string | null;
  adapter?: string | null;
  async_job?: boolean;
  status?: string;
  request_hash?: string | null;
  request_hash_short?: string | null;
  args_hash?: string | null;
  created_at?: string;
  updated_at?: string;
  approved_at?: string | null;
  consumed_at?: string | null;
  can_resume?: boolean;
  waiting_for_approval?: boolean;
  result_hash?: string | null;
  result_hash_short?: string | null;
  result_status?: number | null;
  result_task_id?: string | null;
  result_run_id?: string | null;
  result_artifact_id?: string | null;
  resume_form?: {
    title?: string;
    description?: string;
    acceptance_criteria?: string;
    priority?: string;
    risk_level?: string;
    worker_agent_id?: string;
    raw_request_omitted?: boolean;
  };
  raw_request_omitted?: boolean;
  raw_result_omitted?: boolean;
  raw_prompt_omitted?: boolean;
  raw_response_omitted?: boolean;
  token_omitted?: boolean;
};

export type CustomerWorkerPreparedActionListPayload = {
  provider?: string;
  workflow?: string;
  workspace_id?: string;
  prepared_actions: CustomerWorkerPreparedAction[];
  count?: number;
  status_filter?: string[] | string;
  raw_request_omitted?: boolean;
  raw_result_omitted?: boolean;
  raw_prompt_omitted?: boolean;
  raw_response_omitted?: boolean;
  token_omitted?: boolean;
};

export type PlanEvidenceManifest = {
  manifest_id?: string;
  workspace_id?: string;
  plan_id?: string;
  task_id?: string;
  run_id?: string;
  agent_id?: string;
  mismatch_policy?: string;
  status?: string;
  verification_json?: string;
  created_at?: string;
  updated_at?: string;
};

export type AgentPlanPayload = {
  plan_id?: string;
  workspace_id?: string;
  task_id?: string;
  run_id?: string | null;
  agent_id?: string;
  task_understanding?: string;
  risk_level?: string;
  approval_required?: boolean | number;
  verification_plan?: string | null;
  rollback_plan?: string | null;
  status?: string;
  created_at?: string;
  updated_at?: string;
};

export type VerificationCheck = {
  id?: string;
  ok?: boolean;
  message?: string;
};

export type VerificationPayload = {
  pass?: boolean;
  checks?: VerificationCheck[];
  failed_checks?: VerificationCheck[];
  summary?: Record<string, unknown>;
  token_omitted?: boolean;
};

export type PlanEvidenceVerifyPayload = {
  provider?: string;
  operation?: string;
  manifest?: PlanEvidenceManifest;
  verification?: VerificationPayload;
  token_omitted?: boolean;
  error?: string;
};

export type AgentPlanVerifyPayload = {
  provider?: string;
  operation?: string;
  plan_id?: string;
  agent_plan?: AgentPlanPayload;
  verification?: VerificationPayload;
  token_omitted?: boolean;
  error?: string;
};

export type RunGraphPayload = {
  provider?: string;
  operation?: string;
  run?: RunSummary;
  task?: TaskSummary;
  parent?: RunSummary | null;
  children?: RunSummary[];
  siblings_by_delegation?: RunSummary[];
  tool_calls?: unknown[];
  evaluations?: unknown[];
  artifacts?: unknown[];
  approvals?: unknown[];
  audit_logs?: unknown[];
  runtime_events?: unknown[];
  token_omitted?: boolean;
  error?: string;
};

export type TaskDetailPayload = {
  provider?: string;
  operation?: string;
  task?: TaskSummary;
  runs?: RunSummary[];
  approvals?: ApprovalSummary[];
  evaluations?: unknown[];
  memories?: MemorySummary[];
  artifacts?: unknown[];
  token_omitted?: boolean;
  error?: string;
};

export type RunDetailPayload = {
  provider?: string;
  operation?: string;
  run?: RunSummary;
  task?: TaskSummary;
  tool_calls?: unknown[];
  approvals?: ApprovalSummary[];
  evaluations?: unknown[];
  memories?: MemorySummary[];
  artifacts?: unknown[];
  runtime_events?: unknown[];
  audit_logs?: unknown[];
  token_omitted?: boolean;
  error?: string;
};

export type RunDetailSnapshot = {
  detail: RunDetailPayload | null;
  graph: RunGraphPayload | null;
};

export type EvidenceDrilldownPayload = {
  manifest: PlanEvidenceVerifyPayload | null;
  plan: AgentPlanVerifyPayload | null;
  runGraph: RunGraphPayload | null;
};

export type AgentControlSnapshot = {
  agents: AgentSummary[];
  security: SecurityReadinessSummary;
  workerStatus: WorkerStatusSummary;
  adapterReadiness: WorkerAdapterReadinessSummary;
  enrollments: AgentGatewayEnrollmentListPayload;
  sessions: AgentGatewaySessionsPayload;
};

export type WorkspaceSnapshot = {
  metrics: DashboardMetrics;
  tasks: TaskSummary[];
  runs: RunSummary[];
  approvals: ApprovalSummary[];
};

async function misJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/mis${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export async function loadWorkspaceSnapshot(): Promise<WorkspaceSnapshot> {
  const [metrics, tasks, runs, approvals] = await Promise.all([
    misJson<DashboardMetrics>("/dashboard/metrics"),
    loadTasks(),
    loadRuns(),
    loadApprovals(),
  ]);
  return {
    metrics,
    tasks: tasks.slice(0, 8),
    runs: runs.slice(0, 8),
    approvals: approvals.filter((approval) => approval.decision === "pending").slice(0, 6),
  };
}

export async function loadTasks(): Promise<TaskSummary[]> {
  return misJson<TaskSummary[]>("/tasks");
}

export async function loadRuns(): Promise<RunSummary[]> {
  return misJson<RunSummary[]>("/runs");
}

export async function loadToolCalls(): Promise<ToolCallSummary[]> {
  return misJson<ToolCallSummary[]>("/tool-calls");
}

export async function loadEvaluations(): Promise<EvaluationSummary[]> {
  return misJson<EvaluationSummary[]>("/evaluations");
}

export async function loadRuntimeConnectors(): Promise<RuntimeConnectorSummary[]> {
  return misJson<RuntimeConnectorSummary[]>("/runtime-connectors");
}

export async function updateRuntimeConnectorTrust(
  connectorId: string,
  trustStatus: "trusted" | "review_required" | "blocked",
  trustNote?: string,
): Promise<RuntimeConnectorTrustResponse> {
  return misJson<RuntimeConnectorTrustResponse>(`/runtime-connectors/${encodeURIComponent(connectorId)}/trust`, {
    method: "POST",
    body: JSON.stringify({
      trust_status: trustStatus,
      trust_note: trustNote || `Next operator marked ${connectorId} as ${trustStatus}.`,
    }),
  });
}

export async function loadNotionStatus(): Promise<NotionStatus> {
  return misJson<NotionStatus>("/integrations/notion/status");
}

export async function loadNotionPreview(): Promise<NotionPreview> {
  return misJson<NotionPreview>("/integrations/notion/preview", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function runNotionDryRunExport(): Promise<NotionExportResult> {
  return misJson<NotionExportResult>("/integrations/notion/dry-run-export", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function runNotionConfirmedExport(): Promise<NotionExportResult> {
  return misJson<NotionExportResult>("/integrations/notion/export-confirmed", {
    method: "POST",
    body: JSON.stringify({ confirm_export: true, title: "AgentOps MIS Next parity export" }),
  });
}

export async function loadApprovals(): Promise<ApprovalSummary[]> {
  return misJson<ApprovalSummary[]>("/approvals");
}

export async function decideApproval(id: string, decision: "approve" | "reject"): Promise<ApprovalSummary> {
  return misJson<ApprovalSummary>(`/approvals/${encodeURIComponent(id)}/${decision}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function loadMemories(): Promise<MemorySummary[]> {
  return misJson<MemorySummary[]>("/memories");
}

export async function decideMemory(id: string, decision: "approve" | "reject"): Promise<MemorySummary> {
  return misJson<MemorySummary>(`/memories/${encodeURIComponent(id)}/${decision}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function loadAudit(): Promise<AuditSummary[]> {
  return misJson<AuditSummary[]>("/audit?limit=120");
}

export async function loadAgents(): Promise<AgentSummary[]> {
  return misJson<AgentSummary[]>("/agents");
}

export async function loadAgentPerformance(agentId: string): Promise<AgentPerformancePayload> {
  return misJson<AgentPerformancePayload>(`/agents/${encodeURIComponent(agentId)}/performance`);
}

export async function loadSecurityProductionReadiness(): Promise<SecurityReadinessSummary> {
  return misJson<SecurityReadinessSummary>("/security/production-readiness");
}

export async function loadWorkerStatus(): Promise<WorkerStatusSummary> {
  return misJson<WorkerStatusSummary>("/workers/status");
}

export async function loadWorkerAdapterReadiness(): Promise<WorkerAdapterReadinessSummary> {
  return misJson<WorkerAdapterReadinessSummary>("/workers/adapter-readiness");
}

export async function loadWorkerFleet(): Promise<WorkerFleetPayload> {
  return misJson<WorkerFleetPayload>("/workers/fleet");
}

export async function loadWorkerFleetHygiene(options: {
  threshold_sec?: number;
  enrollment_age_sec?: number;
  limit?: number;
} = {}): Promise<WorkerFleetHygienePayload> {
  const params = new URLSearchParams();
  if (options.threshold_sec !== undefined) params.set("threshold_sec", String(options.threshold_sec));
  if (options.enrollment_age_sec !== undefined) params.set("enrollment_age_sec", String(options.enrollment_age_sec));
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return misJson<WorkerFleetHygienePayload>(`/workers/fleet/hygiene${suffix}`);
}

export async function loadOperatorExecutionMode(adapter?: string): Promise<OperatorExecutionModePayload> {
  const suffix = adapter ? `?${new URLSearchParams({ adapter }).toString()}` : "";
  return misJson<OperatorExecutionModePayload>(`/operator/execution-mode${suffix}`);
}

export async function loadAgentGatewayEnrollments(): Promise<AgentGatewayEnrollmentListPayload> {
  return misJson<AgentGatewayEnrollmentListPayload>("/agent-gateway/enrollments");
}

export async function loadAgentGatewaySessions(): Promise<AgentGatewaySessionsPayload> {
  return misJson<AgentGatewaySessionsPayload>("/agent-gateway/sessions");
}

export async function previewAgentGatewayEnrollmentPolicy(input: {
  workspace_id?: string;
  runtime_type?: string;
  scopes: string[];
}): Promise<AgentGatewayEnrollmentPolicyPreview> {
  return misJson<AgentGatewayEnrollmentPolicyPreview>("/agent-gateway/enrollment/policy-preview", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function requestAgentGatewayEnrollment(input: AgentGatewayEnrollmentRequestInput): Promise<AgentGatewayEnrollmentRequestResult> {
  return misJson<AgentGatewayEnrollmentRequestResult>("/agent-gateway/enrollment/request", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function startMockWorkerDaemon(input?: {
  poll_interval?: number;
  max_tasks?: number;
}): Promise<WorkerDaemonResult> {
  return misJson<WorkerDaemonResult>("/workers/local/start", {
    method: "POST",
    body: JSON.stringify({
      adapter: "mock",
      confirm_run: false,
      poll_interval: input?.poll_interval ?? 2,
      max_tasks: input?.max_tasks ?? 0,
      max_errors: 5,
      status: ["planned"],
    }),
  });
}

export async function stopMockWorkerDaemon(): Promise<WorkerDaemonResult> {
  return misJson<WorkerDaemonResult>("/workers/local/stop", {
    method: "POST",
    body: JSON.stringify({ adapter: "mock" }),
  });
}

export async function restartMockWorkerDaemon(input?: {
  poll_interval?: number;
  max_tasks?: number;
}): Promise<WorkerDaemonResult> {
  return misJson<WorkerDaemonResult>("/workers/local/restart", {
    method: "POST",
    body: JSON.stringify({
      adapter: "mock",
      confirm_run: false,
      poll_interval: input?.poll_interval ?? 2,
      max_tasks: input?.max_tasks ?? 0,
      max_errors: 5,
      status: ["planned"],
    }),
  });
}

export async function dispatchLocalWorkerOnce(input: {
  adapter: "mock";
  title?: string;
  description?: string;
  acceptance_criteria?: string;
}): Promise<WorkerDispatchResult> {
  if (input.adapter !== "mock") {
    throw new Error("mock_only_next_parity");
  }
  return misJson<WorkerDispatchResult>("/workers/local/dispatch-once", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function releaseWorkerTask(input: {
  task_id: string;
  reason?: string;
}): Promise<WorkerTaskReleaseResult> {
  return misJson<WorkerTaskReleaseResult>("/workers/tasks/release", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function loadCustomerProjects(limit = 25): Promise<CustomerProjectIndexPayload> {
  return misJson<CustomerProjectIndexPayload>(`/workflows/customer-projects?limit=${encodeURIComponent(String(limit))}`);
}

export async function loadCustomerDeliveryBoard(limit = 12): Promise<CustomerDeliveryBoardPayload> {
  return misJson<CustomerDeliveryBoardPayload>(`/workflows/customer-delivery-board?limit=${encodeURIComponent(String(limit))}`);
}

export async function loadCustomerProjectReport(projectId: string): Promise<CustomerProjectReportPayload> {
  return misJson<CustomerProjectReportPayload>(`/workflows/customer-projects/${encodeURIComponent(projectId)}/report`);
}

export async function loadCommercialEntitlements(): Promise<CommercialEntitlementStatus> {
  return misJson<CommercialEntitlementStatus>("/commercial/entitlements");
}

export async function loadCommercialReleaseStatus(input?: { includeExternalCi?: boolean; requireExternalCi?: boolean; externalCiRunId?: string }): Promise<CommercialReleaseStatusPayload> {
  const params = new URLSearchParams();
  if (input?.includeExternalCi) params.set("include_external_ci_evidence", "1");
  if (input?.requireExternalCi) params.set("require_external_ci_evidence", "1");
  if (input?.externalCiRunId) params.set("external_ci_run_id", input.externalCiRunId);
  const query = params.toString();
  return misJson<CommercialReleaseStatusPayload>(`/commercial/release-status${query ? `?${query}` : ""}`);
}

export async function loadStorageBackendStatus(): Promise<StorageBackendStatus> {
  return misJson<StorageBackendStatus>("/storage/backend-status");
}

export async function loadCustomerTaskTemplates(): Promise<CustomerTaskTemplateListPayload> {
  return misJson<CustomerTaskTemplateListPayload>("/workflows/customer-task-templates");
}

export async function loadBases(): Promise<BasesPayload> {
  return misJson<BasesPayload>("/bases");
}

export async function loadTemplatePackages(): Promise<TemplatePackage[]> {
  return misJson<TemplatePackage[]>("/template-packages");
}

export async function loadTemplateBindings(): Promise<TemplateBinding[]> {
  return misJson<TemplateBinding[]>("/template-bindings");
}

export async function loadWorkflowJobs(limit = 8): Promise<WorkflowJobListPayload> {
  return misJson<WorkflowJobListPayload>(`/workflows/jobs?limit=${encodeURIComponent(String(limit))}`);
}

export async function loadAgentControlSnapshot(): Promise<AgentControlSnapshot> {
  const [agents, security, workerStatus, adapterReadiness, enrollments, sessions] = await Promise.all([
    loadAgents(),
    loadSecurityProductionReadiness(),
    loadWorkerStatus(),
    loadWorkerAdapterReadiness(),
    loadAgentGatewayEnrollments(),
    loadAgentGatewaySessions(),
  ]);
  return { agents, security, workerStatus, adapterReadiness, enrollments, sessions };
}
