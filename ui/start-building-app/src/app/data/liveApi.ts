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
  evaluation_case_runs?: EvaluationCaseRun[];
}

export interface TaskDetailPayload {
  task: Task;
  runs: Run[];
  approvals: Approval[];
  evaluations: Evaluation[];
  memories: Memory[];
  artifacts?: { artifact_id: string; title: string; artifact_type: string; summary: string; created_at: string }[];
  evaluation_case_runs?: EvaluationCaseRun[];
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
  approval_id?: string | null;
  plan_id?: string | null;
  plan_evidence_manifest_id?: string | null;
  plan_evidence_status?: string | null;
  plan_evidence_pass?: boolean;
  evaluation_case_result?: Record<string, unknown> | null;
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

export interface HermesOpenClawLoopReadbackPayload {
  provider: string;
  operation: string;
  loop_id?: string | null;
  status: string;
  runs: Record<string, unknown>[];
  tasks: Record<string, unknown>[];
  artifacts: Record<string, unknown>[];
  agent_plans: Record<string, unknown>[];
  plan_evidence_manifests: Record<string, unknown>[];
  audit_logs?: Record<string, unknown>[];
  summary: {
    runs?: number;
    tasks?: number;
    artifacts?: number;
    agent_plans?: number;
    plan_evidence_manifests?: number;
    verified_plan_evidence_manifests?: number;
    blocked_plan_evidence_manifests?: number;
    failed_runs?: number;
  };
  token_omitted?: boolean;
}

export interface HermesOpenClawLoopWorkflowResult {
  provider: string;
  workflow: string;
  ok?: boolean;
  loop_id?: string;
  mode?: string;
  rounds?: number;
  agents?: string[];
  duration_ms?: number;
  log_path?: string;
  audit_path?: string;
  next_action_artifact_path?: string;
  next_action_artifact?: Record<string, unknown>;
  runtime_dir_gitignored?: boolean;
  mis_ledger?: {
    ok?: boolean;
    parent_task_id?: string;
    parent_run_id?: string;
    child_task_ids?: string[];
    child_run_ids?: string[];
    plan_ids?: string[];
    plan_evidence_manifest_ids?: string[];
    verified_plan_evidence_manifest_ids?: string[];
    blocked_plan_evidence_manifest_ids?: string[];
    artifact_id?: string;
    artifact_ids?: string[];
    token_omitted?: boolean;
    raw_omitted?: boolean;
  };
  outputs?: Record<string, unknown>[];
  stderr_summary?: string | null;
  token_omitted?: boolean;
  raw_omitted?: boolean;
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
  observation_level?: string;
  capability_policy_hash?: string | null;
  capability_manifest?: Record<string, unknown>;
  risk_floor?: string;
  commercial_readiness?: string;
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
  commander_synthesis_artifacts: number;
  commander_synthesis_pending_reviews: number;
  commander_synthesis_approved_reviews: number;
  commander_synthesis_promoted_memories: number;
  commander_synthesis_promoted_deliveries: number;
  has_task_run_tool_eval_audit_artifact_chain: boolean;
  has_memory_or_knowledge: boolean;
  has_approval_flow: boolean;
}

export interface CommanderSynthesisLifecyclePayload {
  status: string;
  summary: {
    synthesis_artifacts: number;
    pending_reviews: number;
    approved_reviews: number;
    rejected_reviews: number;
    promoted_memory_candidates: number;
    promoted_delivery_artifacts: number;
  };
  recent: Record<string, unknown>[];
  next_actions: string[];
  safety: {
    read_only: boolean;
    ledger_mutated: boolean;
    live_execution_performed: boolean;
    token_omitted: boolean;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
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
  commander_synthesis_lifecycle?: CommanderSynthesisLifecyclePayload;
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

export interface CommanderWorkPackage {
  plan_id: string;
  project_id: string;
  lane_id: string;
  task_id: string;
  title: string;
  description: string;
  owner_agent_id: string;
  collaborator_agent_ids: string[];
  status: string;
  priority: string;
  risk_level: string;
  acceptance_criteria: string;
  dependencies: string[];
  verification_commands: string[];
  scope: string;
  avoid_scope: string;
}

export interface CommanderWorkPackagePlanPayload {
  provider: string;
  operation: string;
  status: string;
  ok: boolean;
  workspace_id: string;
  project_id: string;
  plan_id: string;
  goal_summary: string;
  confirm_create: boolean;
  created: boolean;
  created_count: number;
  planned_count: number;
  work_packages: CommanderWorkPackage[];
  created_task_ids: string[];
  errors: { lane_id?: string; task_id?: string; error?: string; message?: string }[];
  recommended_next_actions: string[];
  safety: {
    live_execution_performed: boolean;
    token_omitted: boolean;
    raw_prompt_omitted: boolean;
    dry_run: boolean;
    ledger_mutated: boolean;
    task_created: boolean;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
}

export interface CommanderWorkPackageReadbackPayload {
  provider: string;
  operation: string;
  status: string;
  workspace_id: string;
  filter: {
    project_id?: string | null;
    plan_id?: string | null;
    status: string;
    limit: number;
  };
  summary: {
    total: number;
    by_status: Record<string, number>;
    by_project: Record<string, number>;
  };
  work_packages: (CommanderWorkPackage & {
    work_package_id: string;
    package_status: string;
    latest_run?: {
      run_id?: string;
      status?: string;
      agent_id?: string;
      runtime_type?: string;
      created_at?: string;
      ended_at?: string | null;
      error_type?: string | null;
      error_message?: string | null;
    } | null;
    evidence_counts?: Record<string, number>;
    recommended_action?: string;
    created_at?: string;
    updated_at?: string;
  })[];
  recommended_next_actions: string[];
  safety: {
    read_only: boolean;
    ledger_mutated: boolean;
    task_created: boolean;
    run_created: boolean;
    live_execution_performed: boolean;
    token_omitted: boolean;
    raw_prompt_omitted: boolean;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
}

export interface CommanderWorkPackageDispatchPayload {
  provider: string;
  operation: string;
  ok: boolean;
  dry_run: boolean;
  adapter: string;
  task_id: string;
  agent_id?: string | null;
  run_id?: string | null;
  work_package?: CommanderWorkPackageReadbackPayload["work_packages"][number] | null;
  evidence?: Record<string, number>;
  duration_ms?: number | null;
  error?: string | null;
  reason?: string | null;
  requires?: Record<string, boolean>;
  safety: {
    ledger_mutated: boolean;
    run_created: boolean;
    live_execution_performed: boolean;
    token_omitted: boolean;
    raw_prompt_omitted: boolean;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
}

export interface CommanderWorkPackageDispatchBatchPayload {
  provider: string;
  operation: string;
  ok: boolean;
  status?: string;
  adapter: string;
  confirm_run: boolean;
  jobs: WorkflowJob[];
  job_ids: string[];
  task_ids: string[];
  status_urls: string[];
  reason?: string | null;
  filter?: {
    project_id?: string | null;
    plan_id?: string | null;
    status?: string;
    limit?: number;
  };
  safety: {
    ledger_mutated: boolean;
    jobs_created: number;
    live_execution_performed: boolean;
    token_omitted: boolean;
    raw_prompt_omitted: boolean;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
}

export interface CommanderWorkPackageSynthesisPayload {
  provider: string;
  operation: string;
  ok: boolean;
  status: string;
  workspace_id: string;
  project_id?: string;
  plan_id?: string;
  artifact_id?: string | null;
  approval_id?: string | null;
  review_approval?: Record<string, unknown> | null;
  markdown?: string;
  content_hash?: string;
  package_count?: number;
  packages?: CommanderWorkPackageReadbackPayload["work_packages"];
  evidence_totals?: Record<string, number>;
  safety: {
    ledger_mutated: boolean;
    artifact_created: boolean;
    live_execution_performed: boolean;
    token_omitted: boolean;
    raw_prompt_omitted: boolean;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
}

export interface CommanderSynthesisPromotionPayload {
  provider: string;
  operation: string;
  ok: boolean;
  status: string;
  workspace_id: string;
  artifact_id: string;
  approval_id?: string | null;
  approval_decision?: string;
  mode: string;
  memory_id?: string | null;
  delivery_artifact_id?: string | null;
  created?: Record<string, unknown>;
  safety: {
    ledger_mutated: boolean;
    live_execution_performed: boolean;
    token_omitted: boolean;
    raw_prompt_omitted: boolean;
    raw_response_omitted: boolean;
    memory_candidate_created?: boolean;
    customer_delivery_artifact_created?: boolean;
  };
  token_omitted: boolean;
  live_execution_performed: boolean;
}

export interface ExecutionEvidenceGapDecisionPayload {
  provider?: string;
  operation?: string;
  ok?: boolean;
  status: string;
  error?: string;
  message?: string;
  closed?: boolean;
  workspace_id?: string;
  run_id?: string;
  decision?: Record<string, unknown>;
  gap?: Record<string, unknown> | null;
  next_actions?: string[];
  recommended_action?: string;
  safety?: {
    read_only?: boolean;
    ledger_mutated?: boolean;
    live_execution_performed?: boolean;
    raw_note_omitted?: boolean;
    raw_prompt_omitted?: boolean;
    raw_response_omitted?: boolean;
    token_omitted?: boolean;
  };
  token_omitted?: boolean;
  live_execution_performed?: boolean;
}

export interface ReviewQueueSummary {
  pending_approvals: number;
  memory_candidates: number;
  evaluation_case_candidates?: number;
  failed_evaluation_case_runs?: number;
  ready_deliveries: number;
  waiting_deliveries: number;
  needs_attention_deliveries: number;
  commander_synthesis_pending_reviews?: number;
  commander_synthesis_promotion_available?: number;
  commander_synthesis_memory_reviews?: number;
  review_items_total: number;
  returned_items: number;
  retrieved_pending_approvals?: number;
  retrieved_memory_candidates?: number;
  retrieved_evaluation_case_candidates?: number;
  retrieved_failed_evaluation_case_runs?: number;
}

export interface ReviewQueueItem {
  item_type: "approval" | "memory_candidate" | "customer_delivery" | string;
  item_id: string;
  status: string;
  review_status?: string;
  kind?: string | null;
  title: string;
  summary?: string;
  task_id?: string | null;
  run_id?: string | null;
  agent_id?: string | null;
  artifact_id?: string | null;
  created_at?: string;
  updated_at?: string;
  priority?: number;
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

export interface OperatorActionPlanItem {
  action_id: string;
  action_signature?: string | null;
  lane: string;
  severity: string;
  priority: number;
  title: string;
  summary?: string;
  command: string;
  verify_command?: string | null;
  ui_route?: string | null;
  source: string;
  evidence?: Record<string, unknown>;
  base_priority?: number;
  receipt_priority_boost?: number;
  receipt_required?: boolean;
  receipt_status?: string;
  receipt_underlying_status?: string;
  receipt_match?: string;
  receipt_current?: boolean;
  receipt_verified?: boolean;
  receipt_id?: string | null;
  receipt_hash?: string | null;
  receipt_state?: Record<string, unknown>;
}

export interface ExecutionEvidenceGapItem {
  run_id: string;
  task_id?: string | null;
  agent_id?: string | null;
  task_title?: string;
  run_status?: string;
  task_status?: string | null;
  remediation_task_id?: string | null;
  remediation_status?: string | null;
  remediation_synthesis_status?: string | null;
  remediation_synthesis_artifact_id?: string | null;
  remediation_synthesis_approval_id?: string | null;
  gap_decision_status?: string | null;
  gap_decision_type?: string | null;
  gap_decision?: Record<string, unknown> | null;
  gap_types: string[];
  missing_evidence: string[];
  severity: string;
  priority: number;
  command: string;
  next_action?: string;
  ui_route?: string | null;
  token_omitted?: boolean;
}

export interface ExecutionEvidenceGapsPayload {
  provider?: string;
  operation?: string;
  status?: string;
  workspace_id?: string;
  summary?: Record<string, number>;
  gaps: ExecutionEvidenceGapItem[];
  next_actions?: string[];
  safety?: Record<string, unknown>;
  token_omitted?: boolean;
}

export interface TaskIntakeChecklistItem {
  task_id: string;
  title: string;
  status: string;
  priority?: string;
  risk_level?: string;
  assigned_agent_ids: string[];
  plan_id?: string | null;
  plan_status?: string | null;
  plan_verified: boolean;
  plan_verified_at?: string | null;
  referenced_specs: number;
  referenced_memories: number;
  referenced_bases: number;
  gates: { id: string; ok: boolean; status: string; message?: string }[];
  failed_gate_ids: string[];
  severity: string;
  priority_score: number;
  command: string;
  next_action?: string;
  ui_route?: string | null;
  token_omitted?: boolean;
}

export interface TaskIntakeChecklistPayload {
  provider?: string;
  operation?: string;
  status?: string;
  workspace_id?: string;
  summary?: Record<string, number>;
  items: TaskIntakeChecklistItem[];
  next_actions?: string[];
  safety?: Record<string, unknown>;
  token_omitted?: boolean;
}

export interface OperatorActionPlanPayload {
  provider: string;
  operation: string;
  status: string;
  workspace_id: string;
  summary: {
    actions: number;
    blocked: number;
    attention: number;
    ready: number;
    review_items_total: number;
    failed_evaluation_case_runs: number;
    waiting_deliveries: number;
    needs_attention_deliveries: number;
    stuck_worker_tasks: number;
    stuck_workflow_jobs: number;
    recommended_adapter: string;
    remediation_packages: number;
    remediation_ready_for_review: number;
    remediation_pending_reviews: number;
    remediation_promoted_memories: number;
    remediation_promoted_deliveries: number;
    evidence_gap_runs: number;
    missing_plan_runs: number;
    missing_plan_evidence_manifests: number;
    unverified_plan_evidence_manifests: number;
    remediated_evidence_gap_runs: number;
    blocked_evidence_gap_runs: number;
    evidence_synthesis_ready_runs: number;
    evidence_synthesis_pending_runs: number;
    evidence_synthesis_promoted_runs: number;
    evidence_gap_closure_ready_runs: number;
    closed_evidence_gap_runs: number;
    waived_evidence_gap_runs: number;
    task_intake_checked: number;
    task_intake_ready: number;
    task_intake_blocked: number;
    task_intake_attention: number;
    task_intake_missing_agent_plan: number;
    dispatch_evidence_proofs: number;
    dispatch_evidence_ready: number;
    dispatch_evidence_waiting_approval: number;
    dispatch_evidence_verified_manifests: number;
    action_receipts: number;
    action_receipts_recorded: number;
    action_receipts_verified: number;
    action_receipts_failed: number;
    receipt_required_actions: number;
    receipt_verified_actions: number;
    receipt_missing_verified_actions: number;
    receipt_stale_actions: number;
  };
  actions: OperatorActionPlanItem[];
  top_commands: string[];
  source_status: Record<string, string | undefined>;
  execution_evidence?: ExecutionEvidenceGapsPayload;
  task_intake?: TaskIntakeChecklistPayload;
  dispatch_evidence?: Record<string, unknown>;
  action_receipts?: OperatorActionReceiptsPayload;
  safety: {
    read_only: boolean;
    ledger_mutated: boolean;
    live_execution_performed: boolean;
    raw_prompt_omitted: boolean;
    raw_response_omitted: boolean;
    token_omitted: boolean;
  };
  token_omitted?: boolean;
  live_execution_performed?: boolean;
}

export interface OperatorActionReceipt {
  receipt_id: string;
  audit_id?: string;
  actor_id?: string;
  workspace_id: string;
  status: string;
  source: string;
  action_id?: string | null;
  action_signature?: string | null;
  action_command?: string | null;
  action_hash?: string | null;
  verify_command?: string | null;
  verify_hash?: string | null;
  result_summary?: string | null;
  created_at?: string;
  tamper_chain_hash?: string;
  token_omitted?: boolean;
}

export interface OperatorActionReceiptsPayload {
  provider: string;
  operation: string;
  status: string;
  workspace_id: string;
  summary: {
    receipts: number;
    recorded: number;
    verified: number;
    failed: number;
    skipped: number;
  };
  receipts: OperatorActionReceipt[];
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

export interface OperatorActionReceiptResult {
  provider?: string;
  operation?: string;
  status: string;
  workspace_id?: string;
  receipt?: OperatorActionReceipt;
  next_actions?: string[];
  safety?: {
    read_only: boolean;
    ledger_mutated: boolean;
    live_execution_performed: boolean;
    raw_prompt_omitted: boolean;
    raw_response_omitted: boolean;
    token_omitted: boolean;
  };
  token_omitted?: boolean;
}

export interface OperatorLoopAuditStep {
  id: string;
  label: string;
  status: string;
  message?: string;
  evidence: Record<string, unknown>;
  command: string;
  source: string;
  token_omitted?: boolean;
}

export interface OperatorLoopRecordMemoryReview {
  memory_id: string;
  scope?: string;
  memory_type?: string;
  review_status: string;
  source_type?: string;
  source_ref?: string | null;
  task_id?: string | null;
  agent_id?: string | null;
  confidence?: number;
  summary?: string;
  created_at?: string | null;
  updated_at?: string | null;
  approve_command?: string;
  reject_command?: string;
  token_omitted?: boolean;
}

export interface OperatorLoopRecordApprovalReview {
  approval_id: string;
  task_id?: string | null;
  run_id?: string | null;
  tool_call_id?: string | null;
  requested_by_agent_id?: string | null;
  decision: string;
  reason?: string;
  created_at?: string | null;
  decided_at?: string | null;
  approve_command?: string;
  reject_command?: string;
  token_omitted?: boolean;
}

export interface OperatorLoopRecordAuditEntry {
  audit_id: string;
  actor_type?: string | null;
  actor_id?: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  before_hash?: string | null;
  after_hash?: string | null;
  tamper_chain_hash?: string | null;
  created_at?: string | null;
  token_omitted?: boolean;
}

export interface OperatorLoopRecordPayload {
  status: string;
  loop_id?: string | null;
  memory_reviews: OperatorLoopRecordMemoryReview[];
  approval_reviews: OperatorLoopRecordApprovalReview[];
  candidate_count: number;
  approved_count: number;
  pending_approval_count: number;
  audit_count: number;
  audit_trail: OperatorLoopRecordAuditEntry[];
  next_action?: string;
  review_queue_command?: string;
  token_omitted?: boolean;
}

export interface OperatorLoopAuditPayload {
  provider: string;
  operation: string;
  status: string;
  workspace_id: string;
  loop_id?: string | null;
  method: string;
  summary: {
    steps: number;
    pass: number;
    attention: number;
    blocked: number;
    knowledge_documents: number;
    verified_agent_plans: number;
    plan_bound_runs: number;
    verified_plan_evidence_manifests: number;
    evidence_gap_runs: number;
    loop_runs: number;
    loop_verified_plan_evidence_manifests: number;
    loop_blocked_plan_evidence_manifests: number;
    pending_approvals: number;
    memory_candidates: number;
    loop_memory_candidates: number;
    loop_approved_memories: number;
    loop_pending_approvals: number;
    audit_logs: number;
  };
  steps: OperatorLoopAuditStep[];
  next_actions: string[];
  source_status: Record<string, string | undefined>;
  sources?: Record<string, unknown>;
  loop_record?: OperatorLoopRecordPayload;
  loop_readback?: HermesOpenClawLoopReadbackPayload | Record<string, unknown>;
  safety: {
    read_only: boolean;
    ledger_mutated: boolean;
    live_execution_performed: boolean;
    raw_prompt_omitted: boolean;
    raw_response_omitted: boolean;
    token_omitted: boolean;
  };
  token_omitted?: boolean;
  live_execution_performed?: boolean;
}

export interface EvaluationCaseCandidate {
  case_id: string;
  workspace_id: string;
  source_type: string;
  source_ref?: string | null;
  task_id?: string | null;
  run_id?: string | null;
  artifact_id?: string | null;
  evaluation_id?: string | null;
  agent_id?: string | null;
  case_type: string;
  title: string;
  input_summary?: string | null;
  expected_output_summary?: string | null;
  failure_mode?: string | null;
  confidence: number;
  review_status: string;
  created_by_agent_id?: string | null;
  owner_user_id?: string | null;
  created_at: string;
  updated_at: string;
  rubric?: Record<string, unknown>;
  token_omitted?: boolean;
}

export interface EvaluationCaseCandidatesPayload {
  provider: string;
  operation: string;
  status: string;
  workspace_id: string;
  limit: number;
  summary: {
    candidate: number;
    approved: number;
    rejected: number;
    returned: number;
  };
  cases: EvaluationCaseCandidate[];
  next_actions: string[];
  safety: {
    read_only: boolean;
    ledger_mutated: boolean;
    live_execution_performed: boolean;
    raw_prompt_omitted: boolean;
    raw_response_omitted: boolean;
    token_omitted: boolean;
  };
  token_omitted: boolean;
}

export interface EvaluationCaseRun {
  case_run_id?: string;
  case_id: string;
  workspace_id?: string;
  run_id?: string;
  evaluation_id?: string;
  artifact_id?: string | null;
  runner_type: string;
  status: string;
  score: number;
  pass_fail: "pass" | "fail";
  review_status?: string;
  reviewed_by_user_id?: string | null;
  review_note?: string | null;
  reviewed_at?: string | null;
  checks?: Record<string, unknown>;
  case_title?: string;
  case_type?: string;
  task_id?: string | null;
  source_type?: string | null;
  source_ref?: string | null;
  created_by_agent_id?: string | null;
  created_at?: string;
  token_omitted?: boolean;
}

export interface EvaluationCaseRunPayload {
  provider: string;
  operation: string;
  status: string;
  created?: boolean;
  workspace_id: string;
  limit?: number;
  summary: {
    selected?: number;
    planned?: number;
    skipped?: number;
    total?: number;
    returned?: number;
    created?: number;
    passed?: number;
    failed?: number;
    min_score?: number;
  };
  planned_runs?: EvaluationCaseRun[];
  case_runs: EvaluationCaseRun[];
  skipped?: EvaluationCaseRun[];
  next_actions?: string[];
  safety: {
    read_only?: boolean;
    ledger_mutated: boolean;
    live_execution_performed: boolean;
    raw_prompt_omitted: boolean;
    raw_response_omitted: boolean;
    token_omitted: boolean;
  };
  token_omitted: boolean;
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
  run_id?: string | null;
  agent_plan_id?: string | null;
  plan_evidence_manifest_id?: string | null;
  plan_evidence_status?: string | null;
  plan_evidence_pass?: boolean;
  evidence?: {
    task_id?: string;
    run_id?: string | null;
    agent_plan_id?: string | null;
    agent_plan_status?: string | null;
    agent_plan_verified?: boolean;
    plan_hash?: string | null;
    plan_evidence_manifest_id?: string | null;
    plan_evidence_status?: string | null;
    plan_evidence_pass?: boolean;
    evidence_counts?: Record<string, number>;
    intake?: Record<string, unknown> | null;
    ready_for_delivery?: boolean;
    token_omitted?: boolean;
  };
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
  message?: string;
  recommended_action?: string;
  task_intake?: TaskIntakeChecklistPayload;
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

export interface WorkerFleetHygienePayload {
  provider: string;
  operation: string;
  status: string;
  threshold_sec: number;
  enrollment_age_sec: number;
  summary: {
    stuck_tasks: number;
    stale_never_seen_enrollments: number;
    actions_available: number;
    released_tasks?: number;
    revoked_enrollments?: number;
    errors?: number;
  };
  stuck_tasks: StuckWorkerTask[];
  stale_never_seen_enrollments: AgentGatewayEnrollment[];
  recommended_actions: string[];
  safety: {
    read_only: boolean;
    requires_confirm_cleanup: boolean;
    live_execution_performed: boolean;
    token_omitted: boolean;
  };
  applied?: boolean;
  released_tasks?: { task_id: string; released_runs: string[] }[];
  revoked_enrollments?: { token_id: string; agent_id?: string | null; sessions_revoked?: number }[];
  errors?: Record<string, unknown>[];
  error?: string;
  token_omitted: boolean;
  live_execution_performed: boolean;
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

export interface AgentGatewayEnrollmentPolicyPreview {
  provider: string;
  operation: string;
  status: string;
  workspace_id: string;
  runtime_type: string;
  policy: string;
  risk_level: string;
  approval_recommended: boolean;
  recommended_path: string;
  scope_count: number;
  scopes: string[];
  invalid_scopes: string[];
  privileged_scopes: string[];
  worker_write_scopes: string[];
  missing_worker_scopes: string[];
  gates: { id: string; ok: boolean; status: string; summary: string }[];
  next_actions: string[];
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

export function normalizeEvaluationCaseCandidate(row: Record<string, unknown>): EvaluationCaseCandidate {
  const rubric = typeof row.rubric === "object" && row.rubric !== null ? row.rubric as Record<string, unknown> : {};
  return {
    case_id: String(row.case_id || ""),
    workspace_id: String(row.workspace_id || "local-demo"),
    source_type: String(row.source_type || "manual"),
    source_ref: row.source_ref ? String(row.source_ref) : null,
    task_id: row.task_id ? String(row.task_id) : null,
    run_id: row.run_id ? String(row.run_id) : null,
    artifact_id: row.artifact_id ? String(row.artifact_id) : null,
    evaluation_id: row.evaluation_id ? String(row.evaluation_id) : null,
    agent_id: row.agent_id ? String(row.agent_id) : null,
    case_type: String(row.case_type || "quality"),
    title: String(row.title || row.case_id || "Evaluation case"),
    input_summary: row.input_summary ? String(row.input_summary) : null,
    expected_output_summary: row.expected_output_summary ? String(row.expected_output_summary) : null,
    failure_mode: row.failure_mode ? String(row.failure_mode) : null,
    confidence: numberValue(row.confidence, 0),
    review_status: String(row.review_status || "candidate"),
    created_by_agent_id: row.created_by_agent_id ? String(row.created_by_agent_id) : null,
    owner_user_id: row.owner_user_id ? String(row.owner_user_id) : null,
    created_at: String(row.created_at || ""),
    updated_at: String(row.updated_at || row.created_at || ""),
    rubric,
    token_omitted: boolValue(row.token_omitted),
  };
}

export function normalizeEvaluationCaseRun(row: Record<string, unknown>): EvaluationCaseRun {
  const checks = typeof row.checks === "object" && row.checks !== null ? row.checks as Record<string, unknown> : {};
  return {
    case_run_id: row.case_run_id ? String(row.case_run_id) : undefined,
    case_id: String(row.case_id || ""),
    workspace_id: row.workspace_id ? String(row.workspace_id) : undefined,
    run_id: row.run_id ? String(row.run_id) : undefined,
    evaluation_id: row.evaluation_id ? String(row.evaluation_id) : undefined,
    artifact_id: row.artifact_id ? String(row.artifact_id) : null,
    runner_type: String(row.runner_type || "rule"),
    status: String(row.status || "preview"),
    score: numberValue(row.score, 0),
    pass_fail: String(row.pass_fail || "fail") === "pass" ? "pass" : "fail",
    review_status: row.review_status ? String(row.review_status) : "open",
    reviewed_by_user_id: row.reviewed_by_user_id ? String(row.reviewed_by_user_id) : null,
    review_note: row.review_note ? String(row.review_note) : null,
    reviewed_at: row.reviewed_at ? String(row.reviewed_at) : null,
    checks,
    case_title: row.case_title ? String(row.case_title) : undefined,
    case_type: row.case_type ? String(row.case_type) : undefined,
    task_id: row.task_id ? String(row.task_id) : null,
    source_type: row.source_type ? String(row.source_type) : null,
    source_ref: row.source_ref ? String(row.source_ref) : null,
    created_by_agent_id: row.created_by_agent_id ? String(row.created_by_agent_id) : null,
    created_at: row.created_at ? String(row.created_at) : undefined,
    token_omitted: boolValue(row.token_omitted),
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

export async function loadEvaluations(): Promise<Evaluation[]> {
  return (await apiJson<Record<string, unknown>[]>("/evaluations")).map(normalizeEvaluation);
}

export async function loadEvaluationCaseCandidates(input: {
  status?: string;
  limit?: number;
  run_id?: string;
  task_id?: string;
  artifact_id?: string;
} = {}): Promise<EvaluationCaseCandidatesPayload> {
  const params = new URLSearchParams();
  params.set("status", input.status || "candidate");
  params.set("limit", String(input.limit || 25));
  if (input.run_id) params.set("run_id", input.run_id);
  if (input.task_id) params.set("task_id", input.task_id);
  if (input.artifact_id) params.set("artifact_id", input.artifact_id);
  const raw = await optionalApiJson<Record<string, unknown>>(`/evaluation-cases?${params.toString()}`, {
    provider: "agentops-evaluation",
    operation: "evaluation_case_candidates",
    status: "unavailable",
    workspace_id: "local-demo",
    limit: input.limit || 25,
    summary: {},
    cases: [],
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
  });
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-evaluation"),
    operation: String(raw.operation || "evaluation_case_candidates"),
    status: String(raw.status || "unknown"),
    workspace_id: String(raw.workspace_id || "local-demo"),
    limit: numberValue(raw.limit, input.limit || 25),
    summary: {
      candidate: numberValue(summaryRaw.candidate, 0),
      approved: numberValue(summaryRaw.approved, 0),
      rejected: numberValue(summaryRaw.rejected, 0),
      returned: numberValue(summaryRaw.returned, 0),
    },
    cases: asArray<Record<string, unknown>>(raw.cases).map(normalizeEvaluationCaseCandidate),
    next_actions: asArray(raw.next_actions).map(String),
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

function normalizeEvaluationCaseRunPayload(raw: Record<string, unknown>, fallbackStatus = "unknown"): EvaluationCaseRunPayload {
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-evaluation"),
    operation: String(raw.operation || "evaluation_case_runs"),
    status: String(raw.status || fallbackStatus),
    created: raw.created === undefined ? undefined : boolValue(raw.created),
    workspace_id: String(raw.workspace_id || "local-demo"),
    limit: raw.limit === undefined ? undefined : numberValue(raw.limit, 0),
    summary: {
      selected: summaryRaw.selected === undefined ? undefined : numberValue(summaryRaw.selected, 0),
      planned: summaryRaw.planned === undefined ? undefined : numberValue(summaryRaw.planned, 0),
      skipped: summaryRaw.skipped === undefined ? undefined : numberValue(summaryRaw.skipped, 0),
      total: summaryRaw.total === undefined ? undefined : numberValue(summaryRaw.total, 0),
      returned: summaryRaw.returned === undefined ? undefined : numberValue(summaryRaw.returned, 0),
      created: summaryRaw.created === undefined ? undefined : numberValue(summaryRaw.created, 0),
      passed: summaryRaw.passed === undefined ? undefined : numberValue(summaryRaw.passed, 0),
      failed: summaryRaw.failed === undefined ? undefined : numberValue(summaryRaw.failed, 0),
      min_score: summaryRaw.min_score === undefined ? undefined : numberValue(summaryRaw.min_score, 0),
    },
    planned_runs: asArray<Record<string, unknown>>(raw.planned_runs).map(normalizeEvaluationCaseRun),
    case_runs: asArray<Record<string, unknown>>(raw.case_runs).map(normalizeEvaluationCaseRun),
    skipped: asArray<Record<string, unknown>>(raw.skipped).map(normalizeEvaluationCaseRun),
    next_actions: asArray(raw.next_actions).map(String),
    safety: {
      read_only: safetyRaw.read_only === undefined ? undefined : boolValue(safetyRaw.read_only),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
      raw_response_omitted: boolValue(safetyRaw.raw_response_omitted),
      token_omitted: boolValue(safetyRaw.token_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
  };
}

export async function loadEvaluationCaseRuns(input: {
  limit?: number;
  case_id?: string;
  run_id?: string;
  task_id?: string;
  pass_fail?: "pass" | "fail";
} = {}): Promise<EvaluationCaseRunPayload> {
  const params = new URLSearchParams();
  params.set("limit", String(input.limit || 25));
  if (input.case_id) params.set("case_id", input.case_id);
  if (input.run_id) params.set("run_id", input.run_id);
  if (input.task_id) params.set("task_id", input.task_id);
  if (input.pass_fail) params.set("pass_fail", input.pass_fail);
  const raw = await optionalApiJson<Record<string, unknown>>(`/evaluation-case-runs?${params.toString()}`, {
    provider: "agentops-evaluation",
    operation: "evaluation_case_runs",
    status: "unavailable",
    workspace_id: "local-demo",
    summary: {},
    case_runs: [],
    safety: {
      read_only: true,
      ledger_mutated: false,
      live_execution_performed: false,
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      token_omitted: true,
    },
    token_omitted: true,
  });
  return normalizeEvaluationCaseRunPayload(raw, "unavailable");
}

export async function runEvaluationCases(input: {
  case_ids?: string[];
  case_type?: string;
  status?: string;
  runner_type?: "rule" | "llm_mock";
  task_id?: string;
  run_id?: string;
  artifact_id?: string;
  limit?: number;
  min_score?: number;
  confirm_run?: boolean;
} = {}): Promise<EvaluationCaseRunPayload> {
  const raw = await apiJson<Record<string, unknown>>("/evaluation-cases/run", {
    method: "POST",
    body: JSON.stringify({
      case_ids: input.case_ids || [],
      case_type: input.case_type,
      status: input.status || "approved",
      runner_type: input.runner_type || "rule",
      task_id: input.task_id,
      run_id: input.run_id,
      artifact_id: input.artifact_id,
      limit: input.limit || 10,
      min_score: input.min_score ?? 0.75,
      confirm_run: Boolean(input.confirm_run),
    }),
  });
  return normalizeEvaluationCaseRunPayload(raw, input.confirm_run ? "completed" : "preview");
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
    evaluation_case_runs: asArray<Record<string, unknown>>(raw.evaluation_case_runs).map(normalizeEvaluationCaseRun),
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
    evaluation_case_runs: asArray<Record<string, unknown>>(raw.evaluation_case_runs).map(normalizeEvaluationCaseRun),
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

export async function decideEvaluationCase(id: string, decision: "approve" | "reject"): Promise<Record<string, unknown>> {
  return apiJson<Record<string, unknown>>(`/evaluation-cases/${encodeURIComponent(id)}/${decision}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
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

export async function loadHermesOpenClawLoopReadback(loopId = "", limit = 10): Promise<HermesOpenClawLoopReadbackPayload> {
  const params = new URLSearchParams();
  if (loopId) params.set("loop_id", loopId);
  params.set("limit", String(limit));
  return apiJson<HermesOpenClawLoopReadbackPayload>(`/workflows/hermes-openclaw-loop?${params.toString()}`);
}

export async function runHermesOpenClawLoopWorkflow(input: {
  topic: string;
  loop_id?: string;
  rounds?: number;
  mode?: "dry-run" | "live-hermes" | "live-openclaw" | "live-both";
  confirm_live?: boolean;
  resume?: boolean;
  order?: ("hermes" | "openclaw")[];
  request_timeout?: number;
  max_agent_attempts?: number;
  retry_delay_sec?: number;
  simulate_failure_agent?: ("hermes" | "openclaw")[];
}): Promise<HermesOpenClawLoopWorkflowResult> {
  return apiJsonWithStatuses<HermesOpenClawLoopWorkflowResult>("/workflows/hermes-openclaw-loop", {
    method: "POST",
    body: JSON.stringify(input),
  }, [201, 409]);
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

function normalizeWorkerFleetHygiene(raw: Record<string, unknown>): WorkerFleetHygienePayload {
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-worker"),
    operation: String(raw.operation || "fleet_hygiene"),
    status: String(raw.status || "unknown"),
    threshold_sec: numberValue(raw.threshold_sec, 900),
    enrollment_age_sec: numberValue(raw.enrollment_age_sec, 900),
    summary: {
      stuck_tasks: numberValue(summaryRaw.stuck_tasks, 0),
      stale_never_seen_enrollments: numberValue(summaryRaw.stale_never_seen_enrollments, 0),
      actions_available: numberValue(summaryRaw.actions_available, 0),
      released_tasks: summaryRaw.released_tasks === undefined ? undefined : numberValue(summaryRaw.released_tasks, 0),
      revoked_enrollments: summaryRaw.revoked_enrollments === undefined ? undefined : numberValue(summaryRaw.revoked_enrollments, 0),
      errors: summaryRaw.errors === undefined ? undefined : numberValue(summaryRaw.errors, 0),
    },
    stuck_tasks: asArray<Record<string, unknown>>(raw.stuck_tasks).map((row) => ({
      ...normalizeTask(row),
      age_sec: numberValue(row.age_sec, 0),
      threshold_sec: numberValue(row.threshold_sec, 0),
      running_run_id: row.running_run_id ? String(row.running_run_id) : null,
      running_run_started_at: row.running_run_started_at ? String(row.running_run_started_at) : null,
      stuck_reason: row.stuck_reason ? String(row.stuck_reason) : undefined,
    })),
    stale_never_seen_enrollments: asArray<Record<string, unknown>>(raw.stale_never_seen_enrollments).map(normalizeAgentGatewayEnrollment),
    recommended_actions: asArray(raw.recommended_actions).map(String).filter(Boolean),
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      requires_confirm_cleanup: boolValue(safetyRaw.requires_confirm_cleanup),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
    },
    applied: raw.applied === undefined ? undefined : boolValue(raw.applied),
    released_tasks: asArray<Record<string, unknown>>(raw.released_tasks).map((item) => ({
      task_id: String(item.task_id || ""),
      released_runs: asArray(item.released_runs).map(String),
    })).filter((item) => item.task_id),
    revoked_enrollments: asArray<Record<string, unknown>>(raw.revoked_enrollments).map((item) => ({
      token_id: String(item.token_id || ""),
      agent_id: item.agent_id ? String(item.agent_id) : null,
      sessions_revoked: numberValue(item.sessions_revoked, 0),
    })).filter((item) => item.token_id),
    errors: asArray<Record<string, unknown>>(raw.errors),
    error: raw.error ? String(raw.error) : undefined,
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
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
  const raw = await optionalApiJson<Record<string, unknown>>(`/workers/fleet/hygiene${suffix}`, {
    provider: "agentops-worker",
    operation: "fleet_hygiene",
    status: "unavailable",
    threshold_sec: options.threshold_sec || 900,
    enrollment_age_sec: options.enrollment_age_sec || 900,
    summary: {
      stuck_tasks: 0,
      stale_never_seen_enrollments: 0,
      actions_available: 0,
    },
    stuck_tasks: [],
    stale_never_seen_enrollments: [],
    recommended_actions: [],
    safety: {
      read_only: true,
      requires_confirm_cleanup: true,
      live_execution_performed: false,
      token_omitted: true,
    },
    token_omitted: true,
    live_execution_performed: false,
    fallback_reason: "endpoint_not_available",
  });
  return normalizeWorkerFleetHygiene(raw);
}

export async function applyWorkerFleetHygiene(input: {
  threshold_sec?: number;
  enrollment_age_sec?: number;
  limit?: number;
  release_reason?: string;
} = {}): Promise<WorkerFleetHygienePayload> {
  const raw = await apiJsonWithStatuses<Record<string, unknown>>("/workers/fleet/hygiene", {
    method: "POST",
    body: JSON.stringify({
      ...input,
      apply: true,
      confirm_cleanup: true,
    }),
  }, [200, 207, 409]);
  return normalizeWorkerFleetHygiene(raw);
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
  const lifecycleRaw = typeof raw.commander_synthesis_lifecycle === "object" && raw.commander_synthesis_lifecycle !== null ? raw.commander_synthesis_lifecycle as Record<string, unknown> : {};
  const lifecycleSummaryRaw = typeof lifecycleRaw.summary === "object" && lifecycleRaw.summary !== null ? lifecycleRaw.summary as Record<string, unknown> : {};
  const lifecycleSafetyRaw = typeof lifecycleRaw.safety === "object" && lifecycleRaw.safety !== null ? lifecycleRaw.safety as Record<string, unknown> : {};
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
      commander_synthesis_artifacts: numberValue(evidenceRaw.commander_synthesis_artifacts, 0),
      commander_synthesis_pending_reviews: numberValue(evidenceRaw.commander_synthesis_pending_reviews, 0),
      commander_synthesis_approved_reviews: numberValue(evidenceRaw.commander_synthesis_approved_reviews, 0),
      commander_synthesis_promoted_memories: numberValue(evidenceRaw.commander_synthesis_promoted_memories, 0),
      commander_synthesis_promoted_deliveries: numberValue(evidenceRaw.commander_synthesis_promoted_deliveries, 0),
      has_task_run_tool_eval_audit_artifact_chain: boolValue(evidenceRaw.has_task_run_tool_eval_audit_artifact_chain),
      has_memory_or_knowledge: boolValue(evidenceRaw.has_memory_or_knowledge),
      has_approval_flow: boolValue(evidenceRaw.has_approval_flow),
    },
    adapter_readiness: adapterReadiness,
    commander_synthesis_lifecycle: raw.commander_synthesis_lifecycle ? {
      status: String(lifecycleRaw.status || "unknown"),
      summary: {
        synthesis_artifacts: numberValue(lifecycleSummaryRaw.synthesis_artifacts, 0),
        pending_reviews: numberValue(lifecycleSummaryRaw.pending_reviews, 0),
        approved_reviews: numberValue(lifecycleSummaryRaw.approved_reviews, 0),
        rejected_reviews: numberValue(lifecycleSummaryRaw.rejected_reviews, 0),
        promoted_memory_candidates: numberValue(lifecycleSummaryRaw.promoted_memory_candidates, 0),
        promoted_delivery_artifacts: numberValue(lifecycleSummaryRaw.promoted_delivery_artifacts, 0),
      },
      recent: asArray<Record<string, unknown>>(lifecycleRaw.recent),
      next_actions: asArray(lifecycleRaw.next_actions).map(String),
      safety: {
        read_only: boolValue(lifecycleSafetyRaw.read_only),
        ledger_mutated: boolValue(lifecycleSafetyRaw.ledger_mutated),
        live_execution_performed: boolValue(lifecycleSafetyRaw.live_execution_performed),
        token_omitted: boolValue(lifecycleSafetyRaw.token_omitted),
      },
      token_omitted: boolValue(lifecycleRaw.token_omitted),
      live_execution_performed: boolValue(lifecycleRaw.live_execution_performed),
    } : undefined,
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

export async function planCommanderWorkPackages(input: {
  goal: string;
  project_id?: string;
  plan_id?: string;
  max_packages?: number;
  confirm_create?: boolean;
}): Promise<CommanderWorkPackagePlanPayload> {
  const raw = await apiJson<Record<string, unknown>>("/commander/work-packages/plan", {
    method: "POST",
    body: JSON.stringify(input),
  });
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-commander"),
    operation: String(raw.operation || "work_package_plan"),
    status: String(raw.status || "unknown"),
    ok: boolValue(raw.ok),
    workspace_id: String(raw.workspace_id || "local-demo"),
    project_id: String(raw.project_id || ""),
    plan_id: String(raw.plan_id || ""),
    goal_summary: String(raw.goal_summary || ""),
    confirm_create: boolValue(raw.confirm_create),
    created: boolValue(raw.created),
    created_count: numberValue(raw.created_count, 0),
    planned_count: numberValue(raw.planned_count, 0),
    work_packages: asArray<Record<string, unknown>>(raw.work_packages).map((item) => ({
      plan_id: String(item.plan_id || raw.plan_id || ""),
      project_id: String(item.project_id || raw.project_id || ""),
      lane_id: String(item.lane_id || ""),
      task_id: String(item.task_id || ""),
      title: String(item.title || "Untitled work package"),
      description: String(item.description || ""),
      owner_agent_id: String(item.owner_agent_id || ""),
      collaborator_agent_ids: asArray<unknown>(item.collaborator_agent_ids).map(String),
      status: String(item.status || "planned"),
      priority: String(item.priority || "medium"),
      risk_level: String(item.risk_level || "medium"),
      acceptance_criteria: String(item.acceptance_criteria || ""),
      dependencies: asArray<unknown>(item.dependencies).map(String),
      verification_commands: asArray<unknown>(item.verification_commands).map(String),
      scope: String(item.scope || ""),
      avoid_scope: String(item.avoid_scope || ""),
    })),
    created_task_ids: asArray<unknown>(raw.created_task_ids).map(String),
    errors: asArray<Record<string, unknown>>(raw.errors).map((item) => ({
      lane_id: item.lane_id ? String(item.lane_id) : undefined,
      task_id: item.task_id ? String(item.task_id) : undefined,
      error: item.error ? String(item.error) : undefined,
      message: item.message ? String(item.message) : undefined,
    })),
    recommended_next_actions: asArray<unknown>(raw.recommended_next_actions).map(String).filter(Boolean),
    safety: {
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
      dry_run: boolValue(safetyRaw.dry_run),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      task_created: boolValue(safetyRaw.task_created),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function loadCommanderWorkPackages(options: {
  project_id?: string;
  plan_id?: string;
  status?: string;
  limit?: number;
} = {}): Promise<CommanderWorkPackageReadbackPayload> {
  const params = new URLSearchParams();
  if (options.project_id) params.set("project_id", options.project_id);
  if (options.plan_id) params.set("plan_id", options.plan_id);
  if (options.status) params.set("status", options.status);
  if (options.limit) params.set("limit", String(options.limit));
  const raw = await optionalApiJson<Record<string, unknown>>(`/commander/work-packages${params.toString() ? `?${params}` : ""}`, {
    provider: "agentops-commander",
    operation: "work_packages_readback",
    status: "unavailable",
    workspace_id: "local-demo",
    filter: { status: options.status || "all", limit: options.limit || 25 },
    summary: {},
    work_packages: [],
    recommended_next_actions: [],
    safety: {
      read_only: true,
      ledger_mutated: false,
      task_created: false,
      run_created: false,
      live_execution_performed: false,
      token_omitted: true,
      raw_prompt_omitted: true,
    },
    token_omitted: true,
    live_execution_performed: false,
  });
  const filterRaw = typeof raw.filter === "object" && raw.filter !== null ? raw.filter as Record<string, unknown> : {};
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-commander"),
    operation: String(raw.operation || "work_packages_readback"),
    status: String(raw.status || "unknown"),
    workspace_id: String(raw.workspace_id || "local-demo"),
    filter: {
      project_id: filterRaw.project_id ? String(filterRaw.project_id) : null,
      plan_id: filterRaw.plan_id ? String(filterRaw.plan_id) : null,
      status: String(filterRaw.status || options.status || "all"),
      limit: numberValue(filterRaw.limit, options.limit || 25),
    },
    summary: {
      total: numberValue(summaryRaw.total, 0),
      by_status: numberRecord(summaryRaw.by_status),
      by_project: numberRecord(summaryRaw.by_project),
    },
    work_packages: asArray<Record<string, unknown>>(raw.work_packages).map((item) => {
      const latestRun = typeof item.latest_run === "object" && item.latest_run !== null ? item.latest_run as Record<string, unknown> : null;
      return {
        plan_id: String(item.plan_id || ""),
        project_id: String(item.project_id || ""),
        lane_id: String(item.lane_id || ""),
        task_id: String(item.task_id || ""),
        work_package_id: String(item.work_package_id || item.task_id || ""),
        title: String(item.title || "Untitled work package"),
        description: String(item.description || ""),
        owner_agent_id: String(item.owner_agent_id || ""),
        collaborator_agent_ids: asArray<unknown>(item.collaborator_agent_ids).map(String),
        status: String(item.status || "unknown"),
        package_status: String(item.package_status || item.status || "unknown"),
        priority: String(item.priority || "medium"),
        risk_level: String(item.risk_level || "medium"),
        acceptance_criteria: String(item.acceptance_criteria || ""),
        dependencies: asArray<unknown>(item.dependencies).map(String),
        verification_commands: asArray<unknown>(item.verification_commands).map(String),
        scope: String(item.scope || ""),
        avoid_scope: String(item.avoid_scope || ""),
        latest_run: latestRun ? {
          run_id: latestRun.run_id ? String(latestRun.run_id) : undefined,
          status: latestRun.status ? String(latestRun.status) : undefined,
          agent_id: latestRun.agent_id ? String(latestRun.agent_id) : undefined,
          runtime_type: latestRun.runtime_type ? String(latestRun.runtime_type) : undefined,
          created_at: latestRun.created_at ? String(latestRun.created_at) : undefined,
          ended_at: latestRun.ended_at ? String(latestRun.ended_at) : null,
          error_type: latestRun.error_type ? String(latestRun.error_type) : null,
          error_message: latestRun.error_message ? String(latestRun.error_message) : null,
        } : null,
        evidence_counts: numberRecord(item.evidence_counts),
        recommended_action: item.recommended_action ? String(item.recommended_action) : undefined,
        created_at: item.created_at ? String(item.created_at) : undefined,
        updated_at: item.updated_at ? String(item.updated_at) : undefined,
      };
    }),
    recommended_next_actions: asArray<unknown>(raw.recommended_next_actions).map(String).filter(Boolean),
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      task_created: boolValue(safetyRaw.task_created),
      run_created: boolValue(safetyRaw.run_created),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function dispatchCommanderWorkPackage(input: {
  task_id: string;
  adapter?: WorkerAdapterName;
  confirm_run?: boolean;
  worker_agent_id?: string;
  hermes_timeout?: number;
}): Promise<CommanderWorkPackageDispatchPayload> {
  const raw = await apiJson<Record<string, unknown>>(`/commander/work-packages/${encodeURIComponent(input.task_id)}/dispatch`, {
    method: "POST",
    body: JSON.stringify({
      adapter: input.adapter || "mock",
      confirm_run: Boolean(input.confirm_run),
      worker_agent_id: input.worker_agent_id,
      hermes_timeout: input.hermes_timeout,
    }),
  });
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  const workPackageRaw = typeof raw.work_package === "object" && raw.work_package !== null ? raw.work_package as Record<string, unknown> : null;
  const latestRun = workPackageRaw && typeof workPackageRaw.latest_run === "object" && workPackageRaw.latest_run !== null
    ? workPackageRaw.latest_run as Record<string, unknown>
    : null;
  const workPackage = workPackageRaw ? {
    plan_id: String(workPackageRaw.plan_id || ""),
    project_id: String(workPackageRaw.project_id || ""),
    lane_id: String(workPackageRaw.lane_id || ""),
    task_id: String(workPackageRaw.task_id || raw.task_id || ""),
    work_package_id: String(workPackageRaw.work_package_id || workPackageRaw.task_id || raw.task_id || ""),
    title: String(workPackageRaw.title || "Untitled work package"),
    description: String(workPackageRaw.description || ""),
    owner_agent_id: String(workPackageRaw.owner_agent_id || ""),
    collaborator_agent_ids: asArray<unknown>(workPackageRaw.collaborator_agent_ids).map(String),
    status: String(workPackageRaw.status || "unknown"),
    package_status: String(workPackageRaw.package_status || workPackageRaw.status || "unknown"),
    priority: String(workPackageRaw.priority || "medium"),
    risk_level: String(workPackageRaw.risk_level || "medium"),
    acceptance_criteria: String(workPackageRaw.acceptance_criteria || ""),
    dependencies: asArray<unknown>(workPackageRaw.dependencies).map(String),
    verification_commands: asArray<unknown>(workPackageRaw.verification_commands).map(String),
    scope: String(workPackageRaw.scope || ""),
    avoid_scope: String(workPackageRaw.avoid_scope || ""),
    latest_run: latestRun ? {
      run_id: latestRun.run_id ? String(latestRun.run_id) : undefined,
      status: latestRun.status ? String(latestRun.status) : undefined,
      agent_id: latestRun.agent_id ? String(latestRun.agent_id) : undefined,
      runtime_type: latestRun.runtime_type ? String(latestRun.runtime_type) : undefined,
      created_at: latestRun.created_at ? String(latestRun.created_at) : undefined,
      ended_at: latestRun.ended_at ? String(latestRun.ended_at) : null,
      error_type: latestRun.error_type ? String(latestRun.error_type) : null,
      error_message: latestRun.error_message ? String(latestRun.error_message) : null,
    } : null,
    evidence_counts: numberRecord(workPackageRaw.evidence_counts),
    recommended_action: workPackageRaw.recommended_action ? String(workPackageRaw.recommended_action) : undefined,
    created_at: workPackageRaw.created_at ? String(workPackageRaw.created_at) : undefined,
    updated_at: workPackageRaw.updated_at ? String(workPackageRaw.updated_at) : undefined,
  } : null;
  return {
    provider: String(raw.provider || "agentops-commander"),
    operation: String(raw.operation || "work_package_dispatch"),
    ok: boolValue(raw.ok),
    dry_run: boolValue(raw.dry_run),
    adapter: String(raw.adapter || input.adapter || "mock"),
    task_id: String(raw.task_id || input.task_id),
    agent_id: raw.agent_id ? String(raw.agent_id) : null,
    run_id: raw.run_id ? String(raw.run_id) : null,
    work_package: workPackage,
    evidence: numberRecord(raw.evidence),
    duration_ms: raw.duration_ms === null || raw.duration_ms === undefined ? null : numberValue(raw.duration_ms, 0),
    error: raw.error ? String(raw.error) : null,
    reason: raw.reason ? String(raw.reason) : null,
    requires: typeof raw.requires === "object" && raw.requires !== null ? raw.requires as Record<string, boolean> : undefined,
    safety: {
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      run_created: boolValue(safetyRaw.run_created),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function dispatchCommanderWorkPackageBatch(input: {
  project_id?: string;
  plan_id?: string;
  task_ids?: string[];
  status?: string;
  limit?: number;
  adapter?: WorkerAdapterName;
  confirm_run?: boolean;
  hermes_timeout?: number;
}): Promise<CommanderWorkPackageDispatchBatchPayload> {
  const raw = await apiJsonWithStatuses<Record<string, unknown>>("/commander/work-packages/dispatch-batch", {
    method: "POST",
    body: JSON.stringify({
      project_id: input.project_id,
      plan_id: input.plan_id,
      task_ids: input.task_ids || [],
      status: input.status || "planned",
      limit: input.limit || 5,
      adapter: input.adapter || "mock",
      confirm_run: Boolean(input.confirm_run),
      hermes_timeout: input.hermes_timeout,
    }),
  }, [409, 404]);
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  const filterRaw = typeof raw.filter === "object" && raw.filter !== null ? raw.filter as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-commander"),
    operation: String(raw.operation || "work_package_dispatch_batch"),
    ok: boolValue(raw.ok),
    status: raw.status ? String(raw.status) : undefined,
    adapter: String(raw.adapter || input.adapter || "mock"),
    confirm_run: boolValue(raw.confirm_run),
    jobs: asArray<WorkflowJob>(raw.jobs),
    job_ids: asArray<unknown>(raw.job_ids).map(String),
    task_ids: asArray<unknown>(raw.task_ids).map(String),
    status_urls: asArray<unknown>(raw.status_urls).map(String),
    reason: raw.reason ? String(raw.reason) : null,
    filter: {
      project_id: filterRaw.project_id ? String(filterRaw.project_id) : null,
      plan_id: filterRaw.plan_id ? String(filterRaw.plan_id) : null,
      status: filterRaw.status ? String(filterRaw.status) : undefined,
      limit: filterRaw.limit === undefined ? undefined : numberValue(filterRaw.limit, input.limit || 5),
    },
    safety: {
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      jobs_created: numberValue(safetyRaw.jobs_created, 0),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function synthesizeCommanderWorkPackages(input: {
  project_id?: string;
  plan_id?: string;
  task_ids?: string[];
  status?: string;
  limit?: number;
  confirm_create?: boolean;
  artifact_id?: string;
}): Promise<CommanderWorkPackageSynthesisPayload> {
  const raw = await apiJsonWithStatuses<Record<string, unknown>>("/commander/work-packages/synthesize", {
    method: "POST",
    body: JSON.stringify({
      project_id: input.project_id,
      plan_id: input.plan_id,
      task_ids: input.task_ids || [],
      status: input.status || "ready_for_review",
      limit: input.limit || 10,
      confirm_create: Boolean(input.confirm_create),
      artifact_id: input.artifact_id,
    }),
  }, [404]);
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-commander"),
    operation: String(raw.operation || "work_package_synthesis"),
    ok: boolValue(raw.ok),
    status: String(raw.status || "unknown"),
    workspace_id: String(raw.workspace_id || "local-demo"),
    project_id: raw.project_id ? String(raw.project_id) : undefined,
    plan_id: raw.plan_id ? String(raw.plan_id) : undefined,
    artifact_id: raw.artifact_id ? String(raw.artifact_id) : null,
    approval_id: raw.approval_id ? String(raw.approval_id) : null,
    review_approval: typeof raw.review_approval === "object" && raw.review_approval !== null ? raw.review_approval as Record<string, unknown> : null,
    markdown: raw.markdown ? String(raw.markdown) : undefined,
    content_hash: raw.content_hash ? String(raw.content_hash) : undefined,
    package_count: raw.package_count === undefined ? undefined : numberValue(raw.package_count, 0),
    packages: asArray<CommanderWorkPackageReadbackPayload["work_packages"][number]>(raw.packages),
    evidence_totals: numberRecord(raw.evidence_totals),
    safety: {
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      artifact_created: boolValue(safetyRaw.artifact_created),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function promoteCommanderSynthesis(input: {
  artifact_id: string;
  approval_id?: string;
  mode?: "memory" | "delivery" | "both";
  confirm_promote?: boolean;
  project_id?: string;
  memory_id?: string;
  delivery_artifact_id?: string;
}): Promise<CommanderSynthesisPromotionPayload> {
  const raw = await apiJsonWithStatuses<Record<string, unknown>>("/commander/work-packages/synthesis/promote", {
    method: "POST",
    body: JSON.stringify({
      artifact_id: input.artifact_id,
      approval_id: input.approval_id,
      mode: input.mode || "both",
      confirm_promote: Boolean(input.confirm_promote),
      project_id: input.project_id,
      memory_id: input.memory_id,
      delivery_artifact_id: input.delivery_artifact_id,
    }),
  }, [409]);
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-commander"),
    operation: String(raw.operation || "work_package_synthesis_promote"),
    ok: boolValue(raw.ok),
    status: String(raw.status || "unknown"),
    workspace_id: String(raw.workspace_id || "local-demo"),
    artifact_id: String(raw.artifact_id || input.artifact_id),
    approval_id: raw.approval_id ? String(raw.approval_id) : null,
    approval_decision: raw.approval_decision ? String(raw.approval_decision) : undefined,
    mode: String(raw.mode || input.mode || "both"),
    memory_id: raw.memory_id ? String(raw.memory_id) : null,
    delivery_artifact_id: raw.delivery_artifact_id ? String(raw.delivery_artifact_id) : null,
    created: typeof raw.created === "object" && raw.created !== null ? raw.created as Record<string, unknown> : undefined,
    safety: {
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
      raw_response_omitted: boolValue(safetyRaw.raw_response_omitted),
      memory_candidate_created: safetyRaw.memory_candidate_created === undefined ? undefined : boolValue(safetyRaw.memory_candidate_created),
      customer_delivery_artifact_created: safetyRaw.customer_delivery_artifact_created === undefined ? undefined : boolValue(safetyRaw.customer_delivery_artifact_created),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function closeExecutionEvidenceGap(input: {
  run_id: string;
  decision?: "accepted_remediation" | "waived" | "reopen";
  reason?: string;
  note?: string;
  synthesis_artifact_id?: string;
  remediation_task_id?: string;
  confirm_close?: boolean;
}): Promise<ExecutionEvidenceGapDecisionPayload> {
  const raw = await apiJsonWithStatuses<Record<string, unknown>>("/operator/execution-evidence/close-gap", {
    method: "POST",
    body: JSON.stringify({
      run_id: input.run_id,
      decision: input.decision || "accepted_remediation",
      reason: input.reason,
      note: input.note,
      synthesis_artifact_id: input.synthesis_artifact_id,
      remediation_task_id: input.remediation_task_id,
      confirm_close: Boolean(input.confirm_close),
    }),
  }, [400, 409]);
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: raw.provider ? String(raw.provider) : undefined,
    operation: raw.operation ? String(raw.operation) : undefined,
    ok: raw.ok === undefined ? undefined : boolValue(raw.ok),
    status: String(raw.status || raw.error || "unknown"),
    error: raw.error ? String(raw.error) : undefined,
    message: raw.message ? String(raw.message) : undefined,
    closed: raw.closed === undefined ? undefined : boolValue(raw.closed),
    workspace_id: raw.workspace_id ? String(raw.workspace_id) : undefined,
    run_id: raw.run_id ? String(raw.run_id) : input.run_id,
    decision: typeof raw.decision === "object" && raw.decision !== null ? raw.decision as Record<string, unknown> : undefined,
    gap: typeof raw.gap === "object" && raw.gap !== null ? raw.gap as Record<string, unknown> : null,
    next_actions: asArray(raw.next_actions).map(String),
    recommended_action: raw.recommended_action ? String(raw.recommended_action) : undefined,
    safety: {
      read_only: safetyRaw.read_only === undefined ? undefined : boolValue(safetyRaw.read_only),
      ledger_mutated: safetyRaw.ledger_mutated === undefined ? undefined : boolValue(safetyRaw.ledger_mutated),
      live_execution_performed: safetyRaw.live_execution_performed === undefined ? undefined : boolValue(safetyRaw.live_execution_performed),
      raw_note_omitted: safetyRaw.raw_note_omitted === undefined ? undefined : boolValue(safetyRaw.raw_note_omitted),
      raw_prompt_omitted: safetyRaw.raw_prompt_omitted === undefined ? undefined : boolValue(safetyRaw.raw_prompt_omitted),
      raw_response_omitted: safetyRaw.raw_response_omitted === undefined ? undefined : boolValue(safetyRaw.raw_response_omitted),
      token_omitted: safetyRaw.token_omitted === undefined ? undefined : boolValue(safetyRaw.token_omitted),
    },
    token_omitted: raw.token_omitted === undefined ? undefined : boolValue(raw.token_omitted),
    live_execution_performed: raw.live_execution_performed === undefined ? undefined : boolValue(raw.live_execution_performed),
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
      evaluation_case_candidates: numberValue(summaryRaw.evaluation_case_candidates, 0),
      failed_evaluation_case_runs: numberValue(summaryRaw.failed_evaluation_case_runs, 0),
      ready_deliveries: numberValue(summaryRaw.ready_deliveries, 0),
      waiting_deliveries: numberValue(summaryRaw.waiting_deliveries, 0),
      needs_attention_deliveries: numberValue(summaryRaw.needs_attention_deliveries, 0),
      commander_synthesis_pending_reviews: numberValue(summaryRaw.commander_synthesis_pending_reviews, 0),
      commander_synthesis_promotion_available: numberValue(summaryRaw.commander_synthesis_promotion_available, 0),
      commander_synthesis_memory_reviews: numberValue(summaryRaw.commander_synthesis_memory_reviews, 0),
      review_items_total: numberValue(summaryRaw.review_items_total, 0),
      returned_items: numberValue(summaryRaw.returned_items, 0),
      retrieved_pending_approvals: numberValue(summaryRaw.retrieved_pending_approvals, 0),
      retrieved_memory_candidates: numberValue(summaryRaw.retrieved_memory_candidates, 0),
      retrieved_evaluation_case_candidates: numberValue(summaryRaw.retrieved_evaluation_case_candidates, 0),
      retrieved_failed_evaluation_case_runs: numberValue(summaryRaw.retrieved_failed_evaluation_case_runs, 0),
    },
    review_items: asArray<Record<string, unknown>>(raw.review_items).map((item) => ({
      item_type: String(item.item_type || "review_item"),
      item_id: String(item.item_id || item.approval_id || item.memory_id || item.artifact_id || ""),
      status: String(item.status || "unknown"),
      review_status: item.review_status ? String(item.review_status) : undefined,
      kind: item.kind ? String(item.kind) : null,
      title: String(item.title || item.item_id || "Review item"),
      summary: item.summary ? String(item.summary) : undefined,
      task_id: item.task_id ? String(item.task_id) : null,
      run_id: item.run_id ? String(item.run_id) : null,
      agent_id: item.agent_id ? String(item.agent_id) : null,
      artifact_id: item.artifact_id ? String(item.artifact_id) : null,
      created_at: item.created_at ? String(item.created_at) : undefined,
      updated_at: item.updated_at ? String(item.updated_at) : undefined,
      priority: numberValue(item.priority, 0),
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

function normalizeExecutionEvidenceGaps(rawValue: unknown): ExecutionEvidenceGapsPayload {
  const raw = typeof rawValue === "object" && rawValue !== null ? rawValue as Record<string, unknown> : {};
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: raw.provider ? String(raw.provider) : undefined,
    operation: raw.operation ? String(raw.operation) : undefined,
    status: raw.status ? String(raw.status) : undefined,
    workspace_id: raw.workspace_id ? String(raw.workspace_id) : undefined,
    summary: numberRecord(summaryRaw),
    gaps: asArray<Record<string, unknown>>(raw.gaps).map((item) => ({
      run_id: String(item.run_id || ""),
      task_id: item.task_id ? String(item.task_id) : null,
      agent_id: item.agent_id ? String(item.agent_id) : null,
      task_title: item.task_title ? String(item.task_title) : undefined,
      run_status: item.run_status ? String(item.run_status) : undefined,
      task_status: item.task_status ? String(item.task_status) : null,
      remediation_task_id: item.remediation_task_id ? String(item.remediation_task_id) : null,
      remediation_status: item.remediation_status ? String(item.remediation_status) : null,
      remediation_synthesis_status: item.remediation_synthesis_status ? String(item.remediation_synthesis_status) : null,
      remediation_synthesis_artifact_id: item.remediation_synthesis_artifact_id ? String(item.remediation_synthesis_artifact_id) : null,
      remediation_synthesis_approval_id: item.remediation_synthesis_approval_id ? String(item.remediation_synthesis_approval_id) : null,
      gap_decision_status: item.gap_decision_status ? String(item.gap_decision_status) : null,
      gap_decision_type: item.gap_decision_type ? String(item.gap_decision_type) : null,
      gap_decision: typeof item.gap_decision === "object" && item.gap_decision !== null ? item.gap_decision as Record<string, unknown> : null,
      gap_types: asArray<unknown>(item.gap_types).map(String),
      missing_evidence: asArray<unknown>(item.missing_evidence).map(String),
      severity: String(item.severity || "attention"),
      priority: numberValue(item.priority, 0),
      command: String(item.command || ""),
      next_action: item.next_action ? String(item.next_action) : undefined,
      ui_route: item.ui_route ? String(item.ui_route) : null,
      token_omitted: item.token_omitted === undefined ? undefined : boolValue(item.token_omitted),
    })).filter((item) => item.run_id),
    next_actions: asArray<unknown>(raw.next_actions).map(String).filter(Boolean),
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
    },
    token_omitted: raw.token_omitted === undefined ? undefined : boolValue(raw.token_omitted),
  };
}

function normalizeTaskIntakeChecklist(rawValue: unknown): TaskIntakeChecklistPayload {
  const raw = typeof rawValue === "object" && rawValue !== null ? rawValue as Record<string, unknown> : {};
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: raw.provider ? String(raw.provider) : undefined,
    operation: raw.operation ? String(raw.operation) : undefined,
    status: raw.status ? String(raw.status) : undefined,
    workspace_id: raw.workspace_id ? String(raw.workspace_id) : undefined,
    summary: numberRecord(summaryRaw),
    items: asArray<Record<string, unknown>>(raw.items).map((item) => ({
      task_id: String(item.task_id || ""),
      title: String(item.title || item.task_id || "Task intake"),
      status: String(item.status || "planned"),
      priority: item.priority ? String(item.priority) : undefined,
      risk_level: item.risk_level ? String(item.risk_level) : undefined,
      assigned_agent_ids: asArray<unknown>(item.assigned_agent_ids).map(String),
      plan_id: item.plan_id ? String(item.plan_id) : null,
      plan_status: item.plan_status ? String(item.plan_status) : null,
      plan_verified: boolValue(item.plan_verified),
      plan_verified_at: item.plan_verified_at ? String(item.plan_verified_at) : null,
      referenced_specs: numberValue(item.referenced_specs, 0),
      referenced_memories: numberValue(item.referenced_memories, 0),
      referenced_bases: numberValue(item.referenced_bases, 0),
      gates: asArray<Record<string, unknown>>(item.gates).map((gate) => ({
        id: String(gate.id || ""),
        ok: boolValue(gate.ok),
        status: String(gate.status || (boolValue(gate.ok) ? "pass" : "attention")),
        message: gate.message ? String(gate.message) : undefined,
      })).filter((gate) => gate.id),
      failed_gate_ids: asArray<unknown>(item.failed_gate_ids).map(String),
      severity: String(item.severity || "attention"),
      priority_score: numberValue(item.priority_score, 0),
      command: String(item.command || ""),
      next_action: item.next_action ? String(item.next_action) : undefined,
      ui_route: item.ui_route ? String(item.ui_route) : null,
      token_omitted: item.token_omitted === undefined ? undefined : boolValue(item.token_omitted),
    })).filter((item) => item.task_id),
    next_actions: asArray<unknown>(raw.next_actions).map(String).filter(Boolean),
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      token_omitted: boolValue(safetyRaw.token_omitted),
    },
    token_omitted: raw.token_omitted === undefined ? undefined : boolValue(raw.token_omitted),
  };
}

function normalizeOperatorActionReceipt(raw: Record<string, unknown>): OperatorActionReceipt {
  return {
    receipt_id: String(raw.receipt_id || raw.audit_id || ""),
    audit_id: raw.audit_id ? String(raw.audit_id) : undefined,
    actor_id: raw.actor_id ? String(raw.actor_id) : undefined,
    workspace_id: String(raw.workspace_id || "local-demo"),
    status: String(raw.status || "recorded"),
    source: String(raw.source || "operator_action_queue"),
    action_id: raw.action_id ? String(raw.action_id) : null,
    action_signature: raw.action_signature ? String(raw.action_signature) : null,
    action_command: raw.action_command ? String(raw.action_command) : null,
    action_hash: raw.action_hash ? String(raw.action_hash) : null,
    verify_command: raw.verify_command ? String(raw.verify_command) : null,
    verify_hash: raw.verify_hash ? String(raw.verify_hash) : null,
    result_summary: raw.result_summary ? String(raw.result_summary) : null,
    created_at: raw.created_at ? String(raw.created_at) : undefined,
    tamper_chain_hash: raw.tamper_chain_hash ? String(raw.tamper_chain_hash) : undefined,
    token_omitted: raw.token_omitted === undefined ? undefined : boolValue(raw.token_omitted),
  };
}

export async function loadOperatorActionReceipts(limit = 8): Promise<OperatorActionReceiptsPayload> {
  const raw = await optionalApiJson<Record<string, unknown>>(`/operator/action-receipts?limit=${encodeURIComponent(String(limit))}`, {
    provider: "agentops-operator",
    operation: "operator_action_receipts",
    status: "unavailable",
    workspace_id: "local-demo",
    summary: {},
    receipts: [],
    safety: {
      read_only: true,
      ledger_mutated: false,
      live_execution_performed: false,
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      token_omitted: true,
    },
    token_omitted: true,
  });
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-operator"),
    operation: String(raw.operation || "operator_action_receipts"),
    status: String(raw.status || "unknown"),
    workspace_id: String(raw.workspace_id || "local-demo"),
    summary: {
      receipts: numberValue(summaryRaw.receipts, 0),
      recorded: numberValue(summaryRaw.recorded, 0),
      verified: numberValue(summaryRaw.verified, 0),
      failed: numberValue(summaryRaw.failed, 0),
      skipped: numberValue(summaryRaw.skipped, 0),
    },
    receipts: asArray<Record<string, unknown>>(raw.receipts).map(normalizeOperatorActionReceipt).filter(item => item.receipt_id),
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

export async function recordOperatorActionReceipt(input: {
  action_command: string;
  verify_command?: string;
  action_id?: string;
  action_signature?: string;
  source?: string;
  status?: "recorded" | "verified" | "failed" | "skipped";
  result_summary?: string;
}): Promise<OperatorActionReceiptResult> {
  const raw = await apiJsonWithStatuses<Record<string, unknown>>("/operator/action-receipts", {
    method: "POST",
    body: JSON.stringify({
      action_command: input.action_command,
      verify_command: input.verify_command,
      action_id: input.action_id,
      action_signature: input.action_signature,
      source: input.source,
      status: input.status || "recorded",
      result_summary: input.result_summary,
    }),
  }, [400]);
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  const receiptRaw = typeof raw.receipt === "object" && raw.receipt !== null ? raw.receipt as Record<string, unknown> : undefined;
  return {
    provider: raw.provider ? String(raw.provider) : undefined,
    operation: raw.operation ? String(raw.operation) : undefined,
    status: String(raw.status || raw.error || input.status || "recorded"),
    workspace_id: raw.workspace_id ? String(raw.workspace_id) : undefined,
    receipt: receiptRaw ? normalizeOperatorActionReceipt(receiptRaw) : undefined,
    next_actions: asArray<unknown>(raw.next_actions).map(String).filter(Boolean),
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
      raw_response_omitted: boolValue(safetyRaw.raw_response_omitted),
      token_omitted: boolValue(safetyRaw.token_omitted),
    },
    token_omitted: raw.token_omitted === undefined ? undefined : boolValue(raw.token_omitted),
  };
}

export async function loadOperatorActionPlan(limit = 12): Promise<OperatorActionPlanPayload> {
  const raw = await optionalApiJson<Record<string, unknown>>(`/operator/action-plan?limit=${encodeURIComponent(String(limit))}`, {
    provider: "agentops-operator",
    operation: "action_plan",
    status: "unavailable",
    workspace_id: "local-demo",
    summary: {},
    actions: [],
    top_commands: [],
    source_status: {},
    safety: {
      read_only: true,
      ledger_mutated: false,
      live_execution_performed: false,
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      token_omitted: true,
    },
    token_omitted: true,
    live_execution_performed: false,
  });
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-operator"),
    operation: String(raw.operation || "action_plan"),
    status: String(raw.status || "unknown"),
    workspace_id: String(raw.workspace_id || "local-demo"),
    summary: {
      actions: numberValue(summaryRaw.actions, 0),
      blocked: numberValue(summaryRaw.blocked, 0),
      attention: numberValue(summaryRaw.attention, 0),
      ready: numberValue(summaryRaw.ready, 0),
      review_items_total: numberValue(summaryRaw.review_items_total, 0),
      failed_evaluation_case_runs: numberValue(summaryRaw.failed_evaluation_case_runs, 0),
      waiting_deliveries: numberValue(summaryRaw.waiting_deliveries, 0),
      needs_attention_deliveries: numberValue(summaryRaw.needs_attention_deliveries, 0),
      stuck_worker_tasks: numberValue(summaryRaw.stuck_worker_tasks, 0),
      stuck_workflow_jobs: numberValue(summaryRaw.stuck_workflow_jobs, 0),
      recommended_adapter: String(summaryRaw.recommended_adapter || "mock"),
      remediation_packages: numberValue(summaryRaw.remediation_packages, 0),
      remediation_ready_for_review: numberValue(summaryRaw.remediation_ready_for_review, 0),
      remediation_pending_reviews: numberValue(summaryRaw.remediation_pending_reviews, 0),
      remediation_promoted_memories: numberValue(summaryRaw.remediation_promoted_memories, 0),
      remediation_promoted_deliveries: numberValue(summaryRaw.remediation_promoted_deliveries, 0),
      evidence_gap_runs: numberValue(summaryRaw.evidence_gap_runs, 0),
      missing_plan_runs: numberValue(summaryRaw.missing_plan_runs, 0),
      missing_plan_evidence_manifests: numberValue(summaryRaw.missing_plan_evidence_manifests, 0),
      unverified_plan_evidence_manifests: numberValue(summaryRaw.unverified_plan_evidence_manifests, 0),
      remediated_evidence_gap_runs: numberValue(summaryRaw.remediated_evidence_gap_runs, 0),
      blocked_evidence_gap_runs: numberValue(summaryRaw.blocked_evidence_gap_runs, 0),
      evidence_synthesis_ready_runs: numberValue(summaryRaw.evidence_synthesis_ready_runs, 0),
      evidence_synthesis_pending_runs: numberValue(summaryRaw.evidence_synthesis_pending_runs, 0),
      evidence_synthesis_promoted_runs: numberValue(summaryRaw.evidence_synthesis_promoted_runs, 0),
      evidence_gap_closure_ready_runs: numberValue(summaryRaw.evidence_gap_closure_ready_runs, 0),
      closed_evidence_gap_runs: numberValue(summaryRaw.closed_evidence_gap_runs, 0),
      waived_evidence_gap_runs: numberValue(summaryRaw.waived_evidence_gap_runs, 0),
      task_intake_checked: numberValue(summaryRaw.task_intake_checked, 0),
      task_intake_ready: numberValue(summaryRaw.task_intake_ready, 0),
      task_intake_blocked: numberValue(summaryRaw.task_intake_blocked, 0),
      task_intake_attention: numberValue(summaryRaw.task_intake_attention, 0),
      task_intake_missing_agent_plan: numberValue(summaryRaw.task_intake_missing_agent_plan, 0),
      dispatch_evidence_proofs: numberValue(summaryRaw.dispatch_evidence_proofs, 0),
      dispatch_evidence_ready: numberValue(summaryRaw.dispatch_evidence_ready, 0),
      dispatch_evidence_waiting_approval: numberValue(summaryRaw.dispatch_evidence_waiting_approval, 0),
      dispatch_evidence_verified_manifests: numberValue(summaryRaw.dispatch_evidence_verified_manifests, 0),
      action_receipts: numberValue(summaryRaw.action_receipts, 0),
      action_receipts_recorded: numberValue(summaryRaw.action_receipts_recorded, 0),
      action_receipts_verified: numberValue(summaryRaw.action_receipts_verified, 0),
      action_receipts_failed: numberValue(summaryRaw.action_receipts_failed, 0),
      receipt_required_actions: numberValue(summaryRaw.receipt_required_actions, 0),
      receipt_verified_actions: numberValue(summaryRaw.receipt_verified_actions, 0),
      receipt_missing_verified_actions: numberValue(summaryRaw.receipt_missing_verified_actions, 0),
      receipt_stale_actions: numberValue(summaryRaw.receipt_stale_actions, 0),
    },
    actions: asArray<Record<string, unknown>>(raw.actions).map((item) => ({
      action_id: String(item.action_id || item.command || item.title || ""),
      action_signature: item.action_signature ? String(item.action_signature) : null,
      lane: String(item.lane || "operator"),
      severity: String(item.severity || "attention"),
      priority: numberValue(item.priority, 0),
      base_priority: numberValue(item.base_priority, numberValue(item.priority, 0)),
      receipt_priority_boost: numberValue(item.receipt_priority_boost, 0),
      title: String(item.title || item.command || "Operator action"),
      summary: item.summary ? String(item.summary) : undefined,
      command: String(item.command || ""),
      verify_command: item.verify_command ? String(item.verify_command) : null,
      ui_route: item.ui_route ? String(item.ui_route) : null,
      source: String(item.source || "operator"),
      evidence: typeof item.evidence === "object" && item.evidence !== null ? item.evidence as Record<string, unknown> : undefined,
      receipt_required: boolValue(item.receipt_required),
      receipt_status: String(item.receipt_status || "missing"),
      receipt_underlying_status: item.receipt_underlying_status ? String(item.receipt_underlying_status) : undefined,
      receipt_match: item.receipt_match ? String(item.receipt_match) : undefined,
      receipt_current: item.receipt_current === undefined ? undefined : boolValue(item.receipt_current),
      receipt_verified: boolValue(item.receipt_verified),
      receipt_id: item.receipt_id ? String(item.receipt_id) : null,
      receipt_hash: item.receipt_hash ? String(item.receipt_hash) : null,
      receipt_state: typeof item.receipt_state === "object" && item.receipt_state !== null ? item.receipt_state as Record<string, unknown> : undefined,
    })).filter((item) => item.command),
    top_commands: asArray<unknown>(raw.top_commands).map(String).filter(Boolean),
    source_status: typeof raw.source_status === "object" && raw.source_status !== null ? raw.source_status as Record<string, string | undefined> : {},
    execution_evidence: normalizeExecutionEvidenceGaps(raw.execution_evidence),
    task_intake: normalizeTaskIntakeChecklist(raw.task_intake),
    dispatch_evidence: typeof raw.dispatch_evidence === "object" && raw.dispatch_evidence !== null ? raw.dispatch_evidence as Record<string, unknown> : undefined,
    action_receipts: typeof raw.action_receipts === "object" && raw.action_receipts !== null ? {
      ...(raw.action_receipts as OperatorActionReceiptsPayload),
      receipts: asArray<Record<string, unknown>>((raw.action_receipts as Record<string, unknown>).receipts).map(normalizeOperatorActionReceipt).filter(item => item.receipt_id),
    } : undefined,
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
      raw_response_omitted: boolValue(safetyRaw.raw_response_omitted),
      token_omitted: boolValue(safetyRaw.token_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
  };
}

export async function loadOperatorLoopAudit(limit = 12, loopId = ""): Promise<OperatorLoopAuditPayload> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (loopId) params.set("loop_id", loopId);
  const raw = await optionalApiJson<Record<string, unknown>>(`/operator/loop-audit?${params.toString()}`, {
    provider: "agentops-operator",
    operation: "loop_audit",
    status: "unavailable",
    workspace_id: "local-demo",
    loop_id: loopId || null,
    method: "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD",
    summary: {},
    steps: [],
    next_actions: [],
    source_status: {},
    safety: {
      read_only: true,
      ledger_mutated: false,
      live_execution_performed: false,
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      token_omitted: true,
    },
    token_omitted: true,
    live_execution_performed: false,
  });
  const summaryRaw = typeof raw.summary === "object" && raw.summary !== null ? raw.summary as Record<string, unknown> : {};
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  const loopRecordRaw = typeof raw.loop_record === "object" && raw.loop_record !== null ? raw.loop_record as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agentops-operator"),
    operation: String(raw.operation || "loop_audit"),
    status: String(raw.status || "unknown"),
    workspace_id: String(raw.workspace_id || "local-demo"),
    loop_id: raw.loop_id ? String(raw.loop_id) : null,
    method: String(raw.method || "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD"),
    summary: {
      steps: numberValue(summaryRaw.steps, 0),
      pass: numberValue(summaryRaw.pass, 0),
      attention: numberValue(summaryRaw.attention, 0),
      blocked: numberValue(summaryRaw.blocked, 0),
      knowledge_documents: numberValue(summaryRaw.knowledge_documents, 0),
      verified_agent_plans: numberValue(summaryRaw.verified_agent_plans, 0),
      plan_bound_runs: numberValue(summaryRaw.plan_bound_runs, 0),
      verified_plan_evidence_manifests: numberValue(summaryRaw.verified_plan_evidence_manifests, 0),
      evidence_gap_runs: numberValue(summaryRaw.evidence_gap_runs, 0),
      loop_runs: numberValue(summaryRaw.loop_runs, 0),
      loop_verified_plan_evidence_manifests: numberValue(summaryRaw.loop_verified_plan_evidence_manifests, 0),
      loop_blocked_plan_evidence_manifests: numberValue(summaryRaw.loop_blocked_plan_evidence_manifests, 0),
      pending_approvals: numberValue(summaryRaw.pending_approvals, 0),
      memory_candidates: numberValue(summaryRaw.memory_candidates, 0),
      loop_memory_candidates: numberValue(summaryRaw.loop_memory_candidates, 0),
      loop_approved_memories: numberValue(summaryRaw.loop_approved_memories, 0),
      loop_pending_approvals: numberValue(summaryRaw.loop_pending_approvals, 0),
      audit_logs: numberValue(summaryRaw.audit_logs, 0),
    },
    steps: asArray<Record<string, unknown>>(raw.steps).map((step) => ({
      id: String(step.id || ""),
      label: String(step.label || step.id || ""),
      status: String(step.status || "attention"),
      message: step.message ? String(step.message) : undefined,
      evidence: typeof step.evidence === "object" && step.evidence !== null ? step.evidence as Record<string, unknown> : {},
      command: String(step.command || ""),
      source: String(step.source || ""),
      token_omitted: step.token_omitted === undefined ? undefined : boolValue(step.token_omitted),
    })).filter((step) => step.id),
    next_actions: asArray<unknown>(raw.next_actions).map(String).filter(Boolean),
    source_status: typeof raw.source_status === "object" && raw.source_status !== null ? raw.source_status as Record<string, string | undefined> : {},
    sources: typeof raw.sources === "object" && raw.sources !== null ? raw.sources as Record<string, unknown> : undefined,
    loop_record: {
      status: String(loopRecordRaw.status || (loopId ? "unknown" : "unscoped")),
      loop_id: loopRecordRaw.loop_id ? String(loopRecordRaw.loop_id) : null,
      memory_reviews: asArray<Record<string, unknown>>(loopRecordRaw.memory_reviews).map((item) => ({
        memory_id: String(item.memory_id || ""),
        scope: item.scope ? String(item.scope) : undefined,
        memory_type: item.memory_type ? String(item.memory_type) : undefined,
        review_status: String(item.review_status || "candidate"),
        source_type: item.source_type ? String(item.source_type) : undefined,
        source_ref: item.source_ref ? String(item.source_ref) : null,
        task_id: item.task_id ? String(item.task_id) : null,
        agent_id: item.agent_id ? String(item.agent_id) : null,
        confidence: item.confidence === undefined || item.confidence === null ? undefined : numberValue(item.confidence, 0),
        summary: item.summary ? String(item.summary) : undefined,
        created_at: item.created_at ? String(item.created_at) : null,
        updated_at: item.updated_at ? String(item.updated_at) : null,
        approve_command: item.approve_command ? String(item.approve_command) : undefined,
        reject_command: item.reject_command ? String(item.reject_command) : undefined,
        token_omitted: item.token_omitted === undefined ? undefined : boolValue(item.token_omitted),
      })).filter((item) => item.memory_id),
      approval_reviews: asArray<Record<string, unknown>>(loopRecordRaw.approval_reviews).map((item) => ({
        approval_id: String(item.approval_id || ""),
        task_id: item.task_id ? String(item.task_id) : null,
        run_id: item.run_id ? String(item.run_id) : null,
        tool_call_id: item.tool_call_id ? String(item.tool_call_id) : null,
        requested_by_agent_id: item.requested_by_agent_id ? String(item.requested_by_agent_id) : null,
        decision: String(item.decision || "pending"),
        reason: item.reason ? String(item.reason) : undefined,
        created_at: item.created_at ? String(item.created_at) : null,
        decided_at: item.decided_at ? String(item.decided_at) : null,
        approve_command: item.approve_command ? String(item.approve_command) : undefined,
        reject_command: item.reject_command ? String(item.reject_command) : undefined,
        token_omitted: item.token_omitted === undefined ? undefined : boolValue(item.token_omitted),
      })).filter((item) => item.approval_id),
      candidate_count: numberValue(loopRecordRaw.candidate_count, 0),
      approved_count: numberValue(loopRecordRaw.approved_count, 0),
      pending_approval_count: numberValue(loopRecordRaw.pending_approval_count, 0),
      audit_count: numberValue(loopRecordRaw.audit_count, 0),
      audit_trail: asArray<Record<string, unknown>>(loopRecordRaw.audit_trail).map((item) => ({
        audit_id: String(item.audit_id || ""),
        actor_type: item.actor_type ? String(item.actor_type) : null,
        actor_id: item.actor_id ? String(item.actor_id) : null,
        action: String(item.action || ""),
        entity_type: String(item.entity_type || ""),
        entity_id: String(item.entity_id || ""),
        before_hash: item.before_hash ? String(item.before_hash) : null,
        after_hash: item.after_hash ? String(item.after_hash) : null,
        tamper_chain_hash: item.tamper_chain_hash ? String(item.tamper_chain_hash) : null,
        created_at: item.created_at ? String(item.created_at) : null,
        token_omitted: item.token_omitted === undefined ? undefined : boolValue(item.token_omitted),
      })).filter((item) => item.audit_id),
      next_action: loopRecordRaw.next_action ? String(loopRecordRaw.next_action) : undefined,
      review_queue_command: loopRecordRaw.review_queue_command ? String(loopRecordRaw.review_queue_command) : undefined,
      token_omitted: loopRecordRaw.token_omitted === undefined ? undefined : boolValue(loopRecordRaw.token_omitted),
    },
    loop_readback: typeof raw.loop_readback === "object" && raw.loop_readback !== null ? raw.loop_readback as Record<string, unknown> : undefined,
    safety: {
      read_only: boolValue(safetyRaw.read_only),
      ledger_mutated: boolValue(safetyRaw.ledger_mutated),
      live_execution_performed: boolValue(safetyRaw.live_execution_performed),
      raw_prompt_omitted: boolValue(safetyRaw.raw_prompt_omitted),
      raw_response_omitted: boolValue(safetyRaw.raw_response_omitted),
      token_omitted: boolValue(safetyRaw.token_omitted),
    },
    token_omitted: boolValue(raw.token_omitted),
    live_execution_performed: boolValue(raw.live_execution_performed),
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
      observation_level: item.observation_level ? String(item.observation_level) : undefined,
      capability_policy_hash: item.capability_policy_hash ? String(item.capability_policy_hash) : null,
      capability_manifest: typeof item.capability_manifest === "object" && item.capability_manifest !== null ? item.capability_manifest as Record<string, unknown> : {},
      risk_floor: item.risk_floor ? String(item.risk_floor) : undefined,
      commercial_readiness: item.commercial_readiness ? String(item.commercial_readiness) : undefined,
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
  return apiJsonWithStatuses<WorkerDaemonResult>("/workers/local/start", {
    method: "POST",
    body: JSON.stringify(input),
  }, [200, 201, 409]);
}

export async function stopLocalWorkerDaemon(adapter?: "mock" | "hermes" | "openclaw" | "all"): Promise<WorkerDaemonResult> {
  return apiJson<WorkerDaemonResult>("/workers/local/stop", {
    method: "POST",
    body: JSON.stringify({ adapter: adapter || "all" }),
  });
}

export async function restartLocalWorkerDaemon(input: {
  adapter: "mock" | "hermes" | "openclaw";
  confirm_run?: boolean;
  poll_interval?: number;
  max_tasks?: number;
}): Promise<WorkerDaemonResult> {
  return apiJsonWithStatuses<WorkerDaemonResult>("/workers/local/restart", {
    method: "POST",
    body: JSON.stringify(input),
  }, [200, 201, 409]);
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

export async function previewAgentGatewayEnrollmentPolicy(input: {
  workspace_id?: string;
  runtime_type?: string;
  scopes: string[];
}): Promise<AgentGatewayEnrollmentPolicyPreview> {
  const raw = await apiJson<Record<string, unknown>>("/agent-gateway/enrollment/policy-preview", {
    method: "POST",
    body: JSON.stringify(input),
  });
  const safetyRaw = typeof raw.safety === "object" && raw.safety !== null ? raw.safety as Record<string, unknown> : {};
  return {
    provider: String(raw.provider || "agent_gateway"),
    operation: String(raw.operation || "enrollment_policy_preview"),
    status: String(raw.status || "unknown"),
    workspace_id: String(raw.workspace_id || ""),
    runtime_type: String(raw.runtime_type || ""),
    policy: String(raw.policy || "custom"),
    risk_level: String(raw.risk_level || "unknown"),
    approval_recommended: boolValue(raw.approval_recommended),
    recommended_path: String(raw.recommended_path || ""),
    scope_count: numberValue(raw.scope_count, 0),
    scopes: asArray(raw.scopes).map(String),
    invalid_scopes: asArray(raw.invalid_scopes).map(String),
    privileged_scopes: asArray(raw.privileged_scopes).map(String),
    worker_write_scopes: asArray(raw.worker_write_scopes).map(String),
    missing_worker_scopes: asArray(raw.missing_worker_scopes).map(String),
    gates: asArray<Record<string, unknown>>(raw.gates).map((gate) => ({
      id: String(gate.id || ""),
      ok: boolValue(gate.ok),
      status: String(gate.status || "unknown"),
      summary: String(gate.summary || ""),
    })).filter((gate) => gate.id || gate.summary),
    next_actions: asArray(raw.next_actions).map(String).filter(Boolean),
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
