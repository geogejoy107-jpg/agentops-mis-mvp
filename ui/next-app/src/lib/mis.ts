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
  runtime_type?: string;
  model_provider?: string;
  model_name?: string;
  status?: string;
  permission_level?: string;
  budget_limit_usd?: number;
  created_at?: string;
  updated_at?: string;
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
  ui_routes?: Record<string, string>;
  next_actions?: string[];
  contract?: string;
  live_execution_performed?: boolean;
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
  daemons?: { adapter?: string; running?: boolean; status?: string; worker_status?: string }[];
  adapter_readiness?: {
    recommended_adapter?: string;
    ready_adapters?: string[];
    live_ready_adapters?: string[];
    unavailable_adapters?: string[];
    blocked_adapters?: string[];
  };
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

export async function loadSecurityProductionReadiness(): Promise<SecurityReadinessSummary> {
  return misJson<SecurityReadinessSummary>("/security/production-readiness");
}

export async function loadWorkerStatus(): Promise<WorkerStatusSummary> {
  return misJson<WorkerStatusSummary>("/workers/status");
}

export async function loadWorkerAdapterReadiness(): Promise<WorkerAdapterReadinessSummary> {
  return misJson<WorkerAdapterReadinessSummary>("/workers/adapter-readiness");
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
  const [agents, security, workerStatus, adapterReadiness] = await Promise.all([
    loadAgents(),
    loadSecurityProductionReadiness(),
    loadWorkerStatus(),
    loadWorkerAdapterReadiness(),
  ]);
  return { agents, security, workerStatus, adapterReadiness };
}
