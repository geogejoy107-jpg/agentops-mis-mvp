import type {
  ApprovalSummary,
  AgentGatewaySessionsPayload,
  CommercialEntitlementStatus,
  CustomerDeliveryBoardPayload,
  CustomerProjectIndexPayload,
  CustomerProjectReportPayload,
  CustomerTaskTemplateListPayload,
  EvidenceDrilldownPayload,
  AgentPlanVerifyPayload,
  MemorySummary,
  PlanEvidenceVerifyPayload,
  RunGraphPayload,
  RunDetailPayload,
  RunDetailSnapshot,
  SecurityReadinessSummary,
  TaskDetailPayload,
  WorkerStatusSummary,
  AuditSummary,
} from "./mis";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

export type ServerLoadResult<T> = {
  data: T;
  error: string | null;
};

async function serverMisJson<T>(path: string): Promise<T> {
  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}${path}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export async function loadServerApprovals(): Promise<ServerLoadResult<ApprovalSummary[]>> {
  try {
    return { data: await serverMisJson<ApprovalSummary[]>("/approvals"), error: null };
  } catch (err) {
    return { data: [], error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerMemories(): Promise<ServerLoadResult<MemorySummary[]>> {
  try {
    return { data: await serverMisJson<MemorySummary[]>("/memories"), error: null };
  } catch (err) {
    return { data: [], error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerCustomerProjects(limit = 25): Promise<ServerLoadResult<CustomerProjectIndexPayload>> {
  try {
    return { data: await serverMisJson<CustomerProjectIndexPayload>(`/workflows/customer-projects?limit=${encodeURIComponent(String(limit))}`), error: null };
  } catch (err) {
    return { data: { projects: [] }, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerCustomerDeliveryBoard(limit = 12): Promise<ServerLoadResult<CustomerDeliveryBoardPayload>> {
  try {
    return { data: await serverMisJson<CustomerDeliveryBoardPayload>(`/workflows/customer-delivery-board?limit=${encodeURIComponent(String(limit))}`), error: null };
  } catch (err) {
    return { data: { deliveries: [] }, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerCustomerProjectReport(projectId: string): Promise<ServerLoadResult<CustomerProjectReportPayload | null>> {
  try {
    return { data: await serverMisJson<CustomerProjectReportPayload>(`/workflows/customer-projects/${encodeURIComponent(projectId)}/report`), error: null };
  } catch (err) {
    return { data: null, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerCommercialEntitlements(): Promise<ServerLoadResult<CommercialEntitlementStatus>> {
  try {
    return { data: await serverMisJson<CommercialEntitlementStatus>("/commercial/entitlements"), error: null };
  } catch (err) {
    return { data: {}, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerSecurityProductionReadiness(): Promise<ServerLoadResult<SecurityReadinessSummary>> {
  try {
    return { data: await serverMisJson<SecurityReadinessSummary>("/security/production-readiness"), error: null };
  } catch (err) {
    return { data: {}, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerWorkerStatus(): Promise<ServerLoadResult<WorkerStatusSummary>> {
  try {
    return { data: await serverMisJson<WorkerStatusSummary>("/workers/status"), error: null };
  } catch (err) {
    return { data: {}, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerGatewaySessions(): Promise<ServerLoadResult<AgentGatewaySessionsPayload>> {
  try {
    return { data: await serverMisJson<AgentGatewaySessionsPayload>("/agent-gateway/sessions"), error: null };
  } catch (err) {
    return { data: { sessions: [] }, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerAudit(limit = 80): Promise<ServerLoadResult<AuditSummary[]>> {
  try {
    return { data: await serverMisJson<AuditSummary[]>(`/audit?limit=${encodeURIComponent(String(limit))}`), error: null };
  } catch (err) {
    return { data: [], error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerCustomerTaskTemplates(): Promise<ServerLoadResult<CustomerTaskTemplateListPayload>> {
  try {
    return { data: await serverMisJson<CustomerTaskTemplateListPayload>("/workflows/customer-task-templates"), error: null };
  } catch (err) {
    return { data: { templates: [] }, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerEvidenceDrilldown(manifestId: string): Promise<ServerLoadResult<EvidenceDrilldownPayload>> {
  try {
    const manifest = await serverMisJson<PlanEvidenceVerifyPayload>(`/agent-gateway/plan-evidence-manifests/${encodeURIComponent(manifestId)}/verify`);
    const planId = manifest.manifest?.plan_id;
    const runId = manifest.manifest?.run_id;
    const [plan, runGraph] = await Promise.all([
      planId ? serverMisJson<AgentPlanVerifyPayload>(`/agent-gateway/agent-plans/${encodeURIComponent(planId)}/verify`) : Promise.resolve(null),
      runId ? serverMisJson<RunGraphPayload>(`/agent-gateway/runs/${encodeURIComponent(runId)}/graph`) : Promise.resolve(null),
    ]);
    return { data: { manifest, plan, runGraph }, error: null };
  } catch (err) {
    return { data: { manifest: null, plan: null, runGraph: null }, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerTaskDetail(taskId: string): Promise<ServerLoadResult<TaskDetailPayload | null>> {
  try {
    return { data: await serverMisJson<TaskDetailPayload>(`/tasks/${encodeURIComponent(taskId)}`), error: null };
  } catch (err) {
    return { data: null, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerRunDetail(runId: string): Promise<ServerLoadResult<RunDetailSnapshot>> {
  try {
    const [detail, graph] = await Promise.all([
      serverMisJson<RunDetailPayload>(`/runs/${encodeURIComponent(runId)}`),
      serverMisJson<RunGraphPayload>(`/runs/${encodeURIComponent(runId)}/graph`),
    ]);
    return { data: { detail, graph }, error: null };
  } catch (err) {
    return { data: { detail: null, graph: null }, error: err instanceof Error ? err.message : String(err) };
  }
}
