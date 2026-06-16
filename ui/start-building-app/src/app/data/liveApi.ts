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

export interface CustomerTaskWorkflowResult {
  provider: string;
  workflow: string;
  dry_run: boolean;
  ok?: boolean;
  task_id: string;
  run_id?: string;
  artifact_id?: string | null;
  duration_ms?: number;
  output_summary?: string;
  error?: string | null;
  reason?: string;
  note?: string;
  requires?: Record<string, unknown>;
  selected_agent_ids?: string[];
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

export async function loadMemories(): Promise<Memory[]> {
  return (await apiJson<Record<string, unknown>[]>("/memories")).map(normalizeMemory);
}

export async function loadRuntimeConnectors(): Promise<RuntimeConnector[]> {
  return (await apiJson<Record<string, unknown>[]>("/runtime-connectors")).map(normalizeConnector);
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

export async function decideApproval(id: string, decision: "approve" | "reject"): Promise<{ updated: boolean }> {
  return apiJson<{ updated: boolean }>(`/approvals/${encodeURIComponent(id)}/${decision}`, {
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
