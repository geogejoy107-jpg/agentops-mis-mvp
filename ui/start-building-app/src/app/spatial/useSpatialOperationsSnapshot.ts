import { useEffect, useMemo, useState } from "react";
import {
  loadAgents,
  loadApprovals,
  loadAudit,
  loadDashboard,
  loadMemories,
  loadRuns,
  loadTasks,
  type DashboardMetrics,
} from "../data/liveApi";
import {
  agents as mockAgents,
  approvals as mockApprovals,
  auditLogs as mockAudit,
  memories as mockMemories,
  runtimeConnectors as mockRuntimeConnectors,
  runs as mockRuns,
  tasks as mockTasks,
  type Agent,
  type Approval,
  type AuditLog,
  type Memory,
  type Run,
  type Task,
} from "../data/mockData";
import { derivePixelAgents, derivePixelMetrics, deriveTaskCards } from "../components/pixel/pixelModel";

interface SpatialOperationsSnapshot {
  metrics: DashboardMetrics;
  agents: Agent[];
  tasks: Task[];
  approvals: Approval[];
  runs: Run[];
  memories: Memory[];
  audit: AuditLog[];
}

function buildFallbackMetrics(): DashboardMetrics {
  const completedTasks = mockTasks.filter((task) => task.status === "completed").length;
  const failedRuns = mockRuns.filter((run) => ["failed", "error", "blocked", "timeout"].includes(run.status)).length;
  const pendingApprovals = mockApprovals.filter((approval) => approval.decision === "pending").length;
  const totalCost = mockRuns.reduce((sum, run) => sum + (Number.isFinite(run.cost_usd) ? run.cost_usd : 0), 0);
  const statusCounts = mockTasks.reduce<Record<string, number>>((acc, task) => {
    acc[task.status] = (acc[task.status] || 0) + 1;
    return acc;
  }, {});

  return {
    agents_total: mockAgents.length,
    agents_running: mockAgents.filter((agent) => agent.status === "running").length,
    tasks_completed_total: completedTasks,
    total_cost_usd: totalCost,
    avg_task_cost_usd: mockTasks.length ? totalCost / mockTasks.length : 0,
    failure_rate: mockRuns.length ? failedRuns / mockRuns.length : 0,
    pending_approvals: pendingApprovals,
    stale_or_due_memories: mockMemories.filter((memory) => ["candidate", "stale"].includes(memory.review_status)).length,
    task_status_distribution: Object.entries(statusCounts).map(([status, count]) => ({ status, count })),
    top_cost_agents: mockAgents.slice(0, 3).map((agent) => ({
      agent_id: agent.agent_id,
      name: agent.name,
      cost_usd: agent.budget_used_usd,
    })),
    top_failing_agents: mockAgents.slice(0, 3).map((agent) => ({
      agent_id: agent.agent_id,
      name: agent.name,
      failures: agent.failure_count,
    })),
    runtime_health: mockRuntimeConnectors.map((connector) => ({
      provider: connector.provider,
      status: connector.status,
      mode: connector.mode,
      last_checked: connector.last_checked,
    })),
    openclaw_import: {
      agents: mockAgents.filter((agent) => agent.runtime_type === "openclaw").length,
      cron_tasks: mockTasks.length,
      enabled_cron_tasks: mockTasks.filter((task) => task.status !== "completed").length,
      cron_runs: mockRuns.length,
      failed_runs: failedRuns,
      failed_quality_gates: failedRuns,
    },
    agent_performance_summary: mockAgents.map((agent) => ({
      agent_id: agent.agent_id,
      name: agent.name,
      runtime_type: agent.runtime_type,
      total_runs: agent.run_count,
      success_rate: agent.success_rate,
      avg_duration_ms: 0,
      total_cost_usd: agent.budget_used_usd,
      failures: agent.failure_count,
      approval_required_count: agent.approval_count,
    })),
    recent_runs: mockRuns.slice(0, 5),
  };
}

const FALLBACK_SNAPSHOT: SpatialOperationsSnapshot = {
  metrics: buildFallbackMetrics(),
  agents: mockAgents,
  tasks: mockTasks,
  approvals: mockApprovals,
  runs: mockRuns,
  memories: mockMemories,
  audit: mockAudit,
};

function readSettled<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

export function useSpatialOperationsSnapshot() {
  const [snapshot, setSnapshot] = useState<SpatialOperationsSnapshot>(FALLBACK_SNAPSHOT);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const metrics = await loadDashboard();
      const [agentsResult, tasksResult, approvalsResult, runsResult, memoriesResult, auditResult] = await Promise.allSettled([
        loadAgents(metrics),
        loadTasks(),
        loadApprovals(),
        loadRuns(),
        loadMemories(),
        loadAudit(),
      ]);
      setSnapshot({
        metrics,
        agents: readSettled(agentsResult, FALLBACK_SNAPSHOT.agents),
        tasks: readSettled(tasksResult, FALLBACK_SNAPSHOT.tasks),
        approvals: readSettled(approvalsResult, FALLBACK_SNAPSHOT.approvals),
        runs: readSettled(runsResult, FALLBACK_SNAPSHOT.runs),
        memories: readSettled(memoriesResult, FALLBACK_SNAPSHOT.memories),
        audit: readSettled(auditResult, FALLBACK_SNAPSHOT.audit),
      });
    } catch (reason) {
      setSnapshot(FALLBACK_SNAPSHOT);
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const metrics = useMemo(
    () => derivePixelMetrics({
      metrics: snapshot.metrics,
      tasks: snapshot.tasks,
      approvals: snapshot.approvals,
      runs: snapshot.runs,
      memories: snapshot.memories,
      audit: snapshot.audit,
    }),
    [snapshot],
  );

  const agents = useMemo(
    () => derivePixelAgents({
      agents: snapshot.agents,
      tasks: snapshot.tasks,
      approvals: snapshot.approvals,
      runs: snapshot.runs,
      memories: snapshot.memories,
    }),
    [snapshot],
  );

  const taskCards = useMemo(() => deriveTaskCards(snapshot.tasks), [snapshot.tasks]);

  return {
    metrics,
    agents,
    taskCards,
    loading,
    error,
    refresh,
  };
}
