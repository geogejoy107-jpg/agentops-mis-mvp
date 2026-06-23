import {
  loadAgents,
  loadApprovals,
  loadAudit,
  loadCommanderWorkPackages,
  loadCustomerDeliveryBoard,
  loadDashboard,
  loadMemories,
  loadOperatorActionPlan,
  loadReviewQueue,
  loadRuns,
  loadTasks,
  loadWorkerFleet,
  useLiveData,
} from "../../data/liveApi";

interface SafeResult<T> {
  data: T | null;
  error: string | null;
  label: string;
}

async function safe<T>(label: string, loader: () => Promise<T>): Promise<SafeResult<T>> {
  try {
    return { data: await loader(), error: null, label };
  } catch (error) {
    return { data: null, error: error instanceof Error ? error.message : String(error), label };
  }
}

export function useMissionControlData() {
  return useLiveData(async () => {
    const [
      metricsResult,
      agentsResult,
      tasksResult,
      runsResult,
      approvalsResult,
      memoriesResult,
      auditResult,
      operatorResult,
      packagesResult,
      fleetResult,
      reviewResult,
      deliveriesResult,
    ] = await Promise.all([
      safe("dashboard", () => loadDashboard()),
      safe("agents", () => loadAgents()),
      safe("tasks", () => loadTasks()),
      safe("runs", () => loadRuns()),
      safe("approvals", () => loadApprovals()),
      safe("memories", () => loadMemories()),
      safe("audit", () => loadAudit()),
      safe("operator action plan", () => loadOperatorActionPlan(10)),
      safe("work packages", () => loadCommanderWorkPackages({ limit: 8 })),
      safe("worker fleet", () => loadWorkerFleet()),
      safe("review queue", () => loadReviewQueue(10)),
      safe("deliveries", () => loadCustomerDeliveryBoard(8)),
    ] as const);

    const all: SafeResult<unknown>[] = [metricsResult, agentsResult, tasksResult, runsResult, approvalsResult, memoriesResult, auditResult, operatorResult, packagesResult, fleetResult, reviewResult, deliveriesResult];

    return {
      metrics: metricsResult.data,
      agents: agentsResult.data || [],
      tasks: tasksResult.data || [],
      runs: runsResult.data || [],
      approvals: approvalsResult.data || [],
      memories: memoriesResult.data || [],
      audit: auditResult.data || [],
      operatorPlan: operatorResult.data,
      workPackages: packagesResult.data,
      workerFleet: fleetResult.data,
      reviewQueue: reviewResult.data,
      deliveries: deliveriesResult.data,
      partialErrors: all.filter((item) => item.error).map((item) => `${item.label}: ${item.error}`),
      checkedAt: new Date().toISOString(),
    };
  }, []);
}
