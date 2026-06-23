import { PixelOfficeParityPage } from "@/components/PixelOfficePage";
import {
  loadServerAgents,
  loadServerApprovals,
  loadServerAudit,
  loadServerDashboardMetrics,
  loadServerMemories,
  loadServerRuns,
  loadServerTasks,
} from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function PixelOfficePage() {
  const [metrics, agents, tasks, runs, approvals, memories, audit] = await Promise.all([
    loadServerDashboardMetrics(),
    loadServerAgents(),
    loadServerTasks(),
    loadServerRuns(),
    loadServerApprovals(),
    loadServerMemories(),
    loadServerAudit(40),
  ]);

  return (
    <PixelOfficeParityPage
      metrics={metrics.data}
      agents={agents.data}
      tasks={tasks.data}
      runs={runs.data}
      approvals={approvals.data}
      memories={memories.data}
      audit={audit.data}
      errors={{
        metrics: metrics.error,
        agents: agents.error,
        tasks: tasks.error,
        runs: runs.error,
        approvals: approvals.error,
        memories: memories.error,
        audit: audit.error,
      }}
    />
  );
}
