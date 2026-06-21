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
  status: string;
  priority?: string;
  risk_level?: string;
  owner_agent_id?: string | null;
};

export type RunSummary = {
  run_id: string;
  task_id?: string;
  agent_id?: string;
  runtime_type?: string;
  status: string;
  cost_usd?: number;
  started_at?: string;
};

export type ApprovalSummary = {
  approval_id: string;
  decision: string;
  task_id?: string;
  run_id?: string;
  reason?: string;
};

export type WorkspaceSnapshot = {
  metrics: DashboardMetrics;
  tasks: TaskSummary[];
  runs: RunSummary[];
  approvals: ApprovalSummary[];
};

async function misJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api/mis${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export async function loadWorkspaceSnapshot(): Promise<WorkspaceSnapshot> {
  const [metrics, tasks, runs, approvals] = await Promise.all([
    misJson<DashboardMetrics>("/dashboard/metrics"),
    misJson<TaskSummary[]>("/tasks"),
    misJson<RunSummary[]>("/runs"),
    misJson<ApprovalSummary[]>("/approvals"),
  ]);
  return {
    metrics,
    tasks: tasks.slice(0, 8),
    runs: runs.slice(0, 8),
    approvals: approvals.filter((approval) => approval.decision === "pending").slice(0, 6),
  };
}
