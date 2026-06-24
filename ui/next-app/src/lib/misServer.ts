import type {
  ApprovalSummary,
  AuditRetentionControlsPayload,
  AuditRetentionPolicyPayload,
  AgentGatewaySessionsPayload,
  AgentSummary,
  BasesPayload,
  CommercialEntitlementStatus,
  CommercialReleaseStatusPayload,
  CustomerDeliveryBoardPayload,
  CustomerWorkerPreparedActionListPayload,
  CustomerProjectIndexPayload,
  CustomerProjectReportPayload,
  CustomerTaskTemplateListPayload,
  DashboardMetrics,
  DeploymentReadinessPayload,
  EnterpriseControlsPayload,
  EvidenceDrilldownPayload,
  AgentPlanVerifyPayload,
  LocalReadinessPayload,
  MemorySummary,
  OperatorExecutionModePayload,
  PlanEvidenceVerifyPayload,
  RunGraphPayload,
  RunDetailPayload,
  RunDetailSnapshot,
  SecurityReadinessSummary,
  StorageBackendStatus,
  TaskDetailPayload,
  TaskSummary,
  TemplateBinding,
  TemplatePackage,
  WorkerAdapterReadinessSummary,
  WorkerFleetHygienePayload,
  WorkerFleetPayload,
  WorkerStatusSummary,
  AuditSummary,
  RunSummary,
  WorkflowJobListPayload,
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

function refTail(value: unknown) {
  return String(value || "").replace(/[^A-Za-z0-9]/g, "").slice(-12);
}

function safeGatewaySessionsPayload(payload: AgentGatewaySessionsPayload): AgentGatewaySessionsPayload {
  return {
    ...payload,
    sessions: (payload.sessions || []).map((session) => {
      const sessionTail = refTail(session.session_id || session.session_ref);
      const parentTail = refTail(session.parent_token_id || session.parent_token_ref);
      const { session_id, parent_token_id, ...rest } = session;
      void session_id;
      void parent_token_id;
      return {
        ...rest,
        session_ref: session.session_ref || (sessionTail ? `session_ref_${sessionTail}` : ""),
        session_id_omitted: true,
        parent_token_ref: session.parent_token_ref || (parentTail ? `token_ref_${parentTail}` : ""),
        parent_token_id_omitted: true,
      };
    }),
    token_omitted: true,
  };
}

export async function loadServerApprovals(): Promise<ServerLoadResult<ApprovalSummary[]>> {
  try {
    return { data: await serverMisJson<ApprovalSummary[]>("/approvals"), error: null };
  } catch (err) {
    return { data: [], error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerDashboardMetrics(): Promise<ServerLoadResult<DashboardMetrics>> {
  try {
    return { data: await serverMisJson<DashboardMetrics>("/dashboard/metrics"), error: null };
  } catch (err) {
    return { data: {}, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerAgents(): Promise<ServerLoadResult<AgentSummary[]>> {
  try {
    return { data: await serverMisJson<AgentSummary[]>("/agents"), error: null };
  } catch (err) {
    return { data: [], error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerTasks(): Promise<ServerLoadResult<TaskSummary[]>> {
  try {
    return { data: await serverMisJson<TaskSummary[]>("/tasks"), error: null };
  } catch (err) {
    return { data: [], error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerRuns(): Promise<ServerLoadResult<RunSummary[]>> {
  try {
    return { data: await serverMisJson<RunSummary[]>("/runs"), error: null };
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

export async function loadServerCommercialReleaseStatus(): Promise<ServerLoadResult<CommercialReleaseStatusPayload>> {
  try {
    return { data: await serverMisJson<CommercialReleaseStatusPayload>("/commercial/release-status"), error: null };
  } catch (err) {
    return { data: {}, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerStorageBackendStatus(): Promise<ServerLoadResult<StorageBackendStatus>> {
  try {
    return { data: await serverMisJson<StorageBackendStatus>("/storage/backend-status"), error: null };
  } catch (err) {
    return { data: {}, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerLocalReadiness(): Promise<ServerLoadResult<LocalReadinessPayload>> {
  try {
    return { data: await serverMisJson<LocalReadinessPayload>("/local/readiness"), error: null };
  } catch (err) {
    return { data: {}, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerDeploymentReadiness(): Promise<ServerLoadResult<DeploymentReadinessPayload>> {
  try {
    return { data: await serverMisJson<DeploymentReadinessPayload>("/deployment/readiness"), error: null };
  } catch (err) {
    return { data: {}, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerEnterpriseControls(): Promise<ServerLoadResult<EnterpriseControlsPayload>> {
  try {
    return { data: await serverMisJson<EnterpriseControlsPayload>("/deployment/enterprise-controls"), error: null };
  } catch (err) {
    return { data: {}, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerAuditRetentionPolicy(): Promise<ServerLoadResult<AuditRetentionPolicyPayload>> {
  try {
    return { data: await serverMisJson<AuditRetentionPolicyPayload>("/audit/retention-policy"), error: null };
  } catch (err) {
    return { data: {}, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerAuditRetentionControls(): Promise<ServerLoadResult<AuditRetentionControlsPayload>> {
  try {
    return { data: await serverMisJson<AuditRetentionControlsPayload>("/audit/retention-controls"), error: null };
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

export async function loadServerWorkerFleet(): Promise<ServerLoadResult<WorkerFleetPayload>> {
  try {
    return { data: await serverMisJson<WorkerFleetPayload>("/workers/fleet"), error: null };
  } catch (err) {
    return {
      data: {
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
      },
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function loadServerWorkerFleetHygiene(limit = 8): Promise<ServerLoadResult<WorkerFleetHygienePayload>> {
  try {
    return { data: await serverMisJson<WorkerFleetHygienePayload>(`/workers/fleet/hygiene?limit=${encodeURIComponent(String(limit))}`), error: null };
  } catch (err) {
    return {
      data: {
        provider: "agentops-worker",
        operation: "fleet_hygiene",
        status: "unavailable",
        threshold_sec: 900,
        enrollment_age_sec: 900,
        summary: { stuck_tasks: 0, stale_never_seen_enrollments: 0, actions_available: 0 },
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
      },
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function loadServerWorkerAdapterReadiness(): Promise<ServerLoadResult<WorkerAdapterReadinessSummary>> {
  try {
    return { data: await serverMisJson<WorkerAdapterReadinessSummary>("/workers/adapter-readiness"), error: null };
  } catch (err) {
    return { data: { adapters: {}, token_omitted: true, live_execution_performed: false }, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerOperatorExecutionMode(adapter?: string): Promise<ServerLoadResult<OperatorExecutionModePayload>> {
  try {
    const suffix = adapter ? `?${new URLSearchParams({ adapter }).toString()}` : "";
    return { data: await serverMisJson<OperatorExecutionModePayload>(`/operator/execution-mode${suffix}`), error: null };
  } catch (err) {
    return {
      data: {
        provider: "agentops-operator",
        operation: "execution_mode",
        status: "unavailable",
        selected_adapter: adapter || "mock",
        adapter_route: {
          adapter: adapter || "mock",
          execution_path: "unknown",
          readiness: "unavailable",
          trust_status: "unknown",
          requires_confirm_run: adapter === "hermes" || adapter === "openclaw",
          live_ready: false,
          confirm_run_wall: {
            required: adapter === "hermes" || adapter === "openclaw",
            satisfied: false,
            server_executes_live_without_confirm: false,
          },
          prepared_action_wall: {
            required_for_live_customer_worker: adapter === "hermes" || adapter === "openclaw",
            server_executes_prepared_action_without_approval: false,
          },
          token_omitted: true,
        },
        summary: {},
        gates: [],
        safety: {
          read_only: true,
          ledger_mutated: false,
          daemon_started: false,
          adapter_executed: false,
          live_execution_performed: false,
          token_omitted: true,
          raw_prompt_omitted: true,
        },
        token_omitted: true,
        live_execution_performed: false,
      },
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

export async function loadServerGatewaySessions(): Promise<ServerLoadResult<AgentGatewaySessionsPayload>> {
  try {
    return { data: safeGatewaySessionsPayload(await serverMisJson<AgentGatewaySessionsPayload>("/agent-gateway/sessions")), error: null };
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

export async function loadServerBases(): Promise<ServerLoadResult<BasesPayload>> {
  try {
    return { data: await serverMisJson<BasesPayload>("/bases"), error: null };
  } catch (err) {
    return { data: { bases: [], capabilities: [] }, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerTemplatePackages(): Promise<ServerLoadResult<TemplatePackage[]>> {
  try {
    return { data: await serverMisJson<TemplatePackage[]>("/template-packages"), error: null };
  } catch (err) {
    return { data: [], error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerTemplateBindings(): Promise<ServerLoadResult<TemplateBinding[]>> {
  try {
    return { data: await serverMisJson<TemplateBinding[]>("/template-bindings"), error: null };
  } catch (err) {
    return { data: [], error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerWorkflowJobs(limit = 6): Promise<ServerLoadResult<WorkflowJobListPayload>> {
  try {
    return { data: await serverMisJson<WorkflowJobListPayload>(`/workflows/jobs?limit=${encodeURIComponent(String(limit))}`), error: null };
  } catch (err) {
    return { data: { jobs: [] }, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerCustomerWorkerPreparedActions(limit = 6): Promise<ServerLoadResult<CustomerWorkerPreparedActionListPayload>> {
  try {
    return { data: await serverMisJson<CustomerWorkerPreparedActionListPayload>(`/workflows/customer-worker-prepared-actions?limit=${encodeURIComponent(String(limit))}`), error: null };
  } catch (err) {
    return { data: { prepared_actions: [] }, error: err instanceof Error ? err.message : String(err) };
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
