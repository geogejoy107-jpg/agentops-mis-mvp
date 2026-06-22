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
