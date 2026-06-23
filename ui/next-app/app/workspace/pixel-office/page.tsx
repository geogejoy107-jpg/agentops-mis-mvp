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

type SearchParams = Record<string, string | string[] | undefined>;
type PageProps = {
  searchParams?: Promise<SearchParams>;
};

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function PixelOfficePage({ searchParams }: PageProps) {
  const [metrics, agents, tasks, runs, approvals, memories, audit, params] = await Promise.all([
    loadServerDashboardMetrics(),
    loadServerAgents(),
    loadServerTasks(),
    loadServerRuns(),
    loadServerApprovals(),
    loadServerMemories(),
    loadServerAudit(40),
    searchParams || Promise.resolve({} as SearchParams),
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
      feedback={{
        localBriefStatus: one(params.local_brief_status),
        localBriefError: one(params.local_brief_error),
        localBriefPromptHash: one(params.local_brief_prompt_hash),
        localBriefStateHash: one(params.local_brief_state_hash),
        localBriefAgentsTotal: one(params.local_brief_agents_total),
        localBriefPendingApprovals: one(params.local_brief_pending_approvals),
        localBriefRecentRealRuns: one(params.local_brief_recent_real_runs),
      }}
    />
  );
}
