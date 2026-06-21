import { useCallback, useEffect, useState } from "react";
import type {
  Agent,
  Approval,
  AuditLog,
  Evaluation,
  Memory,
  RuntimeConnector,
  Run,
  Task,
  ToolCall,
} from "./mockData";

const API_BASE = import.meta.env.VITE_AGENTOPS_API_BASE || "/mis-api";

export interface DashboardMetrics {
  agents_total: number;
  agents_running: number;
  tasks_completed_total: number;
  total_cost_usd: number;
  avg_task_cost_usd: number;
  failure_rate: number;
  pending_approvals: number;
  stale_or_due_memories: number;
  task_status_distribution: { status: string; count: number }[];
  top_cost_agents: { agent_id: string; name: string; cost_usd: number }[];
  top_failing_agents: { agent_id: string; name: string; failures: number }[];
  runtime_health: Record<string, unknown>[];
  openclaw_import: {
    agents: number;
    cron_tasks: number;
    enabled_cron_tasks: number;
    cron_runs: number;
    failed_runs: number;
    failed_quality_gates: number;
  };
  agent_performance_summary: {
    agent_id: string;
    name: string;
    runtime_type: string;
    total_runs: number;
    success_rate: number;
    avg_duration_ms: number;
    total_cost_usd: number;
    failures: number;
    approval_required_count: number;
  }[];
  recent_runs: Run[];
}

export interface RunDetailPayload {
  run: Run;
  tool_calls: ToolCall[];
  approvals: Approval[];
  evaluations: Evaluation[];
  artifacts?: { artifact_id: string; title: string; artifact_type: string; summary: string; created_at: string }[];
}

export interface TaskDetailPayload {
  task: Task;
  runs: Run[];
  approvals: Approval[];
  evaluations: Evaluation[];
  memories: Memory[];
  artifacts?: { artifact_id: string; title: string; artifact_type: string; summary: string; created_at: string }[];
}

export interface AgentPerformancePayload {
  agent: Agent;
  total_runs: number;
  completed_runs: number;
  failures: number;
  success_rate: number;
  avg_duration_ms: number;
  total_cost_usd: number;
  approval_required_count: number;
  recent_error_types: { error_type: string; count: number }[];
  recent_runs: Run[];
}

export interface LocalBriefResult {
  provider: string;
  workflow: string;
  dry_run: boolean;
  ok?: boolean;
  run_id?: string;
  task_id?: string;
  artifact_id?: string | null;
  duration_ms?: number;
  output_summary?: string;
  error?: string | null;
  note?: string;
  state_preview?: {
    agents_total?: number;
    pending_approvals?: number;
    openclaw_cron_runs?: number;
    recent_real_runs?: number;
  };
}

export interface CustomerTaskWorkflowInput {
  title: string;
  description: string;
  acceptance_criteria: string;
  priority: string;
  risk_level: string;
  owner_agent_id?: string;
  selected_agent_ids: string[];
  template_id?: string;
  workflow_kind?: string;
  confirm_run?: boolean;
}

export interface CustomerWorkerTaskWorkflowInput extends CustomerTaskWorkflowInput {
  adapter?: "mock" | "hermes" | "openclaw";
}

export interface CustomerTaskWorkflowResult {
  provider: string;
  workflow: string;
  dry_run: boolean;
  ok?: boolean;
  adapter?: string;
  agent_id?: string;
  task_id: string;
  run_id?: string;
  artifact_id?: string | null;
  duration_ms?: number;
  output_summary?: string;
  error?: string | null;
  reason?: string;
  readiness?: string;
  recommended_action?: string;
  note?: string;
  requires?: Record<string, unknown>;
  selected_agent_ids?: string[];
  evidence?: {
    tool_calls?: number;
    evaluations?: number;
    runtime_events?: number;
    audit_logs?: number;
    artifacts?: number;
    memories?: number;
    approvals?: number;
  };
}

export interface KbBotProjectWorkflowResult {
  provider: string;
  workflow: string;
  dry_run: boolean;
  ok: boolean;
  project_id?: string;
  task_id?: string;
  run_id?: string;
  artifact_id?: string | null;
  approval_ids?: string[];
  results?: {
    task_id: string;
    run_id: string;
    agent_id: string;
    approval_id?: string | null;
    artifact_id?: string | null;
    evaluation_id?: string;
    memory_id?: string;
  }[];
  safe_defaults?: Record<string, unknown>;
  open_pages?: Record<string, string>;
  report_url?: string;
  error?: string | null;
}

export interface CustomerProjectReportArtifactResult {
  ok: boolean;
  created: boolean;
  project_id: string;
  report_url: string;
  content_hash: string;
  raw_report_omitted: boolean;
  token_omitted: boolean;
  artifact?: {
    artifact_id: string;
    task_id?: string | null;
    run_id?: string | null;
    artifact_type: string;
    title: string;
    uri: string;
    summary: string;
    created_at: string;
  };
  safe_defaults?: Record<string, unknown>;
  error?: string | null;
}

export interface CustomerProjectReportPayload {
  project_id: string;
  status: string;
  markdown: string;
  counts: {
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
  };
  artifact_id?: string | null;
  report_artifact_id?: string | null;
  approval_ids?: string[];
  safe_defaults?: Record<string, unknown>;
  error?: string | null;
}

export interface CustomerProjectSummary {
  project_id: string;
  title: string;
  status: string;
  task_count: number;
  completed_tasks: number;
  failed_or_blocked_tasks: number;
  run_count: number;
  completed_runs: number;
  pending_approvals: number;
  artifact_count: number;
  last_task_id?: string | null;
  last_run_id?: string | null;
  delivery_artifact_id?: string | null;
  report_artifact_id?: string | null;
  approval_ids?: string[];
  created_at?: string;
  updated_at?: string;
  report_url: string;
  ui_report_url: string;
  safe_defaults?: Record<string, unknown>;
}

export interface CustomerProjectIndexPayload {
  projects: CustomerProjectSummary[];
  total: number;
  limit: number;
  safe_defaults?: Record<string, unknown>;
}

export interface CustomerDeliveryBoardItem {
  delivery_id: string;
  status: string;
  title: string;
  task_id?: string | null;
  run_id?: string | null;
  artifact_id?: string | null;
  artifact_type?: string | null;
  project_id?: string | null;
  owner_agent_id?: string | null;
  run_status?: string | null;
  task_status?: string | null;
  priority?: string | null;
  risk_level?: string | null;
  summary?: string;
  created_at?: string;
  report_url?: string | null;
  ui_report_url?: string | null;
  task_url?: string | null;
  run_url?: string | null;
  approval_ids?: string[];
  pending_approval_ids?: string[];
  evaluation_summary?: {
    count?: number;
    failed?: number;
    latest_score?: number | null;
    latest_pass_fail?: string | null;
  };
  delivery_approval_gate?: {
    required?: boolean;
    pass?: boolean;
    status?: string;
    manifest_id?: string | null;
    message?: string;
    evidence_counts?: Record<string, number>;
    failed_checks?: string[];
    token_omitted?: boolean;
    verification?: {
      status?: string;
      failed_checks?: { id?: string; message?: string; ok?: boolean }[];
      evidence_counts?: Record<string, number>;
    };
  };
  evidence?: Record<string, number>;
  next_action?: string;
}

export interface CustomerDeliveryBoardPayload {
  provider: string;
  operation: string;
  status: string;
  summary: {
    deliveries: number;
    ready: number;
    waiting_approval: number;
    in_progress: number;
    needs_attention: number;
    pending_approvals: number;
    artifacts: number;
    verified_plan_evidence_manifests?: number;
    missing_plan_evidence_manifests?: number;
  };
  deliveries: CustomerDeliveryBoardItem[];
  gates: { id: string; label: string; ok: boolean; value?: string | number | boolean }[];
  next_actions: string[];
  safety: {
    read_only: boolean;
    ledger_mutated: boolean;
    live_execution_performed: boolean;
    raw_prompt_omitted: boolean;
    raw_response_omitted: boolean;
    token_omitted: boolean;
  };
  token_omitted?: boolean;
}

export interface CustomerTaskTemplate {
  template_id: string;
  name: string;
  name_en?: string;
  workflow: string;
  scenario: string;
  status: string;
  risk_level: string;
  priority: string;
  description: string;
  default_title: string;
  default_description: string;
  default_acceptance: string;
  agent_roles: string[];
  required_approvals: string[];
  safe_defaults: Record<string, unknown>;
  entrypoint: string;
}

export interface CustomerTaskTemplateListPayload {
  templates: CustomerTaskTemplate[];
  safe_defaults: Record<string, unknown>;
}

export interface WorkflowJob {
  job_id: string;
  workspace_id?: string;
  workflow_type: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  template_id?: string | null;
  adapter?: string | null;
  confirm_run?: boolean;
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
  result?: Partial<CustomerTaskWorkflowResult & KbBotProjectWorkflowResult>;
  raw_request_omitted?: boolean;
  token_omitted?: boolean;
  age_sec?: number;
  threshold_sec?: number;
  stuck_reason?: string;
}

export interface WorkflowJobSubmitPayload {
  ok: boolean;
  provider: string;
  job_id: string;
  status_url: string;
  job: WorkflowJob;
  raw_request_omitted: boolean;
  token_omitted: boolean;
}

export interface WorkflowJobListPayload {
  jobs: WorkflowJob[];
  token_omitted?: boolean;
}

export interface WorkflowJobStuckPayload {
  provider: string;
  threshold_sec: number;
  stuck_jobs: WorkflowJob[];
  token_omitted?: boolean;
}

export interface WorkflowJobMarkFailedPayload {
  ok: boolean;
  provider?: string;
  job_id: string;
  job?: WorkflowJob;
  marked_failed?: boolean;
  reason?: string;
  token_omitted?: boolean;
}

