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
  contracts?: string[];
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
    billing_call_performed?: boolean;
  };
  token_omitted?: boolean;
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
    free_local_dependency?: boolean;
  };
  checks?: Record<string, boolean>;
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

export async function loadAgentGatewayEnrollments(): Promise<AgentGatewayEnrollmentListPayload> {
  return misJson<AgentGatewayEnrollmentListPayload>("/agent-gateway/enrollments");
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

export async function loadStorageBackendStatus(): Promise<StorageBackendStatus> {
  return misJson<StorageBackendStatus>("/storage/backend-status");
}

export async function loadCustomerTaskTemplates(): Promise<CustomerTaskTemplateListPayload> {
  return misJson<CustomerTaskTemplateListPayload>("/workflows/customer-task-templates");
}

export async function loadAgentControlSnapshot(): Promise<AgentControlSnapshot> {
  const [agents, security, workerStatus, adapterReadiness, enrollments] = await Promise.all([
    loadAgents(),
    loadSecurityProductionReadiness(),
    loadWorkerStatus(),
    loadWorkerAdapterReadiness(),
    loadAgentGatewayEnrollments(),
  ]);
  return { agents, security, workerStatus, adapterReadiness, enrollments };
}