export interface WorkerStatusPayload {
  provider: string;
  status: string;
  worker_count: number;
  running_workers: number;
  recent_completed_runs: number;
  pending_worker_tasks: number;
  stuck_worker_tasks: number;
  stuck_workflow_jobs?: number;
  remote_worker_count: number;
  total_remote_enrollments: number;
  active_remote_enrollments: number;
  fresh_remote_enrollments: number;
  stale_remote_enrollments: number;
  never_seen_remote_enrollments: number;
  active_remote_sessions: number;
  remote_worker_health: Record<string, unknown>;
  adapter_readiness?: WorkerAdapterReadinessSummary;
  fleet_health?: WorkerFleetHealth;
  daemons: WorkerDaemonStatus[];
  workers: Agent[];
  recent_runs: Run[];
  recent_tasks: Task[];
  stuck_tasks: StuckWorkerTask[];
  stuck_workflow_job_refs?: {
    job_id: string;
    workflow_type?: string;
    status?: string;
    age_sec?: number;
    stuck_reason?: string;
  }[];
  recent_events: Record<string, unknown>[];
}

export interface WorkerFleetLane {
  lane_id: string;
  lane_type: string;
  adapter?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  workspace_id?: string | null;
  runtime_type?: string | null;
  status: string;
  health: string;
  heartbeat_state?: string | null;
  session_state?: string | null;
  active_session_count: number;
  last_seen_at?: string | null;
  expires_at?: string | null;
  scope_count?: number;
  workload?: Record<string, unknown>;
  next_action?: string;
  safe_ref?: string | null;
  token_omitted?: boolean;
  session_id_omitted?: boolean;
  token_id_omitted?: boolean;
}

export interface WorkerFleetPayload {
  provider: string;
  operation: string;
  status: string;
  summary: {
    lane_count: number;
    lane_counts: Record<string, number>;
    health_counts: Record<string, number>;
    local_daemon_count: number;
    running_local_daemons: number;
    remote_worker_count: number;
    fresh_remote_enrollments: number;
    stale_remote_enrollments: number;
    never_seen_remote_enrollments: number;
    active_remote_sessions: number;
    stuck_worker_tasks: number;
    stuck_workflow_jobs: number;
    recommended_adapter?: string;
  };
  lanes: WorkerFleetLane[];
  next_actions: string[];
  contract?: string;
  safety: {
    read_only: boolean;
    live_execution_performed: boolean;
    token_omitted: boolean;
    session_id_omitted: boolean;
    raw_prompt_omitted: boolean;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
}

export type WorkerAdapterName = "mock" | "hermes" | "openclaw";

export interface WorkerAdapterReadinessSummary {
  ready_adapters?: WorkerAdapterName[];
  live_ready_adapters?: WorkerAdapterName[];
  review_required_adapters?: WorkerAdapterName[];
  blocked_adapters?: WorkerAdapterName[];
  unavailable_adapters?: WorkerAdapterName[];
  recommended_adapter?: WorkerAdapterName;
}

export interface WorkerAdapterReadinessItem {
  adapter: WorkerAdapterName;
  ok: boolean;
  readiness: "ready" | "review_required" | "blocked" | "unavailable" | string;
  connector_id?: string | null;
  trust_status?: string;
  requires_confirm_run?: boolean;
  target_resource?: string | null;
  checks?: Record<string, unknown>;
  recommended_action?: string;
  last_error?: string | null;
  token_omitted?: boolean;
}

export interface WorkerAdapterReadinessPayload {
  provider: string;
  status: "ready" | "degraded" | "blocked" | string;
  summary: WorkerAdapterReadinessSummary;
  adapters: Record<WorkerAdapterName, WorkerAdapterReadinessItem>;
  contract?: string;
  live_execution_performed: boolean;
  token_omitted?: boolean;
}

export interface WorkerFleetGate {
  id: string;
  status: string;
  summary: string;
  action?: string;
}

export interface WorkerFleetHealth {
  overall: string;
  contract?: string;
  gates: WorkerFleetGate[];
  recommended_actions: string[];
  remote_status?: string;
  token_omitted?: boolean;
}

export interface LocalReadinessGate {
  id: string;
  label: string;
  ok: boolean;
  status: string;
  detail: string;
  next_action: string;
}

export interface LocalReadinessEvidence {
  tasks: number;
  planned_tasks: number;
  completed_tasks: number;
  runs: number;
  completed_runs: number;
  tool_calls: number;
  evaluations: number;
  audit_logs: number;
  artifacts: number;
  memories: number;
  memory_candidates: number;
  approved_memories: number;
  pending_approvals: number;
  approvals: number;
  workflow_jobs: number;
  customer_worker_artifacts: number;
  closed_loop_runs: number;
  has_task_run_tool_eval_audit_artifact_chain: boolean;
  has_memory_or_knowledge: boolean;
  has_approval_flow: boolean;
}

export interface LocalReadinessPayload {
  provider: string;
  operation: string;
  status: "ready" | "attention" | "blocked" | string;
  ok: boolean;
  workspace_id?: string;
  gates: LocalReadinessGate[];
  evidence: LocalReadinessEvidence;
  next_actions: string[];
  contract?: string;
  adapter_readiness: WorkerAdapterReadinessSummary;
  token_omitted: boolean;
  live_execution_performed: boolean;
}

export interface IntegrationInboxSummary {
  ready_for_review: number;
  still_running: number;
  blocked: number;
  late_or_stale: number;
  needs_memory_review: number;
  total: number;
}

export interface IntegrationInboxItem {
  item_id: string;
  bucket: string;
  title: string;
  status: string;
  task_id?: string | null;
  run_id?: string | null;
  job_id?: string | null;
  artifact_id?: string | null;
  agent_id?: string | null;
  owner_agent_id?: string | null;
  age_sec: number;
  evidence?: Record<string, unknown>;
  recommended_action?: string;
  created_at?: string;
  updated_at?: string;
}

export interface IntegrationInboxPayload {
  provider: string;
  operation: string;
  status: string;
  filter?: {
    bucket: string;
    limit: number;
    threshold_sec: number;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
  summary: IntegrationInboxSummary;
  inbox_items: IntegrationInboxItem[];
  recommended_next_actions: string[];
  safety: {
    read_only: boolean;
    ledger_mutated: boolean;
    raw_prompt_omitted: boolean;
  };
}

export interface IntegrationInboxOptions {
  bucket?: string;
  limit?: number;
  threshold_sec?: number;
}

export interface ReviewQueueSummary {
  pending_approvals: number;
  memory_candidates: number;
  ready_deliveries: number;
  waiting_deliveries: number;
  needs_attention_deliveries: number;
  review_items_total: number;
  returned_items: number;
  retrieved_pending_approvals?: number;
  retrieved_memory_candidates?: number;
}

export interface ReviewQueueItem {
  item_type: "approval" | "memory_candidate" | "customer_delivery" | string;
  item_id: string;
  status: string;
  kind?: string | null;
  title: string;
  summary?: string;
  task_id?: string | null;
  run_id?: string | null;
  agent_id?: string | null;
  artifact_id?: string | null;
  created_at?: string;
  updated_at?: string;
  next_action?: string;
  cli_action?: string;
  alternate_cli_action?: string | null;
  links?: Record<string, string | null>;
}

export interface ReviewQueuePayload {
  provider: string;
  operation: string;
  status: string;
  limit: number;
  summary: ReviewQueueSummary;
  review_items: ReviewQueueItem[];
  gates: { id: string; label: string; ok: boolean; value?: string | number | boolean }[];
  next_actions: string[];
  safety: {
    read_only: boolean;
    ledger_mutated: boolean;
    live_execution_performed: boolean;
    raw_prompt_omitted: boolean;
    raw_response_omitted: boolean;
    token_omitted: boolean;
  };
  token_omitted?: boolean;
}

export interface StuckWorkerTask extends Task {
  age_sec?: number;
  threshold_sec?: number;
  running_run_id?: string | null;
  running_run_started_at?: string | null;
  stuck_reason?: string;
}

export interface WorkerDaemonStatus {
  adapter: "mock" | "hermes" | "openclaw";
  status: string;
  running: boolean;
  pid?: number | null;
  agent_id?: string | null;
  started_at?: string | null;
  stopped_at?: string | null;
  poll_interval?: number | null;
  max_tasks?: number | null;
  confirm_run?: boolean;
  log_path?: string;
  state_path?: string;
  worker_status?: string | null;
  state_updated_at?: string | null;
  processed?: number;
  iterations?: number;
  total_errors?: number;
  consecutive_errors?: number;
  continue_on_error?: boolean;
  last_error?: Record<string, unknown> | null;
  last_result?: Record<string, unknown> | null;
  log_tail?: string[];
}

export interface WorkerDispatchResult {
  provider: string;
  dry_run: boolean;
  ok: boolean;
  adapter: "mock" | "hermes" | "openclaw";
  agent_id: string;
  task_id: string;
  duration_ms: number;
  worker_result?: {
    ok?: boolean;
    processed?: number;
    results?: {
      processed?: boolean;
      task_id?: string;
      run_id?: string;
      adapter?: string;
      ok?: boolean;
      output_summary?: string;
      error_type?: string | null;
    }[];
  };
  error?: string | null;
}

export interface WorkerDaemonResult {
  provider: string;
  ok: boolean;
  already_running?: boolean;
  daemon?: WorkerDaemonStatus;
  daemons?: WorkerDaemonStatus[];
  error?: string;
}

export interface WorkerDaemonLogPayload {
  provider: string;
  daemon: WorkerDaemonStatus;
}

export interface WorkerTaskReleaseResult {
  released: boolean;
  task: Task;
  released_runs: string[];
  token_omitted: boolean;
  error?: string;
}

export interface AgentGatewayEnrollment {
  token_id: string;
  workspace_id: string;
  agent_id: string;
  scopes: string[];
  status: string;
  label: string;
  heartbeat_timeout_sec: number;
  created_at: string;
  expires_at: string;
  revoked_at?: string | null;
  last_used_at?: string | null;
  last_heartbeat_at?: string | null;
  heartbeat_state: "fresh" | "stale" | "never_seen" | string;
}

export interface AgentGatewayEnrollmentListPayload {
  enrollments: AgentGatewayEnrollment[];
  valid_scopes: string[];
}

export interface AgentGatewaySession {
  session_id: string;
  parent_token_id?: string | null;
  workspace_id: string;
  agent_id: string;
  scopes: string[];
  status: string;
  session_state: string;
  created_at: string;
  expires_at: string;
  revoked_at?: string | null;
  last_used_at?: string | null;
}

export interface AgentGatewaySessionListPayload {
  sessions: AgentGatewaySession[];
  valid_scopes: string[];
  token_omitted: boolean;
}

export interface AgentGatewayStatusPayload {
  provider: string;
  status: string;
  auth: {
    mode: string;
    authenticated: boolean;
    agent_id: string;
    workspace_id: string;
    scopes: string[];
    token_id?: string;
    token_status?: string;
    heartbeat_state?: string;
    heartbeat_timeout_sec?: number;
    expires_at?: string;
    last_used_at?: string | null;
    last_heartbeat_at?: string | null;
    session_id?: string;
    parent_token_id?: string;
    session_expires_at?: string;
  };
  valid_scopes: string[];
  token_omitted: boolean;
}

export interface SecurityProductionGate {
  id: string;
  label: string;
  status: string;
  ok: boolean;
  detail: string;
  next_action: string;
}

export interface SecurityProductionReadinessPayload {
  provider: string;
  operation: string;
  status: string;
  production_ready: boolean;
  production_requested: boolean;
  auth_mode: string;
  gateway_status_code: number;
  gates: SecurityProductionGate[];
  next_actions: string[];
  contract?: string;
  safety: {
    read_only: boolean;
    live_execution_performed: boolean;
    token_omitted: boolean;
    raw_prompt_omitted: boolean;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
}

export interface DemoReadinessShot {
  id: string;
  label: string;
  route?: string;
  command?: string;
  status: string;
  ok: boolean;
  detail: string;
  next_action: string;
}

export interface DemoReadinessPayload {
  provider: string;
  operation: string;
  status: string;
  demo_ready: boolean;
  production_ready: boolean;
  summary: {
    shot_count: number;
    ready_shots: number;
    blocker_count: number;
    warning_count: number;
    closed_loop_runs: number;
    customer_worker_artifacts: number;
    fleet_lanes: number;
    ready_inbox_items: number;
  };
  shots: DemoReadinessShot[];
  next_actions: string[];
  references?: Record<string, string>;
  contract?: string;
  safety: {
    read_only: boolean;
    ledger_mutated: boolean;
    live_execution_performed: boolean;
    token_omitted: boolean;
    raw_prompt_omitted: boolean;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
}

export interface AgentGatewayEnrollmentCreateInput {
  agent_id: string;
  name: string;
  role?: string;
  runtime_type: string;
  workspace_id?: string;
  label?: string;
  scopes: string[];
  ttl_days?: number;
  heartbeat_timeout_sec?: number;
}

export interface AgentGatewayEnrollmentCreateResult {
  created: boolean;
  token_id: string;
  agent_id: string;
  workspace_id: string;
  scopes: string[];
  expires_at: string;
  heartbeat_timeout_sec: number;
  token: string;
  note: string;
  next_steps?: {
    token_policy: string;
    base_url: string;
    agent_id: string;
    workspace_id: string;
    adapter: string;
    install?: string;
    env: string[];
    verify: string;
    preflight?: string;
    session?: string;
    heartbeat: string;
    run_once: string;
    run_loop: string;
    launchd_template?: string;
    systemd_template?: string;
    repo_fallback_run_once?: string;
    repo_fallback_run_loop?: string;
    notes: string[];
    token_omitted: boolean;
  };
}

export interface AgentGatewayEnrollmentRequestResult {
  request: {
    request_id: string;
    approval_id: string;
    task_id: string;
    run_id: string;
    workspace_id: string;
    agent_id: string;
    name: string;
    runtime_type: string;
    status: string;
    scopes: string[];
  };
  approval: Approval;
  token_issued: boolean;
  token_omitted: boolean;
}

export interface AgentGatewayEnrollmentRotateResult extends AgentGatewayEnrollmentCreateResult {
  rotated: boolean;
  rotated_from_token_id: string;
  revoked: number;
}

export interface AgentGatewayEnrollmentRevokeResult {
  revoked: number;
  changed: number;
  tokens: string[];
  sessions_revoked?: number;
  sessions?: string[];
}

export interface AgentGatewaySessionRevokeResult {
  revoked: number;
  sessions: string[];
  token_omitted: boolean;
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function parseJsonArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value !== "string" || !value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }
}

function numberValue(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function boolValue(value: unknown): boolean {
  return value === true || value === 1 || value === "1" || value === "true";
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

async function optionalApiJson<T>(path: string, fallback: T): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (res.status === 404) {
    return fallback;
  }
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

async function apiJsonWithStatuses<T>(path: string, init: RequestInit | undefined, acceptedStatuses: number[]): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok && !acceptedStatuses.includes(res.status)) {
    throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export function useLiveData<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await loader());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, deps);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, loading, error, refresh };
}

export function normalizeAgent(row: Record<string, unknown>, perf?: DashboardMetrics["agent_performance_summary"][number]): Agent {
  return {
    agent_id: String(row.agent_id || perf?.agent_id || ""),
    name: String(row.name || perf?.name || "Unnamed Agent"),
    role: String(row.role || "Agent"),
    description: String(row.description || ""),
    runtime_type: String(row.runtime_type || perf?.runtime_type || "mock") as Agent["runtime_type"],
    model_provider: String(row.model_provider || "unknown"),
    model_name: String(row.model_name || "unknown"),
    status: String(row.status || "idle") as Agent["status"],
    permission_level: String(row.permission_level || "standard"),
    allowed_tools: parseJsonArray(row.allowed_tools),
    budget_limit_usd: numberValue(row.budget_limit_usd, 0),
    budget_used_usd: numberValue(perf?.total_cost_usd, 0),
    owner_user_id: String(row.owner_user_id || "usr_founder"),
    success_rate: numberValue(perf?.success_rate, 0),
    run_count: numberValue(perf?.total_runs, 0),
    failure_count: numberValue(perf?.failures, 0),
    approval_count: numberValue(perf?.approval_required_count, 0),
    created_at: String(row.created_at || ""),
    updated_at: String(row.updated_at || row.created_at || ""),
  };
}

export function normalizeTask(row: Record<string, unknown>): Task {
  return {
    task_id: String(row.task_id || ""),
    title: String(row.title || "Untitled task"),
    description: String(row.description || ""),
    requester_id: String(row.requester_id || "usr_founder"),
    owner_agent_id: String(row.owner_agent_id || ""),
    collaborator_agent_ids: parseJsonArray(row.collaborator_agent_ids),
    status: String(row.status || "planned") as Task["status"],
    priority: String(row.priority || "medium") as Task["priority"],
    due_date: String(row.due_date || ""),
    acceptance_criteria: String(row.acceptance_criteria || ""),
    risk_level: String(row.risk_level || "medium") as Task["risk_level"],
    budget_limit_usd: numberValue(row.budget_limit_usd, 0),
    created_at: String(row.created_at || ""),
    updated_at: String(row.updated_at || row.created_at || ""),
  };
}

export function normalizeRun(row: Record<string, unknown>): Run {
  return {
    run_id: String(row.run_id || ""),
    task_id: String(row.task_id || ""),
    agent_id: String(row.agent_id || ""),
    runtime_type: String(row.runtime_type || "mock") as Run["runtime_type"],
    status: String(row.status || "unknown"),
    started_at: String(row.started_at || row.created_at || ""),
    ended_at: row.ended_at ? String(row.ended_at) : null,
    duration_ms: numberValue(row.duration_ms, 0),
    input_summary: String(row.input_summary || ""),
    output_summary: String(row.output_summary || ""),
    model_provider: String(row.model_provider || ""),
    model_name: String(row.model_name || ""),
    input_tokens: numberValue(row.input_tokens, 0),
    output_tokens: numberValue(row.output_tokens, 0),
    reasoning_tokens: numberValue(row.reasoning_tokens, 0),
    cost_usd: numberValue(row.cost_usd, 0),
    error_type: row.error_type ? String(row.error_type) : null,
    error_message: row.error_message ? String(row.error_message) : null,
    trace_id: String(row.trace_id || ""),
    parent_run_id: row.parent_run_id ? String(row.parent_run_id) : null,
    delegation_id: row.delegation_id ? String(row.delegation_id) : null,
    approval_required: boolValue(row.approval_required),
    created_at: String(row.created_at || row.started_at || ""),
  };
}

export function normalizeApproval(row: Record<string, unknown>): Approval {
  return {
    approval_id: String(row.approval_id || ""),
    task_id: String(row.task_id || ""),
    run_id: String(row.run_id || ""),
    tool_call_id: String(row.tool_call_id || ""),
    requested_by_agent_id: String(row.requested_by_agent_id || ""),
    approver_user_id: row.approver_user_id ? String(row.approver_user_id) : null,
    decision: String(row.decision || "pending") as Approval["decision"],
    reason: String(row.reason || ""),
    expires_at: String(row.expires_at || row.created_at || ""),
    created_at: String(row.created_at || ""),
    decided_at: row.decided_at ? String(row.decided_at) : null,
  };
}

export function normalizeMemory(row: Record<string, unknown>): Memory {
  return {
    memory_id: String(row.memory_id || ""),
    scope: String(row.scope || "project") as Memory["scope"],
    memory_type: String(row.memory_type || "note"),
    canonical_text: String(row.canonical_text || ""),
    source_type: String(row.source_type || ""),
    confidence: numberValue(row.confidence, 0),
    review_status: String(row.review_status || "candidate") as Memory["review_status"],
    task_id: row.task_id ? String(row.task_id) : null,
    agent_id: row.agent_id ? String(row.agent_id) : null,
    created_at: String(row.created_at || ""),
    updated_at: String(row.updated_at || row.created_at || ""),
  };
}

export function normalizeEvaluation(row: Record<string, unknown>): Evaluation {
  return {
    evaluation_id: String(row.evaluation_id || ""),
    task_id: String(row.task_id || ""),
    run_id: String(row.run_id || ""),
    agent_id: String(row.agent_id || ""),
    evaluator_type: String(row.evaluator_type || "rule"),
    score: numberValue(row.score, 0),
    pass_fail: String(row.pass_fail || "fail") as Evaluation["pass_fail"],
    notes: String(row.notes || ""),
    created_at: String(row.created_at || ""),
  };
}

export function normalizeToolCall(row: Record<string, unknown>): ToolCall {
  return {
    tool_call_id: String(row.tool_call_id || ""),
    run_id: String(row.run_id || ""),
    agent_id: String(row.agent_id || ""),
    tool_name: String(row.tool_name || ""),
    tool_version: String(row.tool_version || ""),
    tool_category: String(row.tool_category || "custom") as ToolCall["tool_category"],
    normalized_args_json: String(row.normalized_args_json || "{}"),
    target_resource: String(row.target_resource || ""),
    risk_level: String(row.risk_level || "low") as ToolCall["risk_level"],
    status: String(row.status || ""),
    result_summary: String(row.result_summary || ""),
    started_at: String(row.started_at || row.created_at || ""),
    ended_at: String(row.ended_at || ""),
    created_at: String(row.created_at || ""),
  };
}

export function normalizeAudit(row: Record<string, unknown>): AuditLog {
  return {
    audit_id: String(row.audit_id || ""),
    actor_type: String(row.actor_type || "system") as AuditLog["actor_type"],
    actor_id: String(row.actor_id || "system"),
    action: String(row.action || ""),
    entity_type: String(row.entity_type || ""),
    entity_id: String(row.entity_id || ""),
    metadata_json: JSON.stringify(row.metadata_json || row.metadata || {}),
    created_at: String(row.created_at || ""),
  };
}

export function normalizeConnector(row: Record<string, unknown>): RuntimeConnector {
  return {
    connector_id: String(row.runtime_connector_id || row.connector_id || ""),
    provider: String(row.provider || ""),
    mode: String(row.connector_type || row.mode || ""),
    status: String(row.status || "unknown"),
    last_checked: String(row.last_health_at || row.updated_at || row.created_at || new Date().toISOString()),
    real_run_enabled: boolValue(row.allow_real_run),
    confirm_required: boolValue(row.require_confirm_run),
    trust_status: String(row.trust_status || "trusted"),
    trust_note: row.trust_note ? String(row.trust_note) : undefined,
    trust_updated_at: row.trust_updated_at ? String(row.trust_updated_at) : undefined,
    endpoint: String(row.base_url || row.binary_path || ""),
    import_count: undefined,
    last_event: row.last_error ? String(row.last_error) : undefined,
  };
}

export async function loadDashboard(): Promise<DashboardMetrics> {
  const raw = await apiJson<Record<string, unknown>>("/dashboard/metrics");
  return {
    ...(raw as unknown as DashboardMetrics),
    recent_runs: asArray<Record<string, unknown>>(raw.recent_runs).map(normalizeRun),
  };
}

export async function loadAgents(metrics?: DashboardMetrics): Promise<Agent[]> {
  const raw = await apiJson<Record<string, unknown>[]>("/agents");
  const perf = new Map((metrics?.agent_performance_summary || []).map((item) => [item.agent_id, item]));
  return raw.map((row) => normalizeAgent(row, perf.get(String(row.agent_id))));
}

export async function loadTasks(): Promise<Task[]> {
  return (await apiJson<Record<string, unknown>[]>("/tasks")).map(normalizeTask);
}

export async function loadRuns(query = ""): Promise<Run[]> {
  return (await apiJson<Record<string, unknown>[]>(`/runs${query}`)).map(normalizeRun);
}

export async function loadApprovals(): Promise<Approval[]> {
  return (await apiJson<Record<string, unknown>[]>("/approvals")).map(normalizeApproval);
}

export async function loadToolCalls(): Promise<ToolCall[]> {
  return (await apiJson<Record<string, unknown>[]>("/tool-calls")).map(normalizeToolCall);
}

export async function loadMemories(): Promise<Memory[]> {
  return (await apiJson<Record<string, unknown>[]>("/memories")).map(normalizeMemory);
}

export async function loadRuntimeConnectors(): Promise<RuntimeConnector[]> {
  return (await apiJson<Record<string, unknown>[]>("/runtime-connectors")).map(normalizeConnector);
}

export async function updateRuntimeConnectorTrust(connectorId: string, input: { trust_status: "trusted" | "review_required" | "blocked"; trust_note?: string }): Promise<{ connector: Record<string, unknown>; token_omitted: boolean }> {
  return apiJson<{ connector: Record<string, unknown>; token_omitted: boolean }>(`/runtime-connectors/${encodeURIComponent(connectorId)}/trust`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function loadAudit(): Promise<AuditLog[]> {
  return (await apiJson<Record<string, unknown>[]>("/audit")).map(normalizeAudit);
}

export async function loadRunDetail(id: string): Promise<RunDetailPayload> {
  const raw = await apiJson<Record<string, unknown>>(`/runs/${encodeURIComponent(id)}`);
  return {
    run: normalizeRun(raw.run as Record<string, unknown>),
    tool_calls: asArray<Record<string, unknown>>(raw.tool_calls).map(normalizeToolCall),
    approvals: asArray<Record<string, unknown>>(raw.approvals).map(normalizeApproval),
    evaluations: asArray<Record<string, unknown>>(raw.evaluations).map(normalizeEvaluation),
    artifacts: asArray(raw.artifacts),
  };
}

export async function loadTaskDetail(id: string): Promise<TaskDetailPayload> {
  const raw = await apiJson<Record<string, unknown>>(`/tasks/${encodeURIComponent(id)}`);
  return {
    task: normalizeTask(raw.task as Record<string, unknown>),
    runs: asArray<Record<string, unknown>>(raw.runs).map(normalizeRun),
    approvals: asArray<Record<string, unknown>>(raw.approvals).map(normalizeApproval),
    evaluations: asArray<Record<string, unknown>>(raw.evaluations).map(normalizeEvaluation),
    memories: asArray<Record<string, unknown>>(raw.memories).map(normalizeMemory),
    artifacts: asArray(raw.artifacts),
  };
}

export async function loadAgentPerformance(id: string): Promise<AgentPerformancePayload> {
  const raw = await apiJson<Record<string, unknown>>(`/agents/${encodeURIComponent(id)}/performance`);
  const perf = {
    agent_id: String((raw.agent as Record<string, unknown>)?.agent_id || id),
    name: String((raw.agent as Record<string, unknown>)?.name || ""),
    runtime_type: String((raw.agent as Record<string, unknown>)?.runtime_type || "mock"),
    total_runs: numberValue(raw.total_runs, 0),
    success_rate: numberValue(raw.success_rate, 0),
    avg_duration_ms: numberValue(raw.avg_duration_ms, 0),
    total_cost_usd: numberValue(raw.total_cost_usd, 0),
    failures: numberValue(raw.failures, 0),
    approval_required_count: numberValue(raw.approval_required_count, 0),
  };
  return {
    agent: normalizeAgent((raw.agent || {}) as Record<string, unknown>, perf),
    total_runs: numberValue(raw.total_runs, 0),
    completed_runs: numberValue(raw.completed_runs, 0),
    failures: numberValue(raw.failures, 0),
    success_rate: numberValue(raw.success_rate, 0),
    avg_duration_ms: numberValue(raw.avg_duration_ms, 0),
    total_cost_usd: numberValue(raw.total_cost_usd, 0),
    approval_required_count: numberValue(raw.approval_required_count, 0),
    recent_error_types: asArray(raw.recent_error_types),
    recent_runs: asArray<Record<string, unknown>>(raw.recent_runs).map(normalizeRun),
  };
}

export async function decideApproval(id: string, decision: "approve" | "reject"): Promise<Approval> {
  const raw = await apiJson<Record<string, unknown>>(`/approvals/${encodeURIComponent(id)}/${decision}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return normalizeApproval(raw);
}

export async function decideMemory(id: string, decision: "approve" | "reject"): Promise<Memory> {
  const raw = await apiJson<Record<string, unknown>>(`/memories/${encodeURIComponent(id)}/${decision}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return normalizeMemory(raw);
}

export async function runLocalBrief(confirmRun = false): Promise<LocalBriefResult> {
  return apiJson<LocalBriefResult>("/workflows/local-brief", {
    method: "POST",
    body: JSON.stringify(confirmRun ? { confirm_run: true } : {}),
  });
}

export async function runCustomerTaskWorkflow(input: CustomerTaskWorkflowInput): Promise<CustomerTaskWorkflowResult> {
  return apiJson<CustomerTaskWorkflowResult>("/workflows/customer-task", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function runCustomerWorkerTaskWorkflow(input: CustomerWorkerTaskWorkflowInput): Promise<CustomerTaskWorkflowResult> {
  return apiJson<CustomerTaskWorkflowResult>("/workflows/customer-worker-task", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function submitCustomerWorkerTaskJob(input: CustomerWorkerTaskWorkflowInput): Promise<WorkflowJobSubmitPayload> {
  return apiJsonWithStatuses<WorkflowJobSubmitPayload>("/workflows/customer-worker-task/submit", {
    method: "POST",
    body: JSON.stringify(input),
  }, [409]);
}

export async function runKbBotProjectWorkflow(): Promise<KbBotProjectWorkflowResult> {
  return apiJson<KbBotProjectWorkflowResult>("/workflows/kb-bot-project", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function loadCustomerTaskTemplates(): Promise<CustomerTaskTemplateListPayload> {
  const raw = await apiJson<Record<string, unknown>>("/workflows/customer-task-templates");
  return {
    templates: asArray<Record<string, unknown>>(raw.templates).map((item) => ({
      template_id: String(item.template_id || ""),
      name: String(item.name || item.template_id || ""),
      name_en: item.name_en ? String(item.name_en) : undefined,
      workflow: String(item.workflow || ""),
      scenario: String(item.scenario || ""),
      status: String(item.status || ""),
      risk_level: String(item.risk_level || "medium"),
      priority: String(item.priority || "medium"),
      description: String(item.description || ""),
      default_title: String(item.default_title || item.name || ""),
      default_description: String(item.default_description || item.description || ""),
      default_acceptance: String(item.default_acceptance || ""),
      agent_roles: asArray(item.agent_roles).map(String),
      required_approvals: asArray(item.required_approvals).map(String),
      safe_defaults: (item.safe_defaults || {}) as Record<string, unknown>,
      entrypoint: String(item.entrypoint || ""),
    })),
    safe_defaults: (raw.safe_defaults || {}) as Record<string, unknown>,
  };
}

export async function runCustomerTaskTemplateWorkflow(input: { template_id: string; confirm_run?: boolean; selected_agent_ids?: string[]; owner_agent_id?: string }): Promise<KbBotProjectWorkflowResult & { template?: Record<string, unknown> }> {
  return apiJson<KbBotProjectWorkflowResult & { template?: Record<string, unknown> }>("/workflows/customer-task-templates/run", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function submitCustomerTaskTemplateJob(input: {
  template_id: string;
  adapter?: "mock" | "hermes" | "openclaw";
  confirm_run?: boolean;
  selected_agent_ids?: string[];
  owner_agent_id?: string;
  worker_agent_id?: string;
  title?: string;
  description?: string;
  acceptance_criteria?: string;
  priority?: string;
  risk_level?: string;
}): Promise<WorkflowJobSubmitPayload> {
  return apiJsonWithStatuses<WorkflowJobSubmitPayload>("/workflows/customer-task-templates/submit", {
    method: "POST",
    body: JSON.stringify(input),
  }, [409]);
}

export async function loadWorkflowJobs(limit = 8): Promise<WorkflowJobListPayload> {
  return apiJson<WorkflowJobListPayload>(`/workflows/jobs?limit=${encodeURIComponent(String(limit))}`);
}

export async function loadStuckWorkflowJobs(thresholdSec = 900, limit = 25): Promise<WorkflowJobStuckPayload> {
  return apiJson<WorkflowJobStuckPayload>(`/workflows/jobs/stuck?threshold_sec=${encodeURIComponent(String(thresholdSec))}&limit=${encodeURIComponent(String(limit))}`);
}

export async function loadWorkflowJob(jobId: string): Promise<{ job: WorkflowJob; token_omitted?: boolean }> {
  return apiJson<{ job: WorkflowJob; token_omitted?: boolean }>(`/workflows/jobs/${encodeURIComponent(jobId)}`);
}

export async function markWorkflowJobFailed(jobId: string, reason: string): Promise<WorkflowJobMarkFailedPayload> {
  return apiJson<WorkflowJobMarkFailedPayload>(`/workflows/jobs/${encodeURIComponent(jobId)}/mark-failed`, {
    method: "POST",
    body: JSON.stringify({ reason, actor_id: "usr_operator" }),
  });
}

export async function persistCustomerProjectReportArtifact(projectId: string): Promise<CustomerProjectReportArtifactResult> {
  return apiJson<CustomerProjectReportArtifactResult>(`/workflows/customer-projects/${encodeURIComponent(projectId)}/report-artifact`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function loadCustomerProjectReport(projectId: string): Promise<CustomerProjectReportPayload> {
  return apiJson<CustomerProjectReportPayload>(`/workflows/customer-projects/${encodeURIComponent(projectId)}/report`);
}

export async function loadCustomerProjects(limit = 25): Promise<CustomerProjectIndexPayload> {
  return apiJson<CustomerProjectIndexPayload>(`/workflows/customer-projects?limit=${encodeURIComponent(String(limit))}`);
}

export async function loadCustomerDeliveryBoard(limit = 12): Promise<CustomerDeliveryBoardPayload> {
  return apiJson<CustomerDeliveryBoardPayload>(`/workflows/customer-delivery-board?limit=${encodeURIComponent(String(limit))}`);
}

export async function loadWorkerStatus(): Promise<WorkerStatusPayload> {
  const raw = await apiJson<Record<string, unknown>>("/workers/status");
  const remoteHealthRaw = typeof raw.remote_worker_health === "object" && raw.remote_worker_health !== null ? raw.remote_worker_health as Record<string, unknown> : {};
  const fleetHealthRaw = typeof raw.fleet_health === "object" && raw.fleet_health !== null ? raw.fleet_health as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-worker"),
    status: String(raw.status || "unknown"),
    worker_count: numberValue(raw.worker_count, 0),
    running_workers: numberValue(raw.running_workers, 0),
    recent_completed_runs: numberValue(raw.recent_completed_runs, 0),
    pending_worker_tasks: numberValue(raw.pending_worker_tasks, 0),
    stuck_worker_tasks: numberValue(raw.stuck_worker_tasks, 0),
    stuck_workflow_jobs: numberValue(raw.stuck_workflow_jobs, 0),
    remote_worker_count: numberValue(raw.remote_worker_count, 0),
    total_remote_enrollments: numberValue(raw.total_remote_enrollments, 0),
    active_remote_enrollments: numberValue(raw.active_remote_enrollments, 0),
    fresh_remote_enrollments: numberValue(raw.fresh_remote_enrollments, 0),
    stale_remote_enrollments: numberValue(raw.stale_remote_enrollments, 0),
    never_seen_remote_enrollments: numberValue(raw.never_seen_remote_enrollments, 0),
    active_remote_sessions: numberValue(raw.active_remote_sessions, 0),
    remote_worker_health: normalizeWorkerRemoteHealth(remoteHealthRaw),
    adapter_readiness: typeof raw.adapter_readiness === "object" && raw.adapter_readiness !== null ? raw.adapter_readiness as WorkerAdapterReadinessSummary : undefined,
    fleet_health: normalizeWorkerFleetHealth(fleetHealthRaw),
    daemons: asArray<Record<string, unknown>>(raw.daemons).map(normalizeWorkerDaemon),
    workers: asArray<Record<string, unknown>>(raw.workers).map((row) => normalizeAgent(row)),
    recent_runs: asArray<Record<string, unknown>>(raw.recent_runs).map(normalizeRun),
    recent_tasks: asArray<Record<string, unknown>>(raw.recent_tasks).map(normalizeTask),
    stuck_tasks: asArray<Record<string, unknown>>(raw.stuck_tasks).map((row) => ({
      ...normalizeTask(row),
      age_sec: numberValue(row.age_sec, 0),
      threshold_sec: numberValue(row.threshold_sec, 0),
      running_run_id: row.running_run_id ? String(row.running_run_id) : null,
      running_run_started_at: row.running_run_started_at ? String(row.running_run_started_at) : null,
      stuck_reason: row.stuck_reason ? String(row.stuck_reason) : undefined,
    })),
    stuck_workflow_job_refs: asArray<Record<string, unknown>>(raw.stuck_workflow_job_refs).map((row) => ({
      job_id: String(row.job_id || ""),
      workflow_type: row.workflow_type ? String(row.workflow_type) : undefined,
      status: row.status ? String(row.status) : undefined,
      age_sec: numberValue(row.age_sec, 0),
      stuck_reason: row.stuck_reason ? String(row.stuck_reason) : undefined,
    })).filter((row) => row.job_id),
    recent_events: asArray<Record<string, unknown>>(raw.recent_events),
  };
}

export async function loadWorkerFleet(): Promise<WorkerFleetPayload> {
  const raw = await optionalApiJson<Record<string, unknown>>("/workers/fleet", {
    provider: "agentops-worker",
    operation: "fleet_view",
    status: "unavailable",
    summary: {},
    lanes: [],
    next_actions: [],
    safety: {
      read_only: true,
      live_execution_performed: false,
      token_omitted: true,
      session_id_omitted: true,
      raw_prompt_omitted: true,
    },
    token_omitted: true,
    live_execution_performed: false,
    fallback_reason: "endpoint_not_available",
  });
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-worker"),
    operation: String(raw.operation || "fleet_view"),
    status: String(raw.status || "unknown"),
    summary: {
      lane_count: numberValue(summaryRaw.lane_count, 0),
      lane_counts: numberRecord(summaryRaw.lane_counts),
      health_counts: numberRecord(summaryRaw.health_counts),
      local_daemon_count: numberValue(summaryRaw.local_daemon_count, 0),
      running_local_daemons: numberValue(summaryRaw.running_local_daemons, 0),
      remote_worker_count: numberValue(summaryRaw.remote_worker_count, 0),
      fresh_remote_enrollments: numberValue(summaryRaw.fresh_remote_enrollments, 0),
      stale_remote_enrollments: numberValue(summaryRaw.stale_remote_enrollments, 0),
      never_seen_remote_enrollments: numberValue(summaryRaw.never_seen_remote_enrollments, 0),
      active_remote_sessions: numberValue(summaryRaw.active_remote_sessions, 0),
      stuck_worker_tasks: numberValue(summaryRaw.stuck_worker_tasks, 0),
      stuck_workflow_jobs: numberValue(summaryRaw.stuck_workflow_jobs, 0),
      recommended_adapter: summaryRaw.recommended_adapter ? String(summaryRaw.recommended_adapter) : undefined,
    },
    lanes: asArray<Record<string, unknown>>(raw.lanes).map((lane) => ({
      lane_id: String(lane.lane_id || ""),
      lane_type: String(lane.lane_type || "unknown"),
      adapter: lane.adapter ? String(lane.adapter) : null,
      agent_id: lane.agent_id ? String(lane.agent_id) : null,
      agent_name: lane.agent_name ? String(lane.agent_name) : null,
      workspace_id: lane.workspace_id ? String(lane.workspace_id) : null,
      runtime_type: lane.runtime_type ? String(lane.runtime_type) : null,
      status: String(lane.status || "unknown"),
      health: String(lane.health || "info"),
      heartbeat_state: lane.heartbeat_state ? String(lane.heartbeat_state) : null,
      session_state: lane.session_state ? String(lane.session_state) : null,
      active_session_count: numberValue(lane.active_session_count, 0),
      last_seen_at: lane.last_seen_at ? String(lane.last_seen_at) : null,
      expires_at: lane.expires_at ? String(lane.expires_at) : null,
      scope_count: numberValue(lane.scope_count, 0),
      workload: typeof lane.workload === "object" && lane.workload !== null ? lane.workload as Record<string, unknown> : undefined,
      next_action: lane.next_action ? String(lane.next_action) : undefined,
      safe_ref: lane.safe_ref ? String(lane.safe_ref) : null,
      token_omitted: boolValue(lane.token_omitted),
      session_id_omitted: boolValue(lane.session_id_omitted),
      token_id_omitted: boolValue(lane.token_id_omitted),
    })).filter((lane) => lane.lane_id),
    next_actions: asArray<unknown>(raw.next_actions).map(String).filter(Boolean),
    contract: raw.contract ? String(raw.contract) : undefined,
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
      session_id_omitted: boolValue(safetyRaw.session_id_omitted),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function loadLocalReadiness(): Promise<LocalReadinessPayload> {
  const raw = await optionalApiJson<Record<string, unknown>>("/local/readiness", {
    provider: "agentops-local",
    operation: "local_readiness",
    status: "unavailable",
    ok: false,
    gates: [],
    evidence: {},
    next_actions: [],
    adapter_readiness: {},
    token_omitted: true,
    live_execution_performed: false,
    fallback_reason: "endpoint_not_available",
  });
  const evidenceRaw = typeof raw.evidence === "object" && raw.evidence !== null ? raw.evidence as Record<string, unknown> : {};
  const adapterReadiness = typeof raw.adapter_readiness === "object" && raw.adapter_readiness !== null ? raw.adapter_readiness as WorkerAdapterReadinessSummary : {};
  return {
    provider: String(raw.provider || "agentops-local"),
    operation: String(raw.operation || "local_readiness"),
    status: String(raw.status || "unknown"),
    ok: boolValue(raw.ok),
    workspace_id: raw.workspace_id ? String(raw.workspace_id) : undefined,
    gates: asArray<Record<string, unknown>>(raw.gates).map((gate) => ({
      id: String(gate.id || ""),
      label: String(gate.label || gate.id || ""),
      ok: boolValue(gate.ok),
      status: String(gate.status || "unknown"),
      detail: String(gate.detail || ""),
      next_action: String(gate.next_action || ""),
    })).filter((gate) => gate.id || gate.label),
    evidence: {
      tasks: numberValue(evidenceRaw.tasks, 0),
      planned_tasks: numberValue(evidenceRaw.planned_tasks, 0),
      completed_tasks: numberValue(evidenceRaw.completed_tasks, 0),
      runs: numberValue(evidenceRaw.runs, 0),
      completed_runs: numberValue(evidenceRaw.completed_runs, 0),
      tool_calls: numberValue(evidenceRaw.tool_calls, 0),
      evaluations: numberValue(evidenceRaw.evaluations, 0),
      audit_logs: numberValue(evidenceRaw.audit_logs, 0),
      artifacts: numberValue(evidenceRaw.artifacts, 0),
      memories: numberValue(evidenceRaw.memories, 0),
      memory_candidates: numberValue(evidenceRaw.memory_candidates, 0),
      approved_memories: numberValue(evidenceRaw.approved_memories, 0),
      pending_approvals: numberValue(evidenceRaw.pending_approvals, 0),
      approvals: numberValue(evidenceRaw.approvals, 0),
      workflow_jobs: numberValue(evidenceRaw.workflow_jobs, 0),
      customer_worker_artifacts: numberValue(evidenceRaw.customer_worker_artifacts, 0),
      closed_loop_runs: numberValue(evidenceRaw.closed_loop_runs, 0),
      has_task_run_tool_eval_audit_artifact_chain: boolValue(evidenceRaw.has_task_run_tool_eval_audit_artifact_chain),
      has_memory_or_knowledge: boolValue(evidenceRaw.has_memory_or_knowledge),
      has_approval_flow: boolValue(evidenceRaw.has_approval_flow),
    },
    adapter_readiness: adapterReadiness,
    next_actions: asArray(raw.next_actions).map(String),
    contract: raw.contract ? String(raw.contract) : undefined,
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function loadIntegrationInbox(options: IntegrationInboxOptions = {}): Promise<IntegrationInboxPayload> {
  const params = new URLSearchParams();
  if (options.bucket && options.bucket !== "all") params.set("bucket", options.bucket);
  if (options.limit) params.set("limit", String(options.limit));
  if (options.threshold_sec) params.set("threshold_sec", String(options.threshold_sec));
  const path = params.toString() ? `/commander/integration-inbox?${params.toString()}` : "/commander/integration-inbox";
  const raw = await optionalApiJson<Record<string, unknown>>(path, {
    provider: "agentops-commander",
    operation: "integration_inbox",
    status: "unavailable",
    filter: { bucket: options.bucket || "all", limit: options.limit || 20, threshold_sec: options.threshold_sec || 900 },
    token_omitted: true,
    live_execution_performed: false,
    summary: {},
    inbox_items: [],
    recommended_next_actions: [],
    safety: {
      read_only: true,
      ledger_mutated: false,
      raw_prompt_omitted: true,
    },
    fallback_reason: "endpoint_not_available",
  });
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const bucketRaw = typeof summaryRaw.buckets === "object" && summaryRaw.buckets !== null ? summaryRaw.buckets as Record<string, unknown> : summaryRaw;
  const filterRaw = typeof raw.filter === "object" && raw.filter !== null ? raw.filter as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-commander"),
    operation: String(raw.operation || "integration_inbox"),
    status: String(raw.status || "unknown"),
    filter: {
      bucket: String(filterRaw.bucket || options.bucket || "all"),
      limit: numberValue(filterRaw.limit, options.limit || 20),
      threshold_sec: numberValue(filterRaw.threshold_sec, options.threshold_sec || 900),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
    summary: {
      ready_for_review: numberValue(bucketRaw.ready_for_review, 0),
      still_running: numberValue(bucketRaw.still_running, 0),
      blocked: numberValue(bucketRaw.blocked, 0),
      late_or_stale: numberValue(bucketRaw.late_or_stale, 0),
      needs_memory_review: numberValue(bucketRaw.needs_memory_review, 0),
      total: numberValue(summaryRaw.total, Object.values(bucketRaw).reduce((sum, value) => sum + numberValue(value, 0), 0)),
    },
    inbox_items: asArray<Record<string, unknown>>(raw.inbox_items).map((item) => ({
      item_id: String(item.item_id || item.job_id || item.run_id || item.task_id || ""),
      bucket: String(item.bucket || "unknown"),
      title: String(item.title || item.item_id || "Untitled inbox item"),
      status: String(item.status || "unknown"),
      task_id: item.task_id ? String(item.task_id) : null,
      run_id: item.run_id ? String(item.run_id) : null,
      job_id: item.job_id ? String(item.job_id) : null,
      artifact_id: item.artifact_id ? String(item.artifact_id) : null,
      agent_id: item.agent_id ? String(item.agent_id) : null,
      owner_agent_id: item.owner_agent_id ? String(item.owner_agent_id) : null,
      age_sec: numberValue(item.age_sec, 0),
      evidence: typeof item.evidence === "object" && item.evidence !== null
        ? item.evidence as Record<string, unknown>
        : typeof item.evidence_counts === "object" && item.evidence_counts !== null
          ? item.evidence_counts as Record<string, unknown>
          : undefined,
      recommended_action: item.recommended_action ? String(item.recommended_action) : undefined,
      created_at: item.created_at ? String(item.created_at) : undefined,
      updated_at: item.updated_at ? String(item.updated_at) : undefined,
    })).filter((item) => item.item_id || item.title),
    recommended_next_actions: asArray<unknown>(raw.recommended_next_actions).map((item) => String(item)).filter(Boolean),
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
    },
  };
}

export async function loadReviewQueue(limit = 12): Promise<ReviewQueuePayload> {
  const raw = await optionalApiJson<Record<string, unknown>>(`/review/queue?limit=${encodeURIComponent(String(limit))}`, {
    provider: "agentops-review",
    operation: "human_review_queue",
    status: "unavailable",
    limit,
    summary: {},
    review_items: [],
    gates: [],
    next_actions: [],
    safety: {
      read_only: true,
      ledger_mutated: false,
      live_execution_performed: false,
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      token_omitted: true,
    },
    token_omitted: true,
    fallback_reason: "endpoint_not_available",
  });
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-review"),
    operation: String(raw.operation || "human_review_queue"),
    status: String(raw.status || "unknown"),
    limit: numberValue(raw.limit, limit),
    summary: {
      pending_approvals: numberValue(summaryRaw.pending_approvals, 0),
      memory_candidates: numberValue(summaryRaw.memory_candidates, 0),
      ready_deliveries: numberValue(summaryRaw.ready_deliveries, 0),
      waiting_deliveries: numberValue(summaryRaw.waiting_deliveries, 0),
      needs_attention_deliveries: numberValue(summaryRaw.needs_attention_deliveries, 0),
      review_items_total: numberValue(summaryRaw.review_items_total, 0),
      returned_items: numberValue(summaryRaw.returned_items, 0),
      retrieved_pending_approvals: numberValue(summaryRaw.retrieved_pending_approvals, 0),
      retrieved_memory_candidates: numberValue(summaryRaw.retrieved_memory_candidates, 0),
    },
    review_items: asArray<Record<string, unknown>>(raw.review_items).map((item) => ({
      item_type: String(item.item_type || "review_item"),
      item_id: String(item.item_id || item.approval_id || item.memory_id || item.artifact_id || ""),
      status: String(item.status || "unknown"),
      kind: item.kind ? String(item.kind) : null,
      title: String(item.title || item.item_id || "Review item"),
      summary: item.summary ? String(item.summary) : undefined,
      task_id: item.task_id ? String(item.task_id) : null,
      run_id: item.run_id ? String(item.run_id) : null,
      agent_id: item.agent_id ? String(item.agent_id) : null,
      artifact_id: item.artifact_id ? String(item.artifact_id) : null,
      created_at: item.created_at ? String(item.created_at) : undefined,
      updated_at: item.updated_at ? String(item.updated_at) : undefined,
      next_action: item.next_action ? String(item.next_action) : undefined,
      cli_action: item.cli_action ? String(item.cli_action) : undefined,
      alternate_cli_action: item.alternate_cli_action ? String(item.alternate_cli_action) : null,
      links: typeof item.links === "object" && item.links !== null ? item.links as Record<string, string | null> : undefined,
    })).filter((item) => item.item_id || item.title),
    gates: asArray<Record<string, unknown>>(raw.gates).map((gate) => ({
      id: String(gate.id || gate.label || ""),
      label: String(gate.label || gate.id || ""),
      ok: boolValue(gate.ok),
      value: typeof gate.value === "string" || typeof gate.value === "number" || typeof gate.value === "boolean" ? gate.value : undefined,
    })),
    next_actions: asArray<unknown>(raw.next_actions).map(String).filter(Boolean),
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
      raw_response_omitted: boolValue(safetyRaw.raw_response_omitted),
      token_omitted: boolValue(safetyRaw.token_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
  };
}

export async function loadWorkerAdapterReadiness(): Promise<WorkerAdapterReadinessPayload> {
  const raw = await apiJson<Record<string, unknown>>("/workers/adapter-readiness");
  const adaptersRaw = typeof raw.adapters === "object" && raw.adapters !== null ? raw.adapters as Record<string, unknown> : {};
  const normalizeAdapter = (name: WorkerAdapterName): WorkerAdapterReadinessItem => {
    const item = typeof adaptersRaw[name] === "object" && adaptersRaw[name] !== null ? adaptersRaw[name] as Record<string, unknown> : {};
    return {
      adapter: name,
      ok: boolValue(item.ok),
      readiness: String(item.readiness || "unavailable"),
      connector_id: item.connector_id ? String(item.connector_id) : null,
      trust_status: item.trust_status ? String(item.trust_status) : undefined,
      requires_confirm_run: boolValue(item.requires_confirm_run),
      target_resource: item.target_resource ? String(item.target_resource) : null,
      checks: typeof item.checks === "object" && item.checks !== null ? item.checks as Record<string, unknown> : {},
      recommended_action: item.recommended_action ? String(item.recommended_action) : undefined,
      last_error: item.last_error ? String(item.last_error) : null,
      token_omitted: boolValue(item.token_omitted),
    };
  };
  return {
    provider: String(raw.provider || "agentops-worker"),
    status: String(raw.status || "unknown"),
    summary: typeof raw.summary === "object" && raw.summary !== null ? raw.summary as WorkerAdapterReadinessSummary : {},
    adapters: {
      mock: normalizeAdapter("mock"),
      hermes: normalizeAdapter("hermes"),
      openclaw: normalizeAdapter("openclaw"),
    },
    contract: raw.contract ? String(raw.contract) : undefined,
    live_execution_performed: boolValue(raw.live_execution_performed),
    token_omitted: boolValue(raw.token_omitted),
  };
}

export async function dispatchLocalWorkerOnce(input: {
  adapter: "mock" | "hermes" | "openclaw";
  confirm_run?: boolean;
  title?: string;
  description?: string;
  acceptance_criteria?: string;
}): Promise<WorkerDispatchResult> {
  return apiJson<WorkerDispatchResult>("/workers/local/dispatch-once", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

function normalizeWorkerDaemon(row: Record<string, unknown>): WorkerDaemonStatus {
  return {
    adapter: String(row.adapter || "mock") as WorkerDaemonStatus["adapter"],
    status: String(row.status || "not_started"),
    running: boolValue(row.running),
    pid: row.pid ? numberValue(row.pid, 0) : null,
    agent_id: row.agent_id ? String(row.agent_id) : null,
    started_at: row.started_at ? String(row.started_at) : null,
    stopped_at: row.stopped_at ? String(row.stopped_at) : null,
    poll_interval: row.poll_interval ? numberValue(row.poll_interval, 0) : null,
    max_tasks: row.max_tasks === undefined || row.max_tasks === null ? null : numberValue(row.max_tasks, 0),
    confirm_run: boolValue(row.confirm_run),
    log_path: row.log_path ? String(row.log_path) : undefined,
    state_path: row.state_path ? String(row.state_path) : undefined,
    worker_status: row.worker_status ? String(row.worker_status) : null,
    state_updated_at: row.state_updated_at ? String(row.state_updated_at) : null,
    processed: numberValue(row.processed, 0),
    iterations: numberValue(row.iterations, 0),
    total_errors: numberValue(row.total_errors, 0),
    consecutive_errors: numberValue(row.consecutive_errors, 0),
    last_sleep_reason: row.last_sleep_reason ? String(row.last_sleep_reason) : null,
    last_sleep_sec: row.last_sleep_sec === undefined || row.last_sleep_sec === null ? null : numberValue(row.last_sleep_sec, 0),
    continue_on_error: boolValue(row.continue_on_error),
    last_error: (row.last_error || null) as Record<string, unknown> | null,
    last_result: (row.last_result || null) as Record<string, unknown> | null,
    log_tail: asArray(row.log_tail).map(String),
  };
}

function numberRecord(value: unknown): Record<string, number> {
  const source = typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
  return Object.fromEntries(Object.entries(source).map(([key, count]) => [key, numberValue(count, 0)]));
}

function normalizeWorkerRemoteHealth(row: Record<string, unknown>): WorkerRemoteHealth {
  return {
    status: row.status ? String(row.status) : undefined,
    remote_worker_count: numberValue(row.remote_worker_count, 0),
    total_remote_enrollments: numberValue(row.total_remote_enrollments, 0),
    active_enrollments: numberValue(row.active_enrollments, 0),
    fresh_enrollments: numberValue(row.fresh_enrollments, 0),
    stale_enrollments: numberValue(row.stale_enrollments, 0),
    never_seen_enrollments: numberValue(row.never_seen_enrollments, 0),
    active_sessions: numberValue(row.active_sessions, 0),
    expired_sessions: numberValue(row.expired_sessions, 0),
    revoked_sessions: numberValue(row.revoked_sessions, 0),
    heartbeat_state_counts: numberRecord(row.heartbeat_state_counts),
    token_status_counts: numberRecord(row.token_status_counts),
    session_state_counts: numberRecord(row.session_state_counts),
    remote_workers: asArray<Record<string, unknown>>(row.remote_workers).map((item) => ({
      token_ref: item.token_ref ? String(item.token_ref) : undefined,
      token_id_omitted: boolValue(item.token_id_omitted),
      workspace_id: item.workspace_id ? String(item.workspace_id) : undefined,
      agent_id: item.agent_id ? String(item.agent_id) : undefined,
      agent_name: item.agent_name ? String(item.agent_name) : undefined,
      runtime_type: item.runtime_type ? String(item.runtime_type) : undefined,
      agent_status: item.agent_status ? String(item.agent_status) : null,
      token_status: item.token_status ? String(item.token_status) : undefined,
      heartbeat_state: item.heartbeat_state ? String(item.heartbeat_state) : undefined,
      heartbeat_timeout_sec: numberValue(item.heartbeat_timeout_sec, 0),
      last_heartbeat_at: item.last_heartbeat_at ? String(item.last_heartbeat_at) : null,
      last_used_at: item.last_used_at ? String(item.last_used_at) : null,
      expires_at: item.expires_at ? String(item.expires_at) : null,
      scope_count: numberValue(item.scope_count, 0),
      active_session_count: numberValue(item.active_session_count, 0),
    })),
    recent_sessions: asArray<Record<string, unknown>>(row.recent_sessions).map((item) => ({
      session_ref: item.session_ref ? String(item.session_ref) : undefined,
      session_id_omitted: boolValue(item.session_id_omitted),
      parent_token_ref: item.parent_token_ref ? String(item.parent_token_ref) : undefined,
      workspace_id: item.workspace_id ? String(item.workspace_id) : undefined,
      agent_id: item.agent_id ? String(item.agent_id) : undefined,
      status: item.status ? String(item.status) : undefined,
      session_state: item.session_state ? String(item.session_state) : undefined,
      created_at: item.created_at ? String(item.created_at) : undefined,
      expires_at: item.expires_at ? String(item.expires_at) : undefined,
      last_used_at: item.last_used_at ? String(item.last_used_at) : null,
      scope_count: numberValue(item.scope_count, 0),
    })),
    token_omitted: boolValue(row.token_omitted),
  };
}

function normalizeWorkerFleetHealth(row: Record<string, unknown>): WorkerFleetHealth | undefined {
  if (Object.keys(row).length === 0) return undefined;
  return {
    overall: String(row.overall || "attention"),
    contract: row.contract ? String(row.contract) : undefined,
    gates: asArray<Record<string, unknown>>(row.gates).map((gate) => ({
      id: String(gate.id || ""),
      status: String(gate.status || "info"),
      summary: String(gate.summary || ""),
      action: gate.action ? String(gate.action) : undefined,
    })).filter((gate) => gate.id || gate.summary),
    recommended_actions: asArray(row.recommended_actions).map(String),
    remote_status: row.remote_status ? String(row.remote_status) : undefined,
    token_omitted: boolValue(row.token_omitted),
  };
}

function normalizeAgentGatewayEnrollment(row: Record<string, unknown>): AgentGatewayEnrollment {
  return {
    token_id: String(row.token_id || ""),
    workspace_id: String(row.workspace_id || ""),
    agent_id: String(row.agent_id || ""),
    scopes: parseJsonArray(row.scopes),
    status: String(row.status || "unknown"),
    label: String(row.label || ""),
    heartbeat_timeout_sec: numberValue(row.heartbeat_timeout_sec, 0),
    created_at: String(row.created_at || ""),
    expires_at: String(row.expires_at || ""),
    revoked_at: row.revoked_at ? String(row.revoked_at) : null,
    last_used_at: row.last_used_at ? String(row.last_used_at) : null,
    last_heartbeat_at: row.last_heartbeat_at ? String(row.last_heartbeat_at) : null,
    heartbeat_state: String(row.heartbeat_state || "never_seen"),
  };
}

function normalizeAgentGatewaySession(row: Record<string, unknown>): AgentGatewaySession {
  return {
    session_id: String(row.session_id || ""),
    parent_token_id: row.parent_token_id ? String(row.parent_token_id) : null,
    workspace_id: String(row.workspace_id || ""),
    agent_id: String(row.agent_id || ""),
    scopes: parseJsonArray(row.scopes),
    status: String(row.status || "unknown"),
    session_state: String(row.session_state || row.status || "unknown"),
    created_at: String(row.created_at || ""),
    expires_at: String(row.expires_at || ""),
    revoked_at: row.revoked_at ? String(row.revoked_at) : null,
    last_used_at: row.last_used_at ? String(row.last_used_at) : null,
  };
}

function normalizeAgentGatewayStatus(row: Record<string, unknown>): AgentGatewayStatusPayload {
  const auth = (row.auth || {}) as Record<string, unknown>;
  return {
    provider: String(row.provider || "agent_gateway"),
    status: String(row.status || "unknown"),
    auth: {
      mode: String(auth.mode || "unknown"),
      authenticated: boolValue(auth.authenticated),
      agent_id: String(auth.agent_id || ""),
      workspace_id: String(auth.workspace_id || ""),
      scopes: parseJsonArray(auth.scopes),
      token_id: auth.token_id ? String(auth.token_id) : undefined,
      token_status: auth.token_status ? String(auth.token_status) : undefined,
      heartbeat_state: auth.heartbeat_state ? String(auth.heartbeat_state) : undefined,
      heartbeat_timeout_sec: auth.heartbeat_timeout_sec === undefined ? undefined : numberValue(auth.heartbeat_timeout_sec, 0),
      expires_at: auth.expires_at ? String(auth.expires_at) : undefined,
      last_used_at: auth.last_used_at ? String(auth.last_used_at) : null,
      last_heartbeat_at: auth.last_heartbeat_at ? String(auth.last_heartbeat_at) : null,
      session_id: auth.session_id ? String(auth.session_id) : undefined,
      parent_token_id: auth.parent_token_id ? String(auth.parent_token_id) : undefined,
      session_expires_at: auth.session_expires_at ? String(auth.session_expires_at) : undefined,
    },
    valid_scopes: asArray(row.valid_scopes).map(String),
    token_omitted: boolValue(row.token_omitted),
  };
}

export async function startLocalWorkerDaemon(input: {
  adapter: "mock" | "hermes" | "openclaw";
  confirm_run?: boolean;
  poll_interval?: number;
  max_tasks?: number;
}): Promise<WorkerDaemonResult> {
  return apiJson<WorkerDaemonResult>("/workers/local/start", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function stopLocalWorkerDaemon(adapter?: "mock" | "hermes" | "openclaw" | "all"): Promise<WorkerDaemonResult> {
  return apiJson<WorkerDaemonResult>("/workers/local/stop", {
    method: "POST",
    body: JSON.stringify({ adapter: adapter || "all" }),
  });
}

export async function loadWorkerDaemonLogs(adapter: "mock" | "hermes" | "openclaw"): Promise<WorkerDaemonLogPayload> {
  const raw = await apiJson<Record<string, unknown>>(`/workers/local/logs?adapter=${encodeURIComponent(adapter)}`);
  return {
    provider: String(raw.provider || "agentops-worker"),
    daemon: normalizeWorkerDaemon((raw.daemon || {}) as Record<string, unknown>),
  };
}

export async function releaseWorkerTask(input: { task_id: string; reason?: string; force?: boolean }): Promise<WorkerTaskReleaseResult> {
  const raw = await apiJson<Record<string, unknown>>("/workers/tasks/release", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return {
    released: boolValue(raw.released),
    task: normalizeTask((raw.task || {}) as Record<string, unknown>),
    released_runs: asArray(raw.released_runs).map(String),
    token_omitted: boolValue(raw.token_omitted),
    error: raw.error ? String(raw.error) : undefined,
  };
}

export async function loadAgentGatewayEnrollments(): Promise<AgentGatewayEnrollmentListPayload> {
  const raw = await apiJson<Record<string, unknown>>("/agent-gateway/enrollments");
  return {
    enrollments: asArray<Record<string, unknown>>(raw.enrollments).map(normalizeAgentGatewayEnrollment),
    valid_scopes: asArray(raw.valid_scopes).map(String),
  };
}

export async function loadAgentGatewaySessions(): Promise<AgentGatewaySessionListPayload> {
  const raw = await apiJson<Record<string, unknown>>("/agent-gateway/sessions");
  return {
    sessions: asArray<Record<string, unknown>>(raw.sessions).map(normalizeAgentGatewaySession),
    valid_scopes: asArray(raw.valid_scopes).map(String),
    token_omitted: boolValue(raw.token_omitted),
  };
}

export async function loadAgentGatewayStatus(): Promise<AgentGatewayStatusPayload> {
  const raw = await apiJson<Record<string, unknown>>("/agent-gateway/status");
  return normalizeAgentGatewayStatus(raw);
}

export async function loadSecurityProductionReadiness(): Promise<SecurityProductionReadinessPayload> {
  const raw = await optionalApiJson<Record<string, unknown>>("/security/production-readiness", {
    provider: "agentops-security",
    operation: "production_readiness",
    status: "unavailable",
    production_ready: false,
    production_requested: false,
    auth_mode: "unknown",
    gateway_status_code: 0,
    gates: [],
    next_actions: ["agentops security production-readiness"],
    safety: {
      read_only: true,
      live_execution_performed: false,
      token_omitted: true,
      raw_prompt_omitted: true,
    },
    token_omitted: true,
    live_execution_performed: false,
  });
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-security"),
    operation: String(raw.operation || "production_readiness"),
    status: String(raw.status || "unknown"),
    production_ready: boolValue(raw.production_ready),
    production_requested: boolValue(raw.production_requested),
    auth_mode: String(raw.auth_mode || "unknown"),
    gateway_status_code: numberValue(raw.gateway_status_code, 0),
    gates: asArray<Record<string, unknown>>(raw.gates).map((gate) => ({
      id: String(gate.id || ""),
      label: String(gate.label || gate.id || ""),
      status: String(gate.status || "unknown"),
      ok: boolValue(gate.ok),
      detail: String(gate.detail || ""),
      next_action: String(gate.next_action || ""),
    })).filter((gate) => gate.id || gate.label),
    next_actions: asArray<unknown>(raw.next_actions).map(String).filter(Boolean),
    contract: raw.contract ? String(raw.contract) : undefined,
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function loadDemoReadiness(): Promise<DemoReadinessPayload> {
  const raw = await optionalApiJson<Record<string, unknown>>("/demo/readiness", {
    provider: "agentops-demo",
    operation: "v1_5_demo_readiness",
    status: "unavailable",
    demo_ready: false,
    production_ready: false,
    summary: {},
    shots: [],
    next_actions: ["agentops demo readiness"],
    safety: {
      read_only: true,
      ledger_mutated: false,
      live_execution_performed: false,
      token_omitted: true,
      raw_prompt_omitted: true,
    },
    token_omitted: true,
    live_execution_performed: false,
  });
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-demo"),
    operation: String(raw.operation || "v1_5_demo_readiness"),
    status: String(raw.status || "unknown"),
    demo_ready: boolValue(raw.demo_ready),
    production_ready: boolValue(raw.production_ready),
    summary: {
      shot_count: numberValue(summaryRaw.shot_count, 0),
      ready_shots: numberValue(summaryRaw.ready_shots, 0),
      blocker_count: numberValue(summaryRaw.blocker_count, 0),
      warning_count: numberValue(summaryRaw.warning_count, 0),
      closed_loop_runs: numberValue(summaryRaw.closed_loop_runs, 0),
      customer_worker_artifacts: numberValue(summaryRaw.customer_worker_artifacts, 0),
      fleet_lanes: numberValue(summaryRaw.fleet_lanes, 0),
      ready_inbox_items: numberValue(summaryRaw.ready_inbox_items, 0),
    },
    shots: asArray<Record<string, unknown>>(raw.shots).map((shot) => ({
      id: String(shot.id || ""),
      label: String(shot.label || shot.id || ""),
      route: shot.route ? String(shot.route) : undefined,
      command: shot.command ? String(shot.command) : undefined,
      status: String(shot.status || "unknown"),
      ok: boolValue(shot.ok),
      detail: String(shot.detail || ""),
      next_action: String(shot.next_action || ""),
    })).filter((shot) => shot.id || shot.label),
    next_actions: asArray<unknown>(raw.next_actions).map(String).filter(Boolean),
    references: typeof raw.references === "object" && raw.references !== null ? raw.references as Record<string, string> : undefined,
    contract: raw.contract ? String(raw.contract) : undefined,
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function createAgentGatewayEnrollment(input: AgentGatewayEnrollmentCreateInput): Promise<AgentGatewayEnrollmentCreateResult> {
  return apiJson<AgentGatewayEnrollmentCreateResult>("/agent-gateway/enrollment/create", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function requestAgentGatewayEnrollment(input: AgentGatewayEnrollmentCreateInput & { reason?: string }): Promise<AgentGatewayEnrollmentRequestResult> {
  return apiJson<AgentGatewayEnrollmentRequestResult>("/agent-gateway/enrollment/request", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function issueApprovedAgentGatewayEnrollment(input: {
  request_id?: string;
  approval_id?: string;
  ttl_days?: number;
  heartbeat_timeout_sec?: number;
  label?: string;
}): Promise<AgentGatewayEnrollmentCreateResult & { issued_from_request_id?: string; approval_id?: string }> {
  return apiJson<AgentGatewayEnrollmentCreateResult & { issued_from_request_id?: string; approval_id?: string }>("/agent-gateway/enrollment/issue-approved", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function revokeAgentGatewayEnrollment(input: { token_id?: string; agent_id?: string }): Promise<AgentGatewayEnrollmentRevokeResult> {
  return apiJson<AgentGatewayEnrollmentRevokeResult>("/agent-gateway/enrollment/revoke", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function revokeAgentGatewaySession(input: { session_id?: string; agent_id?: string }): Promise<AgentGatewaySessionRevokeResult> {
  return apiJson<AgentGatewaySessionRevokeResult>("/agent-gateway/session/revoke", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function rotateAgentGatewayEnrollment(input: {
  token_id?: string;
  agent_id?: string;
  scopes?: string[];
  ttl_days?: number;
  heartbeat_timeout_sec?: number;
  label?: string;
}): Promise<AgentGatewayEnrollmentRotateResult> {
  return apiJson<AgentGatewayEnrollmentRotateResult>("/agent-gateway/enrollment/rotate", {
    method: "POST",
    body: JSON.stringify(input),
  });
}
