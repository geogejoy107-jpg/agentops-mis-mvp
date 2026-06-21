import { Link } from "react-router";
import { useEffect, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, Play, RefreshCw, Activity, Power, Square, KeyRound, ShieldCheck, Trash2, RotateCw, Inbox, GripVertical, XCircle, Copy } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import {
  createAgentGatewayEnrollment,
  closeExecutionEvidenceGap,
  decideApproval,
  decideEvaluationCase,
  decideMemory,
  dispatchCommanderWorkPackage,
  dispatchCommanderWorkPackageBatch,
  dispatchLocalWorkerOnce,
  issueApprovedAgentGatewayEnrollment,
  loadApprovals,
  loadAgentGatewayEnrollments,
  loadAgentGatewaySessions,
  loadAgentGatewayStatus,
  loadAgents,
  loadCustomerDeliveryBoard,
  loadDashboard,
  loadDemoReadiness,
  loadCommanderWorkPackages,
  loadHermesOpenClawLoopReadback,
  loadIntegrationInbox,
  loadLocalReadiness,
  loadOperatorActionPlan,
  loadReviewQueue,
  loadSecurityProductionReadiness,
  loadStuckWorkflowJobs,
  loadWorkerAdapterReadiness,
  loadWorkerDaemonLogs,
  loadWorkerFleet,
  loadWorkerFleetHygiene,
  loadWorkerStatus,
  loadWorkflowJobs,
  markWorkflowJobFailed,
  applyWorkerFleetHygiene,
  planCommanderWorkPackages,
  promoteCommanderSynthesis,
  previewAgentGatewayEnrollmentPolicy,
  releaseWorkerTask,
  restartLocalWorkerDaemon,
  revokeAgentGatewayEnrollment,
  revokeAgentGatewaySession,
  rotateAgentGatewayEnrollment,
  runCustomerWorkerTaskWorkflow,
  runHermesOpenClawLoopWorkflow,
  requestAgentGatewayEnrollment,
  startLocalWorkerDaemon,
  stopLocalWorkerDaemon,
  submitCustomerWorkerTaskJob,
  synthesizeCommanderWorkPackages,
  useLiveData,
  type AgentGatewayEnrollmentCreateResult,
  type AgentGatewayEnrollmentPolicyPreview,
  type AgentGatewayEnrollmentRequestResult,
  type CommanderWorkPackagePlanPayload,
  type CommanderSynthesisPromotionPayload,
  type CustomerDeliveryBoardPayload,
  type CustomerTaskWorkflowResult,
  type ExecutionEvidenceGapItem,
  type HermesOpenClawLoopReadbackPayload,
  type HermesOpenClawLoopWorkflowResult,
  type OperatorActionPlanPayload,
  type ReviewQueuePayload,
  type TaskIntakeChecklistItem,
  type WorkerAdapterName,
  type WorkerDispatchResult,
  type WorkerFleetHygienePayload,
  type WorkflowJob,
} from "../../data/liveApi";
import { pick, usePreferences } from "../../context/PreferencesContext";

const RUNTIME_COLOR: Record<string, string> = {
  claude_code: "#7A5AF8",
  codex:       "#22D3EE",
  openhands:   "#E76F51",
  mock:        "#6B7280",
  openclaw:    "#2A9D8F",
  hermes:      "#2E86AB",
  crewai:      "#FBBF24",
  langgraph:   "#F87171",
};

const DEFAULT_GATEWAY_SCOPES = [
  "agents:heartbeat",
  "agent_plans:write",
  "plan_evidence:write",
  "tasks:create",
  "tasks:read",
  "tasks:claim",
  "runs:write",
  "toolcalls:write",
  "artifacts:write",
  "evaluations:submit",
  "audit:write",
];

const GATEWAY_SCOPE_PRESETS = [
  {
    id: "worker",
    scopes: DEFAULT_GATEWAY_SCOPES,
  },
  {
    id: "observer",
    scopes: ["agents:heartbeat", "tasks:read", "audit:write"],
  },
  {
    id: "approval",
    scopes: ["agents:heartbeat", "tasks:read", "approvals:request", "audit:write"],
  },
  {
    id: "full",
    scopes: ["agents:write", "agents:heartbeat", "agent_plans:read", "agent_plans:write", "plan_evidence:read", "plan_evidence:write", "tasks:create", "tasks:read", "tasks:claim", "runs:write", "toolcalls:write", "artifacts:write", "approvals:request", "memories:propose", "evaluations:submit", "audit:write"],
  },
];

const WORKER_ADAPTERS = ["mock", "hermes", "openclaw"] as const;

export function AIEmployees() {
  const { locale } = usePreferences();
  const [dispatching, setDispatching] = useState<string | null>(null);
  const [dispatchResult, setDispatchResult] = useState<string | null>(null);
  const [hygieneBusy, setHygieneBusy] = useState(false);
  const [hygieneResult, setHygieneResult] = useState<WorkerFleetHygienePayload | null>(null);
  const [hygieneError, setHygieneError] = useState<string | null>(null);
  const [customerTaskBusy, setCustomerTaskBusy] = useState(false);
  const [customerTaskError, setCustomerTaskError] = useState<string | null>(null);
  const [customerTaskResult, setCustomerTaskResult] = useState<CustomerTaskWorkflowResult | null>(null);
  const [customerTaskJob, setCustomerTaskJob] = useState<WorkflowJob | null>(null);
  const [lastWorkerDispatch, setLastWorkerDispatch] = useState<WorkerDispatchResult | null>(null);
  const [copiedIntakeCommand, setCopiedIntakeCommand] = useState<string | null>(null);
  const [loopLaneBusy, setLoopLaneBusy] = useState(false);
  const [loopLaneError, setLoopLaneError] = useState<string | null>(null);
  const [loopLaneResult, setLoopLaneResult] = useState<HermesOpenClawLoopWorkflowResult | null>(null);
  const [loopLaneForm, setLoopLaneForm] = useState({
    topic: locale === "zh"
      ? "请 Hermes 和 OpenClaw 审视 AgentOps MIS 下一步最重要的产品闭环。"
      : "Ask Hermes and OpenClaw to review the next most important AgentOps MIS product closure.",
    loop_id: "",
  });
  const [workflowJobAction, setWorkflowJobAction] = useState<string | null>(null);
  const [workflowJobResult, setWorkflowJobResult] = useState<string | null>(null);
  const [reviewAction, setReviewAction] = useState<string | null>(null);
  const [reviewResult, setReviewResult] = useState<string | null>(null);
  const [commanderPlannerBusy, setCommanderPlannerBusy] = useState(false);
  const [commanderPlannerError, setCommanderPlannerError] = useState<string | null>(null);
  const [commanderPlannerResult, setCommanderPlannerResult] = useState<CommanderWorkPackagePlanPayload | null>(null);
  const [lastSynthesis, setLastSynthesis] = useState<{ artifactId: string; approvalId?: string | null } | null>(null);
  const [synthesisPromotion, setSynthesisPromotion] = useState<CommanderSynthesisPromotionPayload | null>(null);
  const [commanderPlannerForm, setCommanderPlannerForm] = useState({
    goal: locale === "zh"
      ? "用 AgentOps MIS 协调一个客户 AI 团队项目：拆分并行工作包、分派 agent、保留证据、准备交付。"
      : "Use AgentOps MIS to coordinate a customer AI-team project: split parallel work packages, assign agents, keep evidence, and prepare delivery.",
    max_packages: "5",
  });
  const [actionQueueOrder, setActionQueueOrder] = useState<string[]>([]);
  const [draggedActionId, setDraggedActionId] = useState<string | null>(null);
  const [customerTaskForm, setCustomerTaskForm] = useState<{
    adapter: (typeof WORKER_ADAPTERS)[number];
    title: string;
    description: string;
  }>({
    adapter: "mock",
    title: locale === "zh" ? "优化 Pixel Office 工作台" : "Improve the Pixel Office workspace",
    description: locale === "zh"
      ? "请 AI 团队从客户视角审视 Pixel Office：让像素风更精致，流程更清楚，同时保持 MIS 账本、审批和运行证据可见。"
      : "Ask the AI team to review Pixel Office from a customer perspective: improve the pixel style, clarify the flow, and keep MIS ledger, approvals, and run evidence visible.",
  });
  const [selectedLogAdapter, setSelectedLogAdapter] = useState<(typeof WORKER_ADAPTERS)[number]>("mock");
  const [integrationInboxBucket, setIntegrationInboxBucket] = useState("all");
  const [enrollmentAction, setEnrollmentAction] = useState<string | null>(null);
  const [enrollmentResult, setEnrollmentResult] = useState<string | null>(null);
  const [createdToken, setCreatedToken] = useState<AgentGatewayEnrollmentCreateResult | null>(null);
  const [createdRequest, setCreatedRequest] = useState<AgentGatewayEnrollmentRequestResult | null>(null);
  const [enrollmentPolicy, setEnrollmentPolicy] = useState<AgentGatewayEnrollmentPolicyPreview | null>(null);
  const [enrollmentPolicyError, setEnrollmentPolicyError] = useState<string | null>(null);
  const [issueApprovalId, setIssueApprovalId] = useState("");
  const [enrollmentForm, setEnrollmentForm] = useState({
    agent_id: "agt_remote_customer_worker",
    name: "Customer Remote Worker",
    runtime_type: "mock",
    workspace_id: "local-demo",
    ttl_days: "30",
    heartbeat_timeout_sec: "300",
    scopes: DEFAULT_GATEWAY_SCOPES.join(", "),
  });
  const { data, loading, error, refresh } = useLiveData(async () => {
    const [metrics, demoReadiness, workerStatus, workerFleet, workerHygiene, adapterReadiness, localReadiness, operatorActionPlan, securityReadiness, integrationInbox, commanderWorkPackages, reviewQueue, customerDeliveryBoard, loopLaneReadback, enrollmentPayload, sessionPayload, gatewayStatus, approvals, daemonLogs, workflowJobs, stuckWorkflowJobs] = await Promise.all([
      loadDashboard(),
      loadDemoReadiness(),
      loadWorkerStatus(),
      loadWorkerFleet(),
      loadWorkerFleetHygiene({ limit: 5 }),
      loadWorkerAdapterReadiness(),
      loadLocalReadiness(),
      loadOperatorActionPlan(12),
      loadSecurityProductionReadiness(),
      loadIntegrationInbox({ bucket: integrationInboxBucket, limit: 20 }),
      loadCommanderWorkPackages({ limit: 8 }),
      loadReviewQueue(12),
      loadCustomerDeliveryBoard(8),
      loadHermesOpenClawLoopReadback("", 6),
      loadAgentGatewayEnrollments(),
      loadAgentGatewaySessions(),
      loadAgentGatewayStatus(),
      loadApprovals(),
      Promise.all(WORKER_ADAPTERS.map(adapter => loadWorkerDaemonLogs(adapter))),
      loadWorkflowJobs(8),
      loadStuckWorkflowJobs(30, 8),
    ]);
    const agents = await loadAgents(metrics);
    return { agents, demoReadiness, workerStatus, workerFleet, workerHygiene, adapterReadiness, localReadiness, operatorActionPlan, securityReadiness, integrationInbox, commanderWorkPackages, reviewQueue, customerDeliveryBoard, loopLaneReadback, enrollmentPayload, sessionPayload, gatewayStatus, approvals, daemonLogs, workflowJobs, stuckWorkflowJobs };
  }, [integrationInboxBucket]);
  const agents = data?.agents || [];
  const demoReadiness = data?.demoReadiness;
  const workerStatus = data?.workerStatus;
  const workerFleet = data?.workerFleet;
  const workerHygiene = data?.workerHygiene as WorkerFleetHygienePayload | undefined;
  const activeHygiene = hygieneResult || workerHygiene;
  const adapterReadiness = data?.adapterReadiness;
  const localReadiness = data?.localReadiness;
  const operatorActionPlan = data?.operatorActionPlan as OperatorActionPlanPayload | undefined;
  const operatorPlanActions = operatorActionPlan?.actions || [];
  const operatorPlanSummary = operatorActionPlan?.summary;
  const operatorEvidenceGaps = operatorActionPlan?.execution_evidence?.gaps || [];
  const taskIntakeChecklist = operatorActionPlan?.task_intake;
  const taskIntakeSummary = taskIntakeChecklist?.summary;
  const taskIntakeItems = taskIntakeChecklist?.items || [];
  const securityReadiness = data?.securityReadiness;
  const integrationInbox = data?.integrationInbox;
  const commanderWorkPackages = data?.commanderWorkPackages;
  const commanderPackageRows = commanderWorkPackages?.work_packages || [];
  const commanderPlannedPackageCount = commanderPackageRows.filter(pkg => pkg.package_status === "planned" || pkg.status === "planned").length;
  const commanderReadyPackageCount = commanderPackageRows.filter(pkg => pkg.package_status === "ready_for_review").length;
  const reviewQueue = data?.reviewQueue as ReviewQueuePayload | undefined;
  const reviewQueueSummary = reviewQueue?.summary;
  const reviewQueueItems = reviewQueue?.review_items || [];
  const reviewQueueSafety = reviewQueue?.safety;
  const customerDeliveryBoard = data?.customerDeliveryBoard as CustomerDeliveryBoardPayload | undefined;
  const customerDeliveries = customerDeliveryBoard?.deliveries || [];
  const customerDeliverySummary = customerDeliveryBoard?.summary;
  const customerDeliverySafety = customerDeliveryBoard?.safety;
  const loopLaneReadback = data?.loopLaneReadback as HermesOpenClawLoopReadbackPayload | undefined;
  const localEvidence = localReadiness?.evidence;
  const localReadinessActions = localReadiness?.next_actions || [];
  const synthesisLifecycle = localReadiness?.commander_synthesis_lifecycle;
  const synthesisLifecycleActions = synthesisLifecycle?.next_actions || [];
  const localReadinessGates = localReadiness?.gates || [];
  const localReadinessReadyGates = localReadinessGates.filter(gate => gate.ok).length;
  const localSafetyOk = Boolean(localReadiness?.token_omitted && localReadiness?.live_execution_performed === false);
  const integrationInboxSummary = integrationInbox?.summary;
  const integrationInboxItems = integrationInbox?.inbox_items || [];
  const integrationInboxActions = integrationInbox?.recommended_next_actions || [];
  const integrationInboxSafety = integrationInbox?.safety;
  const integrationInboxSafe = Boolean(
    integrationInbox?.token_omitted &&
    integrationInbox?.live_execution_performed === false &&
    integrationInboxSafety?.read_only &&
    integrationInboxSafety?.ledger_mutated === false &&
    integrationInboxSafety?.raw_prompt_omitted,
  );
  const fleetHealth = workerStatus?.fleet_health;
  const fleetLanes = workerFleet?.lanes || [];
  const fleetLaneSummary = workerFleet?.summary;
  const fleetGates = fleetHealth?.gates || [];
  const recommendedActions = fleetHealth?.recommended_actions || [];
  const remoteHealth = workerStatus?.remote_worker_health;
  const remoteWorkers = remoteHealth?.remote_workers || [];
  const recentRemoteSessions = remoteHealth?.recent_sessions || [];
  const daemonLogs = data?.daemonLogs || [];
  const selectedDaemonLog = daemonLogs.find(item => item.daemon.adapter === selectedLogAdapter)?.daemon;
  const workflowJobs = data?.workflowJobs?.jobs || [];
  const stuckWorkflowJobs = data?.stuckWorkflowJobs?.stuck_jobs || [];
  const stuckWorkflowJobRefs = workerStatus?.stuck_workflow_job_refs || [];
  const stuckWorkflowRecoveryRows = stuckWorkflowJobs.length > 0 ? stuckWorkflowJobs : stuckWorkflowJobRefs;
  const recentEvents = workerStatus?.recent_events || [];
  const stuckTasks = workerStatus?.stuck_tasks || [];
  const hygieneSummary = activeHygiene?.summary;
  const hygieneActionsAvailable = Number(hygieneSummary?.actions_available || 0);
  const enrollments = data?.enrollmentPayload?.enrollments || [];
  const sessions = data?.sessionPayload?.sessions || [];
  const gatewayStatus = data?.gatewayStatus;
  const enrollmentApprovals = (data?.approvals || []).filter(item => item.reason.includes("Approve scoped enrollment"));
  const validScopes = data?.enrollmentPayload?.valid_scopes || DEFAULT_GATEWAY_SCOPES;
  const activeAgents = agents.filter(a => a.status === "running").length;
  const activeEnrollments = enrollments.filter(item => item.status === "active").length;
  const staleEnrollments = enrollments.filter(item => item.heartbeat_state === "stale").length;
  const activeSessions = sessions.filter(item => item.session_state === "active").length;
  const runningDaemons = (workerStatus?.daemons || []).filter(daemon => daemon.running).length;
  const stuckWorkerCount = Number(workerStatus?.stuck_worker_tasks || stuckTasks.length || 0);
  const stuckWorkflowJobCount = Number(workerStatus?.stuck_workflow_jobs || stuckWorkflowJobRefs.length || stuckWorkflowJobs.length || 0);
  const liveReadyAdapters = adapterReadiness?.summary.live_ready_adapters || workerStatus?.adapter_readiness?.live_ready_adapters || [];
  const unavailableAdapters = adapterReadiness?.summary.unavailable_adapters || workerStatus?.adapter_readiness?.unavailable_adapters || [];
  const blockedAdapters = adapterReadiness?.summary.blocked_adapters || workerStatus?.adapter_readiness?.blocked_adapters || [];
  const recommendedAdapter = adapterReadiness?.summary.recommended_adapter || workerStatus?.adapter_readiness?.recommended_adapter || "mock";
  const localRecommendedAdapter = localReadiness?.adapter_readiness?.recommended_adapter || recommendedAdapter;
  const selectedAdapterRoute = adapterReadiness?.adapters?.[customerTaskForm.adapter];
  const selectedAdapterLiveBlocked = customerTaskForm.adapter !== "mock" && ["unavailable", "blocked"].includes(selectedAdapterRoute?.readiness || "");
  const selectedAdapterIsReady = customerTaskForm.adapter === "mock" || selectedAdapterRoute?.readiness === "ready" || selectedAdapterRoute?.readiness === "review_required";
  const gatewayReady = Boolean(gatewayStatus?.auth.authenticated || ["ready", "ok", "authenticated"].includes(gatewayStatus?.status || ""));
  const copy = pick(locale, {
    en: {
      title: "AI Employees",
      summary: `${agents.length} registered agents · ${activeAgents} active · live backend`,
      loading: "Loading live agents...",
      backendUnavailable: "Live backend unavailable",
      refresh: "Refresh live agents",
      commandCenterTitle: "Worker Fleet Console",
      commandCenterSummary: "Adapter readiness, daemon capacity, remote heartbeat/session health, stuck recovery, and the next safe CLI/API action.",
      demoReadinessTitle: "Demo readiness",
      demoReadinessSummary: "Canonical v1.5 recording path: readiness, security boundary, fleet lanes, async inbox, customer task loop, and run ledger evidence.",
      demoReady: "Demo ready",
      shotsReady: "Shots ready",
      actionQueueTitle: "Operator action queue",
      actionQueueSummary: "Drag to reorder your next checks. Use arrows as the precise fallback.",
      actionSource: "Source",
      dragToReorder: "Drag to reorder",
      resetOrder: "Reset order",
      moveUp: "Move up",
      moveDown: "Move down",
      closeEvidenceGap: "Close gap",
      closingEvidenceGap: "Closing...",
      evidenceClosureLedger: "Evidence closure ledger",
      evidenceClosureSummary: "Audit readback for remediated source-run debt: closure-ready, closed, waived and reopened decisions.",
      taskIntakeTitle: "Task intake gates",
      taskIntakeSummary: "Pre-run governance for planned work: assignment, Agent Plan, knowledge retrieval, base reference and risk boundary.",
      activeIntakeGate: "Active intake gate",
      activeIntakeSummary: "Planned work is blocked before worker pull. Resolve the listed Agent Plan / knowledge gates first.",
      workerStartBlockedHint: "Worker daemon start/restart is held until intake gates pass.",
      copyCommand: "Copy command",
      copiedCommand: "Copied",
      reopenEvidenceGap: "Reopen",
      reopeningEvidenceGap: "Reopening...",
      closureDecision: "Decision",
      remediationState: "Remediation",
      noClosureRows: "No closure decisions yet.",
      noIntakeRows: "No planned or backlog tasks to gate.",
      intakeReady: "Ready",
      intakeBlocked: "Blocked",
      intakeAttention: "Attention",
      assignedAgents: "Assigned",
      planReferences: "Refs",
      agentPlan: "Agent Plan",
      planEvidence: "Plan evidence",
      intakeGate: "Intake gate",
      localReadinessTitle: "Local Readiness",
      localReadinessSummary: "Read-only proof that this local MIS workspace can be operated without leaking tokens or triggering live work.",
      localReadinessOverall: "Overall status",
      evidenceChains: "Evidence chains",
      memoryApprovalCounts: "Memory / approvals",
      safetyProof: "Safety proof",
      tokenOmittedProof: "Token omitted",
      liveExecutionProof: "Live execution not performed",
      integrationInboxTitle: "Async Integration Inbox",
      integrationInboxSummary: "Commander queue for worker results arriving at different speeds: review ready work, watch running jobs, and recover blocked items.",
      commanderPlannerTitle: "Commander Work Package Planner",
      commanderPlannerSummary: "Turn one customer goal into parallel MIS work-package tasks for the AI team. Preview is safe; confirm writes planned tasks into the ledger.",
      commanderGoal: "Project goal",
      commanderMaxPackages: "Packages",
      previewPlan: "Preview plan",
      createWorkPackages: "Create work packages",
      planning: "Planning...",
      plannerResult: "Planner result",
      plannedPackages: "Planned packages",
      createdPackages: "Created tasks",
      plannerSafety: "Preview is safe",
      persistedPackages: "Persisted packages",
      packageReadback: "Package readback",
      packageStatus: "Package status",
      dispatchPackage: "Run package",
      dispatchPackageMock: "Run mock",
      dispatchPackageHermes: "Run Hermes",
      dispatchPackageOpenClaw: "Run OpenClaw",
      dispatchBatchMock: "Queue planned mock batch",
      synthesizePackages: "Create synthesis report",
      promoteSynthesis: "Promote approved synthesis",
      synthesisLoop: "Synthesis loop",
      reviewQueueTitle: "Human Review Queue",
      reviewQueueSummary: "One operator queue for approvals, memory candidates and customer deliveries. Handle returned work first without waiting for every worker lane.",
      reviewQueueEmpty: "No review items. Keep dispatching or watch the async inbox.",
      reviewActionResult: "Review action",
      reviewApprove: "Approve",
      reviewReject: "Reject",
      reviewReadbackProof: "Queue readback",
      reviewDecisionAuditProof: "Decisions write audit",
      pendingApprovals: "Pending approvals",
      memoryCandidates: "Memory candidates",
      failedBenchmarks: "Failed benchmarks",
      waitingDeliveries: "Waiting deliveries",
      returnedItems: "Returned items",
      cliAction: "CLI action",
      alternateAction: "Alternative",
      customerDeliveryBoardTitle: "Customer Delivery Board",
      customerDeliveryBoardSummary: "Read-only customer-facing board: delivery artifact, linked task/run, approvals, evaluations, audit evidence, and next action.",
      planEvidenceGate: "Plan evidence gate",
      planEvidenceVerified: "Verified",
      planEvidenceBlocked: "Blocked",
      planEvidenceMissing: "Missing manifest",
      loopLaneTitle: "Hermes/OpenClaw Loop Lane",
      loopLaneSummary: "Run a supervised dry-run review loop, then inspect parent/child runs, plans, artifacts, audit and plan evidence manifests.",
      loopTopic: "Loop topic",
      loopId: "Loop ID",
      runLoopLane: "Run safe loop",
      resumeLoopLane: "Resume loop",
      loopRunning: "Loop running...",
      loopReadback: "Loop readback",
      verifiedManifests: "Verified manifests",
      blockedManifests: "Blocked manifests",
      parentRun: "Parent run",
      deliveriesReady: "Ready",
      deliveriesWaiting: "Waiting approval",
      deliveriesAttention: "Needs attention",
      deliveryEmpty: "No customer deliveries yet. Dispatch a customer worker task first.",
      deliverySafeReadback: "Safe readback",
      openReport: "Open report",
      inboxFilter: "Queue view",
      inboxAll: "All",
      readyForReview: "Ready",
      stillRunning: "Running",
      blockedItems: "Blocked",
      lateOrStale: "Late/stale",
      memoryReview: "Memory review",
      inboxEmpty: "No async integration items yet.",
      readOnlyProof: "Read-only",
      ledgerMutationProof: "Ledger unchanged",
      rawPromptProof: "Raw prompt omitted",
      itemAge: "Age",
      itemOwner: "Owner",
      itemBucket: "Bucket",
      overallFleetHealth: "Fleet health",
      fleetHygieneTitle: "Fleet hygiene",
      fleetHygieneSummary: "Plan or confirm cleanup for stale running worker tasks and never-seen remote enrollments. Cleanup writes audit/runtime evidence and never runs live adapters.",
      hygienePlan: "Plan cleanup",
      hygieneApply: "Confirm cleanup",
      hygieneRunning: "Checking...",
      hygieneActions: "Actions",
      staleNeverSeen: "Never-seen enrollments",
      releasedTasks: "Released",
      revokedEnrollments: "Revoked",
      hygieneNoActions: "No cleanup needed.",
      hygieneSafety: "No live execution",
      healthGates: "Health gates",
      recommendedActions: "Recommended actions",
      noRecommendedActions: "No urgent action. Keep monitoring the worker status.",
      remoteWorkersTitle: "Remote heartbeat/session",
      recentRemoteSessionsTitle: "Recent sessions",
      totalEnrollments: "Total enrollments",
      heartbeatFresh: "Fresh",
      heartbeatStale: "Stale",
      heartbeatNeverSeen: "Never seen",
      workflowRecovery: "Workflow recovery",
      recoveryRefs: "Recovery refs",
      contract: "Contract",
      noRemoteWorkers: "No remote workers enrolled.",
      daemonBackoff: "Backoff",
      noBackoff: "none",
      gatewayTitle: "Agent Gateway",
      gatewaySummary: "Machine-facing API/CLI layer for local and remote agents.",
      authMode: "Auth mode",
      authenticated: "Authenticated",
      productionSecurity: "Production security",
      productionReady: "Production ready",
      localDevOnly: "Local demo only",
      securityGate: "Security gate",
      gatewayWorkspace: "Workspace",
      gatewayScopes: "Allowed scopes",
      activeEnrollments: "Active enrollments",
      staleEnrollments: "Stale heartbeats",
      activeSessions: "Active sessions",
      yes: "Yes",
      no: "No",
      runs: "Runs",
      success: "Success",
      approvals: "Approvals",
      budget: "Budget",
      more: "more",
      workerTitle: "Local Worker Loop",
      workerSummary: "Pulls normal MIS tasks, executes through mock / Hermes / OpenClaw, and writes run · tool · eval · audit.",
      customerTaskTitle: "Customer Task Dispatch",
      customerTaskSummary: "Create a normal MIS task, let an agent worker execute it through the selected adapter, then inspect ledger evidence.",
      taskTitleLabel: "Task title",
      taskDescriptionLabel: "Task description",
      adapterLabel: "Runtime adapter",
      runSafeTask: "Run safe plan",
      confirmLiveTask: "Confirm live run",
      submitAsyncTask: "Submit async job",
      customerTaskRunning: "Running task...",
      confirmLiveHint: "Hermes/OpenClaw require explicit confirmation before live execution. Mock is the safe default.",
      asyncTaskHint: "Use async jobs for long Hermes/OpenClaw work; the ledger records job status, run, artifact, eval and audit evidence.",
      selectedAdapterReady: "Selected route is ready for this dispatch.",
      selectedAdapterBlocked: "Selected live route is not ready. Use the next action before confirming a real run.",
      taskId: "Task",
      jobId: "Job",
      jobType: "Workflow",
      runId: "Run",
      artifactId: "Artifact",
      evidence: "Evidence",
      openTask: "Open task",
      openRun: "Open run",
      workflowJobsTitle: "Async Workflow Jobs",
      workflowJobsSummary: "Recent customer worker/template jobs submitted through the machine-facing Agent Gateway path.",
      noWorkflowJobs: "No workflow jobs yet.",
      stuckWorkflowJobsTitle: "Stuck Workflow Jobs",
      stuckWorkflowJobsSummary: "Queued or running workflow jobs older than the recovery threshold.",
      noStuckWorkflowJobs: "No stuck workflow jobs.",
      markJobFailed: "Mark failed",
      markingJobFailed: "Marking...",
      outputSummary: "Output",
      workers: "Workers",
      completedRuns: "Completed worker runs",
      pendingTasks: "Pending worker tasks",
      stuckTasks: "Stuck tasks",
      releaseTask: "Release",
      releasingTask: "Releasing...",
      noStuckTasks: "No stuck running tasks.",
      age: "Age",
      linkedRun: "Run",
      dispatchMock: "Run mock once",
      dispatchHermes: "Run Hermes once",
      dispatchOpenClaw: "Run OpenClaw once",
      startMockDaemon: "Start mock daemon",
      startHermesDaemon: "Start Hermes daemon",
      startOpenClawDaemon: "Start OpenClaw daemon",
      restartMockDaemon: "Restart mock",
      restartHermesDaemon: "Restart Hermes",
      restartOpenClawDaemon: "Restart OpenClaw",
      stopDaemons: "Stop daemons",
      dispatching: "Dispatching...",
      restarting: "Restarting...",
      starting: "Starting...",
      stopping: "Stopping...",
      recentRun: "Recent run",
      daemonStatus: "Daemon status",
      pid: "PID",
      processed: "Processed",
      iterations: "Loops",
      errors: "Errors",
      lastError: "Last error",
      statePath: "State path",
      fleetTitle: "Worker Fleet Telemetry",
      fleetSummary: "Read-only observability for local daemons and Agent Gateway events.",
      fleetLanes: "Fleet lanes",
      laneType: "Type",
      laneHealth: "Health",
      laneHeartbeat: "Heartbeat",
      laneSession: "Session",
      laneLastSeen: "Last seen",
      laneNextAction: "Next action",
      noFleetLanes: "No worker fleet lanes yet.",
      daemonLogs: "Daemon logs",
      recentEvents: "Recent gateway events",
      logPath: "Log path",
      noLogs: "No log lines yet.",
      noEvents: "No runtime events yet.",
      eventStatus: "Status",
      eventAgent: "Agent",
      enrollmentTitle: "Remote Agent Enrollment",
      enrollmentSummary: "Issue scoped tokens for agents running on another laptop or server. The token is shown once; MIS stores only a hash.",
      enrollmentPolicyTitle: "Scope policy preview",
      enrollmentPolicySummary: "Read-only preview before token issue: risk, approval path, privileged scopes, and worker viability.",
      riskLevel: "Risk",
      policyType: "Policy",
      approvalPath: "Approval path",
      directCreatePath: "Direct create",
      recommendedPath: "Recommended",
      invalidScopes: "Invalid scopes",
      privilegedScopes: "Privileged",
      workerWriteScopes: "Worker writes",
      missingWorkerScopes: "Missing worker scopes",
      createToken: "Create scoped token",
      creatingToken: "Creating token...",
      requestEnrollment: "Request approval",
      requestingEnrollment: "Requesting...",
      issueApproved: "Issue approved token",
      issuingApproved: "Issuing...",
      approveRequest: "Approve",
      rejectRequest: "Reject",
      approvalRequestTitle: "Approval-gated requests",
      noApprovalRequests: "No enrollment approval requests yet.",
      requestCreated: "Enrollment request created",
      rotateToken: "Rotate",
      rotatingToken: "Rotating...",
      revokeToken: "Revoke",
      revokingToken: "Revoking...",
      scopePresets: "Permission presets",
      presetWorker: "Worker",
      presetObserver: "Observer",
      presetApproval: "Approval",
      presetFull: "Full",
      agentId: "Agent ID",
      agentName: "Display name",
      runtime: "Runtime",
      workspace: "Workspace",
      ttlDays: "TTL days",
      heartbeat: "Heartbeat timeout",
      scopes: "Scopes",
      tokenShownOnce: "Copy this token now. It will not be shown again.",
      launchPacket: "Remote launch packet",
      envSetup: "Environment",
      installCommand: "Install",
      verifyCommand: "Verify",
      preflightCommand: "Preflight",
      sessionCommand: "Mint session",
      heartbeatCommand: "Heartbeat",
      runOnceCommand: "Run once",
      runLoopCommand: "Run loop",
      launchdTemplate: "launchd template",
      systemdTemplate: "systemd template",
      fallbackCommand: "Repo fallback",
      recentEnrollments: "Recent enrollments",
      recentSessions: "Recent sessions",
      lastHeartbeat: "Last heartbeat",
      lastUsed: "Last used",
      expires: "Expires",
      tokenId: "Token",
      sessionId: "Session",
      parentToken: "Parent token",
      revokeSession: "Revoke session",
      revokingSession: "Revoking session...",
      noEnrollments: "No remote enrollments yet.",
      noSessions: "No short-lived sessions yet.",
      operatorTitle: "Operator Readiness",
      operatorSummary: "Use this page as the one-person company control tower: assign work, run local AI workers, enroll remote machines, and recover stuck tasks without leaving the MIS ledger.",
      modeLocalTitle: "Local worker loop",
      modeLocalBody: "Mock is safe for dry-runs; Hermes and OpenClaw buttons require explicit live confirmation and write run/tool/eval/audit evidence.",
      modeLiveTitle: "Real runtime dispatch",
      modeLiveBody: "Hermes/OpenClaw adapters execute normal MIS tasks, not isolated demos. Results are summarized, hashed, and recorded in the ledger.",
      modeRemoteTitle: "Remote agent entry",
      modeRemoteBody: "External machines use scoped enrollment tokens, short-lived sessions, heartbeat, and workspace-bound permissions.",
      modeRecoveryTitle: "Recovery queue",
      modeRecoveryBody: "Stale running worker tasks can be released back to planned; linked runs are blocked with audit evidence.",
      adapterRoutesTitle: "Adapter routes",
      adapterRoutesSummary: "Read-only route selection for agent workers before live dispatch.",
      recommendedAdapter: "Recommended",
      trustStatus: "Trust",
      targetResource: "Target",
      nextAction: "Next action",
      liveReady: "live ready",
      notLiveReady: "not live ready",
      statusRunning: "running",
      statusReady: "ready",
      statusConfirm: "confirm required",
      statusAttention: "attention",
      statusClear: "clear",
      statusSetup: "setup",
    },
    zh: {
      title: "AI 员工",
      summary: `${agents.length} 个已注册代理 · ${activeAgents} 个运行中 · 连接本地后端`,
      loading: "正在加载实时代理...",
      backendUnavailable: "本地后端不可用",
      refresh: "刷新实时代理",
      commandCenterTitle: "Worker Fleet 控制台",
      commandCenterSummary: "集中查看 adapter 就绪、daemon 容量、远程心跳/session、卡住恢复和下一步安全 CLI/API 动作。",
      demoReadinessTitle: "Demo 就绪",
      demoReadinessSummary: "v1.5 录屏主路径：本地就绪、安全边界、Fleet 队伍、异步 Inbox、客户任务闭环、Run 账本证据。",
      demoReady: "可录 Demo",
      shotsReady: "镜头就绪",
      actionQueueTitle: "Operator 动作队列",
      actionQueueSummary: "拖拽调整下一步检查顺序；也可以用箭头精确移动。",
      actionSource: "来源",
      dragToReorder: "拖拽排序",
      resetOrder: "重置顺序",
      moveUp: "上移",
      moveDown: "下移",
      closeEvidenceGap: "关闭缺口",
      closingEvidenceGap: "关闭中...",
      evidenceClosureLedger: "证据关闭账本",
      evidenceClosureSummary: "回读已修复源 run 债务的审计状态：待关闭、已关闭、已豁免和已重开。",
      taskIntakeTitle: "任务接收 Gate",
      taskIntakeSummary: "planned 工作的运行前治理：分派、Agent Plan、知识检索、底座引用和风险边界。",
      activeIntakeGate: "接单 Gate 生效",
      activeIntakeSummary: "已有 planned 工作在 worker pull 前被阻塞；请先处理 Agent Plan / 知识 Gate。",
      workerStartBlockedHint: "Worker 常驻启动/重启会被暂停，直到接单 Gate 通过。",
      copyCommand: "复制命令",
      copiedCommand: "已复制",
      reopenEvidenceGap: "重开",
      reopeningEvidenceGap: "重开中...",
      closureDecision: "决策",
      remediationState: "修复",
      noClosureRows: "暂无关闭决策。",
      noIntakeRows: "暂无 planned/backlog 任务需要 Gate。",
      intakeReady: "就绪",
      intakeBlocked: "阻塞",
      intakeAttention: "需处理",
      assignedAgents: "已分派",
      planReferences: "引用",
      agentPlan: "Agent Plan",
      planEvidence: "计划证据",
      intakeGate: "接单 Gate",
      localReadinessTitle: "本地就绪",
      localReadinessSummary: "只读证明：这个本地 MIS 工作区可运行，同时不泄露 token，也不会触发真实执行。",
      localReadinessOverall: "整体状态",
      evidenceChains: "证据闭环",
      memoryApprovalCounts: "记忆 / 审批",
      safetyProof: "安全证明",
      tokenOmittedProof: "Token 已省略",
      liveExecutionProof: "未执行真实任务",
      integrationInboxTitle: "异步集成 Inbox",
      integrationInboxSummary: "Commander 用来处理不同速度 worker 回报的队列：审阅已完成工作、观察运行中 job、恢复阻塞项。",
      commanderPlannerTitle: "总指挥工作包规划器",
      commanderPlannerSummary: "把一个客户目标拆成多条 MIS 工作包任务，分派给 AI 团队并行推进。预览安全不改账本；确认后才写入 planned tasks。",
      commanderGoal: "项目目标",
      commanderMaxPackages: "工作包数",
      previewPlan: "预览规划",
      createWorkPackages: "创建工作包",
      planning: "规划中...",
      plannerResult: "规划结果",
      plannedPackages: "规划工作包",
      createdPackages: "已创建任务",
      plannerSafety: "预览安全",
      persistedPackages: "持久化工作包",
      packageReadback: "工作包读回",
      packageStatus: "工作包状态",
      dispatchPackage: "运行工作包",
      dispatchPackageMock: "运行 mock",
      dispatchPackageHermes: "运行 Hermes",
      dispatchPackageOpenClaw: "运行 OpenClaw",
      dispatchBatchMock: "批量排队 planned mock",
      synthesizePackages: "生成合并报告",
      promoteSynthesis: "晋升已批准报告",
      synthesisLoop: "合并闭环",
      reviewQueueTitle: "人工审核队列",
      reviewQueueSummary: "把审批、候选记忆和客户交付聚合成一个 operator 队列；哪个 worker 先回来，就先处理哪个。",
      reviewQueueEmpty: "暂无待审事项。可以继续派发任务，或观察异步 Inbox。",
      reviewActionResult: "审核动作",
      reviewApprove: "批准",
      reviewReject: "拒绝",
      reviewReadbackProof: "队列读取",
      reviewDecisionAuditProof: "决策写入审计",
      pendingApprovals: "待审批",
      memoryCandidates: "候选记忆",
      failedBenchmarks: "失败基准",
      waitingDeliveries: "待交付审批",
      returnedItems: "已返回事项",
      cliAction: "CLI 动作",
      alternateAction: "备用动作",
      customerDeliveryBoardTitle: "客户交付看板",
      customerDeliveryBoardSummary: "只读客户视角：交付 artifact、关联 task/run、审批、评估、审计证据和下一步动作。",
      planEvidenceGate: "计划证据门禁",
      planEvidenceVerified: "已验证",
      planEvidenceBlocked: "未通过",
      planEvidenceMissing: "缺少 manifest",
      loopLaneTitle: "Hermes/OpenClaw 循环 Lane",
      loopLaneSummary: "运行一个受监督的安全 dry-run 评审循环，然后查看父子 run、计划、artifact、审计和计划证据 manifest。",
      loopTopic: "循环主题",
      loopId: "Loop ID",
      runLoopLane: "运行安全循环",
      resumeLoopLane: "继续循环",
      loopRunning: "循环运行中...",
      loopReadback: "循环回读",
      verifiedManifests: "已验证 manifest",
      blockedManifests: "阻塞 manifest",
      parentRun: "父 Run",
      deliveriesReady: "可交付",
      deliveriesWaiting: "待审批",
      deliveriesAttention: "需处理",
      deliveryEmpty: "暂无客户交付。请先派发一个客户 worker 任务。",
      deliverySafeReadback: "安全只读",
      openReport: "打开报告",
      inboxFilter: "队列视角",
      inboxAll: "全部",
      readyForReview: "待审阅",
      stillRunning: "运行中",
      blockedItems: "阻塞",
      lateOrStale: "超时/陈旧",
      memoryReview: "记忆审查",
      inboxEmpty: "暂无异步集成事项。",
      readOnlyProof: "只读",
      ledgerMutationProof: "账本未修改",
      rawPromptProof: "原始 Prompt 已省略",
      itemAge: "耗时",
      itemOwner: "负责人",
      itemBucket: "分组",
      overallFleetHealth: "Fleet 健康",
      fleetHygieneTitle: "Fleet 清理",
      fleetHygieneSummary: "为卡住的运行中任务和从未心跳的远程接入生成清理计划；确认清理会写入审计/runtime 证据，但不会触发真实 adapter 执行。",
      hygienePlan: "只读计划",
      hygieneApply: "确认清理",
      hygieneRunning: "检查中...",
      hygieneActions: "可处理项",
      staleNeverSeen: "未连接接入",
      releasedTasks: "已释放",
      revokedEnrollments: "已吊销",
      hygieneNoActions: "暂无需要清理的项目。",
      hygieneSafety: "不执行真实任务",
      healthGates: "健康 Gate",
      recommendedActions: "推荐动作",
      noRecommendedActions: "暂无紧急动作，继续观察 worker status。",
      remoteWorkersTitle: "远程心跳 / Session",
      recentRemoteSessionsTitle: "最近 Session",
      totalEnrollments: "接入总数",
      heartbeatFresh: "新鲜",
      heartbeatStale: "过期",
      heartbeatNeverSeen: "未连接",
      workflowRecovery: "Workflow 恢复",
      recoveryRefs: "恢复引用",
      contract: "执行契约",
      noRemoteWorkers: "暂无远程 worker 接入。",
      daemonBackoff: "退避",
      noBackoff: "无",
      gatewayTitle: "Agent Gateway",
      gatewaySummary: "给本地和远程 agent 使用的 API/CLI 接入层。",
      authMode: "认证模式",
      authenticated: "已认证",
      productionSecurity: "生产安全",
      productionReady: "生产就绪",
      localDevOnly: "仅本地演示",
      securityGate: "安全 Gate",
      gatewayWorkspace: "工作区",
      gatewayScopes: "权限数量",
      activeEnrollments: "有效接入",
      staleEnrollments: "心跳过期",
      activeSessions: "有效 Session",
      yes: "是",
      no: "否",
      runs: "运行",
      success: "成功率",
      approvals: "审批",
      budget: "预算",
      more: "项更多",
      workerTitle: "本地 Worker 循环",
      workerSummary: "自动拉取普通 MIS 任务，通过 mock / Hermes / OpenClaw 执行，并写回 run · tool · eval · audit。",
      customerTaskTitle: "客户任务派发",
      customerTaskSummary: "创建一个普通 MIS 任务，让 agent worker 通过选定 adapter 执行，再查看账本证据。",
      taskTitleLabel: "任务标题",
      taskDescriptionLabel: "任务描述",
      adapterLabel: "运行 adapter",
      runSafeTask: "安全运行 / dry-run",
      confirmLiveTask: "确认真实运行",
      submitAsyncTask: "异步提交 Job",
      customerTaskRunning: "任务运行中...",
      confirmLiveHint: "Hermes/OpenClaw 真实执行前必须显式确认。mock 是安全默认。",
      asyncTaskHint: "长时间 Hermes/OpenClaw 工作建议用异步 Job；账本会记录 job 状态、run、artifact、评估和审计证据。",
      selectedAdapterReady: "当前选中的路由可以用于这次派发。",
      selectedAdapterBlocked: "当前真实运行路由未就绪。请先执行下一步动作，再确认真跑。",
      taskId: "任务",
      jobId: "Job",
      jobType: "工作流",
      runId: "Run",
      artifactId: "Artifact",
      evidence: "证据",
      openTask: "打开任务",
      openRun: "打开 Run",
      workflowJobsTitle: "异步 Workflow Jobs",
      workflowJobsSummary: "最近通过 Agent Gateway 机器接口提交的客户 worker / 模板任务。",
      noWorkflowJobs: "还没有异步任务。",
      stuckWorkflowJobsTitle: "卡住的 Workflow Jobs",
      stuckWorkflowJobsSummary: "超过恢复阈值仍处于 queued/running 的 workflow job。",
      noStuckWorkflowJobs: "暂无卡住的 workflow job。",
      markJobFailed: "标记 failed",
      markingJobFailed: "正在标记...",
      outputSummary: "输出",
      workers: "Worker",
      completedRuns: "已完成 worker run",
      pendingTasks: "待处理 worker 任务",
      stuckTasks: "卡住任务",
      releaseTask: "释放回队列",
      releasingTask: "正在释放...",
      noStuckTasks: "暂无卡住的运行中任务。",
      age: "已运行",
      linkedRun: "Run",
      dispatchMock: "运行 mock 单轮",
      dispatchHermes: "运行 Hermes 单轮",
      dispatchOpenClaw: "运行 OpenClaw 单轮",
      startMockDaemon: "启动 mock 常驻",
      startHermesDaemon: "启动 Hermes 常驻",
      startOpenClawDaemon: "启动 OpenClaw 常驻",
      restartMockDaemon: "重启 mock",
      restartHermesDaemon: "重启 Hermes",
      restartOpenClawDaemon: "重启 OpenClaw",
      stopDaemons: "停止常驻 worker",
      dispatching: "正在派发...",
      restarting: "正在重启...",
      starting: "正在启动...",
      stopping: "正在停止...",
      recentRun: "最近 run",
      daemonStatus: "常驻状态",
      pid: "进程",
      processed: "已处理",
      iterations: "轮询",
      errors: "错误",
      lastError: "最近错误",
      statePath: "状态路径",
      fleetTitle: "Worker Fleet 观测",
      fleetSummary: "只读查看本地 daemon 日志和 Agent Gateway 最近事件。",
      fleetLanes: "Fleet 队伍",
      laneType: "类型",
      laneHealth: "健康",
      laneHeartbeat: "心跳",
      laneSession: "Session",
      laneLastSeen: "最近出现",
      laneNextAction: "下一步动作",
      noFleetLanes: "暂无 worker fleet 队伍。",
      daemonLogs: "Daemon 日志",
      recentEvents: "最近网关事件",
      logPath: "日志路径",
      noLogs: "暂无日志行。",
      noEvents: "暂无运行事件。",
      eventStatus: "状态",
      eventAgent: "Agent",
      enrollmentTitle: "远程 Agent 接入",
      enrollmentSummary: "给运行在另一台电脑或服务器上的 agent 发放带权限范围的 token。token 只显示一次，MIS 只保存 hash。",
      enrollmentPolicyTitle: "Scope 策略预览",
      enrollmentPolicySummary: "发 token 前的只读检查：风险、审批路径、高权限 scope 和 worker 可执行性。",
      riskLevel: "风险",
      policyType: "策略",
      approvalPath: "走审批",
      directCreatePath: "直接创建",
      recommendedPath: "推荐路径",
      invalidScopes: "无效 scope",
      privilegedScopes: "高权限",
      workerWriteScopes: "Worker 写权限",
      missingWorkerScopes: "缺少 worker scope",
      createToken: "创建接入 token",
      creatingToken: "正在创建...",
      requestEnrollment: "提交审批申请",
      requestingEnrollment: "正在申请...",
      issueApproved: "审批后发 token",
      issuingApproved: "正在发放...",
      approveRequest: "批准",
      rejectRequest: "拒绝",
      approvalRequestTitle: "审批式接入申请",
      noApprovalRequests: "暂无远程接入审批申请。",
      requestCreated: "已创建接入申请",
      rotateToken: "轮换",
      rotatingToken: "正在轮换...",
      revokeToken: "吊销",
      revokingToken: "正在吊销...",
      scopePresets: "权限预设",
      presetWorker: "Worker",
      presetObserver: "只读观测",
      presetApproval: "审批请求",
      presetFull: "完整权限",
      agentId: "Agent ID",
      agentName: "显示名称",
      runtime: "运行时",
      workspace: "工作区",
      ttlDays: "有效天数",
      heartbeat: "心跳超时",
      scopes: "权限范围",
      tokenShownOnce: "请现在复制 token。页面不会再次显示原始 token。",
      launchPacket: "远程启动指引",
      envSetup: "环境变量",
      installCommand: "安装",
      verifyCommand: "自检",
      preflightCommand: "预检",
      sessionCommand: "换取短期 Session",
      heartbeatCommand: "心跳",
      runOnceCommand: "单轮运行",
      runLoopCommand: "常驻运行",
      launchdTemplate: "launchd 模板",
      systemdTemplate: "systemd 模板",
      fallbackCommand: "仓库内备用",
      recentEnrollments: "最近接入记录",
      recentSessions: "最近短期 Session",
      lastHeartbeat: "最近心跳",
      lastUsed: "最近使用",
      expires: "过期时间",
      tokenId: "Token",
      sessionId: "Session",
      parentToken: "父 token",
      revokeSession: "吊销 session",
      revokingSession: "正在吊销 session...",
      noEnrollments: "还没有远程接入记录。",
      noSessions: "还没有短期 session。",
      operatorTitle: "运营就绪",
      operatorSummary: "把这一页当成一人公司的 AI 团队控制塔：派活、运行本地 worker、接入远程机器、恢复卡住任务，全都进入 MIS 账本。",
      modeLocalTitle: "本地 worker 循环",
      modeLocalBody: "mock 用于安全 dry-run；Hermes 和 OpenClaw 按钮需要显式确认真跑，并写入 run/tool/eval/audit 证据。",
      modeLiveTitle: "真实运行派发",
      modeLiveBody: "Hermes/OpenClaw adapter 执行的是普通 MIS 任务，不是孤立演示；结果会摘要、hash，并记录到账本。",
      modeRemoteTitle: "远程 agent 接入",
      modeRemoteBody: "其他电脑或服务器用带权限范围的接入 token、短期 session、心跳和工作区绑定权限接入。",
      modeRecoveryTitle: "恢复队列",
      modeRecoveryBody: "卡住的运行中 worker 任务可以释放回 planned；关联 run 会标记 blocked 并留下审计证据。",
      adapterRoutesTitle: "Adapter 路由",
      adapterRoutesSummary: "agent worker 真跑前使用的只读选路状态。",
      recommendedAdapter: "推荐",
      trustStatus: "信任",
      targetResource: "目标",
      nextAction: "下一步",
      liveReady: "可真跑",
      notLiveReady: "不可真跑",
      statusRunning: "运行中",
      statusReady: "就绪",
      statusConfirm: "需确认",
      statusAttention: "需处理",
      statusClear: "正常",
      statusSetup: "待配置",
    },
  });
  const operatorReadiness = [
    {
      title: copy.modeLocalTitle,
      body: copy.modeLocalBody,
      status: runningDaemons > 0 ? "running" : "ready",
      label: runningDaemons > 0 ? copy.statusRunning : copy.statusReady,
      attention: false,
      meta: `${runningDaemons}/${workerStatus?.worker_count ?? 0} ${copy.workers}`,
    },
    {
      title: copy.modeLiveTitle,
      body: copy.modeLiveBody,
      status: liveReadyAdapters.length > 0 ? "ready" : "unavailable",
      label: liveReadyAdapters.length > 0 ? copy.statusReady : copy.statusAttention,
      attention: liveReadyAdapters.length === 0 || unavailableAdapters.length > 0 || blockedAdapters.length > 0,
      meta: `${liveReadyAdapters.length} ${copy.liveReady} · ${copy.recommendedAdapter}: ${recommendedAdapter}`,
    },
    {
      title: copy.modeRemoteTitle,
      body: copy.modeRemoteBody,
      status: gatewayReady && activeEnrollments > 0 ? "ready" : "planned",
      label: gatewayReady && activeEnrollments > 0 ? copy.statusReady : copy.statusSetup,
      attention: !gatewayReady || staleEnrollments > 0,
      meta: `${activeEnrollments} ${copy.activeEnrollments} · ${activeSessions} ${copy.activeSessions}`,
    },
    {
      title: copy.modeRecoveryTitle,
      body: copy.modeRecoveryBody,
      status: stuckWorkerCount > 0 || stuckWorkflowJobCount > 0 ? "blocked" : "pass",
      label: stuckWorkerCount > 0 || stuckWorkflowJobCount > 0 ? copy.statusAttention : copy.statusClear,
      attention: stuckWorkerCount > 0 || stuckWorkflowJobCount > 0,
      meta: `${stuckWorkerCount} ${copy.stuckTasks} · ${stuckWorkflowJobCount} ${copy.workflowRecovery}`,
    },
  ];
  const adapterRouteCards = WORKER_ADAPTERS.map((adapter) => {
    const item = adapterReadiness?.adapters?.[adapter] || {
      adapter: adapter as WorkerAdapterName,
      ok: false,
      readiness: "unknown",
      trust_status: "unknown",
      target_resource: "—",
      recommended_action: "agentops worker readiness",
      checks: {},
    };
    const liveReady = item.readiness === "ready" && adapter !== "mock";
    const attention = ["unavailable", "blocked"].includes(item.readiness);
    const checks = item.checks || {};
    const checkSummary = adapter === "hermes"
      ? `api=${String(checks.api_listening ?? "—")} · port=${String(checks.api_port ?? "—")}`
      : adapter === "openclaw"
        ? `bin=${String(checks.binary_exists ?? "—")} · agents=${String(checks.agents_count ?? "—")}`
        : "local mock worker";
    return { item, liveReady, attention, checkSummary };
  });
  const integrationInboxFilters = [
    { bucket: "all", label: copy.inboxAll, count: integrationInboxSummary?.total ?? 0 },
    { bucket: "ready_for_review", label: copy.readyForReview, count: integrationInboxSummary?.ready_for_review ?? 0 },
    { bucket: "still_running", label: copy.stillRunning, count: integrationInboxSummary?.still_running ?? 0 },
    { bucket: "blocked", label: copy.blockedItems, count: integrationInboxSummary?.blocked ?? 0 },
    { bucket: "late_or_stale", label: copy.lateOrStale, count: integrationInboxSummary?.late_or_stale ?? 0 },
    { bucket: "needs_memory_review", label: copy.memoryReview, count: integrationInboxSummary?.needs_memory_review ?? 0 },
  ];
  const isCloseEvidenceGapCommand = (action: string) => action.startsWith("agentops operator close-evidence-gap --run-id ");
  const actionQueueCandidateScore = (action: string) => isCloseEvidenceGapCommand(action) ? 100 : 0;
  const actionQueueCandidates = [
    ...operatorPlanActions.map((item) => ({
      id: `operator:${item.action_id}`,
      action: item.command,
      source: `${copy.operatorTitle} · ${item.lane}`,
      status: item.severity || operatorActionPlan?.status || "attention",
      operatorAction: item,
    })),
    ...recommendedActions.map((action, index) => ({
      id: `fleet:${index}:${action}`,
      action,
      source: copy.overallFleetHealth,
      status: fleetHealth?.overall || "attention",
    })),
    ...integrationInboxActions.map((action, index) => ({
      id: `inbox:${index}:${action}`,
      action,
      source: copy.integrationInboxTitle,
      status: integrationInbox?.status || "attention",
    })),
    ...synthesisLifecycleActions.map((action, index) => ({
      id: `synthesis:${index}:${action}`,
      action,
      source: copy.synthesisLoop,
      status: synthesisLifecycle?.status || "attention",
    })),
    ...localReadinessActions.map((action, index) => ({
      id: `local:${index}:${action}`,
      action,
      source: copy.localReadinessTitle,
      status: localReadiness?.status || "attention",
    })),
  ].filter((candidate, index, list) => (
    candidate.action &&
    list.findIndex(item => item.action === candidate.action) === index
  )).sort((left, right) => actionQueueCandidateScore(right.action) - actionQueueCandidateScore(left.action)).slice(0, 8);
  const actionQueueKey = actionQueueCandidates.map(item => item.id).join("|");
  const orderedActionQueue = [
    ...actionQueueOrder.map(id => actionQueueCandidates.find(item => item.id === id)).filter(Boolean),
    ...actionQueueCandidates.filter(item => !actionQueueOrder.includes(item.id)),
  ].slice(0, 8);
  const visibleActionQueue = orderedActionQueue.filter(Boolean) as typeof actionQueueCandidates;

  useEffect(() => {
    const nextIds = actionQueueCandidates.map(item => item.id);
    setActionQueueOrder(prev => {
      const kept = prev.filter(id => nextIds.includes(id));
      const added = nextIds.filter(id => !kept.includes(id));
      return [...kept, ...added].slice(0, 8);
    });
  }, [actionQueueKey]);

  const moveActionQueueItem = (activeId: string, targetId: string) => {
    const ids = orderedActionQueue.map(item => item?.id).filter(Boolean) as string[];
    const activeIndex = ids.indexOf(activeId);
    const targetIndex = ids.indexOf(targetId);
    if (activeIndex < 0 || targetIndex < 0 || activeIndex === targetIndex) return;
    const next = [...ids];
    const [moved] = next.splice(activeIndex, 1);
    next.splice(targetIndex, 0, moved);
    setActionQueueOrder(next);
  };

  const nudgeActionQueueItem = (id: string, direction: -1 | 1) => {
    const ids = orderedActionQueue.map(item => item?.id).filter(Boolean) as string[];
    const index = ids.indexOf(id);
    const targetIndex = index + direction;
    if (index < 0 || targetIndex < 0 || targetIndex >= ids.length) return;
    const next = [...ids];
    const [moved] = next.splice(index, 1);
    next.splice(targetIndex, 0, moved);
    setActionQueueOrder(next);
  };

  const readCommandFlag = (command: string, flag: string) => {
    const parts = command.split(/\s+/).filter(Boolean);
    const index = parts.indexOf(flag);
    if (index < 0 || index + 1 >= parts.length) return "";
    return parts[index + 1] || "";
  };

  const closeGapDetailsForAction = (item: (typeof actionQueueCandidates)[number]) => {
    const command = item.action || "";
    if (!isCloseEvidenceGapCommand(command)) return null;
    const evidence = item.operatorAction?.evidence || {};
    const readEvidence = (key: string) => {
      const value = evidence[key];
      return typeof value === "string" ? value : "";
    };
    const decisionRaw = readCommandFlag(command, "--decision") || "accepted_remediation";
    const decision = decisionRaw === "waived" || decisionRaw === "reopen" ? decisionRaw : "accepted_remediation";
    const runId = readCommandFlag(command, "--run-id") || readEvidence("run_id");
    if (!runId) return null;
    return {
      runId,
      decision,
      synthesisArtifactId: readCommandFlag(command, "--synthesis-artifact-id") || readEvidence("remediation_synthesis_artifact_id"),
      remediationTaskId: readCommandFlag(command, "--remediation-task-id") || readEvidence("remediation_task_id"),
    };
  };

  const evidenceGapDecisionDetails = (gap: ExecutionEvidenceGapItem, decision: "accepted_remediation" | "reopen" = "accepted_remediation") => ({
    runId: gap.run_id,
    decision,
    synthesisArtifactId: gap.remediation_synthesis_artifact_id || undefined,
    remediationTaskId: gap.remediation_task_id || undefined,
  });

  const evidenceClosureRows = operatorEvidenceGaps
    .filter((gap) => gap.remediation_synthesis_status || gap.gap_decision_status || isCloseEvidenceGapCommand(gap.command || ""))
    .sort((left, right) => {
      const score = (gap: ExecutionEvidenceGapItem) => (
        gap.gap_decision_status === "closed" ? 30 :
        isCloseEvidenceGapCommand(gap.command || "") ? 50 :
        gap.remediation_synthesis_status === "promoted" ? 40 :
        0
      );
      return score(right) - score(left);
    })
    .slice(0, 4);

  const taskIntakeRows = [...taskIntakeItems]
    .sort((left, right) => {
      const score = (item: TaskIntakeChecklistItem) => item.severity === "blocked" ? 3 : item.severity === "attention" ? 2 : 1;
      return score(right) - score(left) || right.priority_score - left.priority_score;
    })
    .slice(0, 4);
  const blockedIntakeRows = taskIntakeItems.filter(item => item.severity === "blocked");
  const primaryBlockedIntake = blockedIntakeRows[0];
  const workerStartBlocked = Boolean(primaryBlockedIntake);

  const copyIntakeCommand = async (command: string) => {
    if (!command) return;
    try {
      await navigator.clipboard?.writeText(command);
      setCopiedIntakeCommand(command);
      window.setTimeout(() => setCopiedIntakeCommand(current => current === command ? null : current), 1800);
    } catch {
      setCopiedIntakeCommand(null);
    }
  };

  const renderActiveIntakeGate = () => {
    if (!primaryBlockedIntake) return null;
    const taskRoute = primaryBlockedIntake.ui_route || `/admin/tasks/${primaryBlockedIntake.task_id}`;
    const gateIds = primaryBlockedIntake.failed_gate_ids.join(", ") || "gate";
    const commandCopied = copiedIntakeCommand === primaryBlockedIntake.command;

    return (
      <div className="rounded-lg p-3 mt-3" style={{ background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.22)" }}>
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <AlertTriangle size={13} style={{ color: "#F87171" }} />
              <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{copy.activeIntakeGate}</div>
            </div>
            <div className="text-[10px] mt-1" style={{ color: "var(--mis-muted)" }}>{copy.activeIntakeSummary}</div>
            <div className="text-[10px] mt-1" style={{ color: "#F87171" }}>{copy.workerStartBlockedHint}</div>
            <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-dim)" }}>{primaryBlockedIntake.title} · {gateIds}</div>
          </div>
          <div className="flex items-center gap-2 shrink-0 flex-wrap">
            <StatusBadge status="blocked" label={String(blockedIntakeRows.length)} />
            <Link to={taskRoute} className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>
              <Inbox size={11} />
              {copy.openTask}
            </Link>
            {primaryBlockedIntake.command && (
              <button
                onClick={() => void copyIntakeCommand(primaryBlockedIntake.command)}
                className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded"
                style={{ background: "rgba(251,191,36,0.10)", color: "var(--mis-warning)", border: "1px solid rgba(251,191,36,0.20)" }}
              >
                <Copy size={11} />
                {commandCopied ? copy.copiedCommand : copy.copyCommand}
              </button>
            )}
          </div>
        </div>
        <div className="text-[10px] mt-2 truncate" style={{ color: "var(--mis-cyan)" }}>{copy.nextAction}: {primaryBlockedIntake.command}</div>
      </div>
    );
  };

  const submitEvidenceGapDecision = async (details: {
    runId: string;
    decision: "accepted_remediation" | "waived" | "reopen";
    synthesisArtifactId?: string;
    remediationTaskId?: string;
  }) => {
    const actionKey = `${details.decision === "reopen" ? "reopen-gap" : "close-gap"}:${details.runId}`;
    setDispatching(actionKey);
    setDispatchResult(null);
    try {
      const result = await closeExecutionEvidenceGap({
        run_id: details.runId,
        decision: details.decision,
        synthesis_artifact_id: details.synthesisArtifactId || undefined,
        remediation_task_id: details.remediationTaskId || undefined,
        confirm_close: true,
      });
      const label = details.decision === "reopen" ? copy.reopenEvidenceGap : copy.closeEvidenceGap;
      setDispatchResult(`${label}: ${result.status} · ${result.run_id || details.runId}`);
      await refresh();
    } catch (err) {
      setDispatchResult(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const closeEvidenceGapFromQueue = async (item: (typeof actionQueueCandidates)[number]) => {
    const details = closeGapDetailsForAction(item);
    if (!details) return;
    await submitEvidenceGapDecision(details);
  };

  const updateCustomerTaskText = (field: "title" | "description", value: string) => {
    setCustomerTaskForm(prev => ({ ...prev, [field]: value }));
  };

  const updateCustomerTaskAdapter = (adapter: (typeof WORKER_ADAPTERS)[number]) => {
    setCustomerTaskForm(prev => ({ ...prev, adapter }));
  };

  const updateLoopLaneForm = (field: keyof typeof loopLaneForm, value: string) => {
    setLoopLaneForm(prev => ({ ...prev, [field]: value }));
  };

  const updateCommanderPlannerForm = (field: keyof typeof commanderPlannerForm, value: string) => {
    setCommanderPlannerForm(prev => ({ ...prev, [field]: value }));
  };

  const runCommanderPlanner = async (confirmCreate: boolean) => {
    setCommanderPlannerBusy(true);
    setCommanderPlannerError(null);
    try {
      const goal = commanderPlannerForm.goal.trim() || (locale === "zh"
        ? "用 AgentOps MIS 拆分并行 AI 团队工作包。"
        : "Use AgentOps MIS to split parallel AI-team work packages.");
      const maxPackages = Math.min(Math.max(Number(commanderPlannerForm.max_packages) || 5, 1), 8);
      const result = await planCommanderWorkPackages({
        goal,
        max_packages: maxPackages,
        confirm_create: confirmCreate,
      });
      setCommanderPlannerResult(result);
      setDispatchResult(`${result.status}: ${result.created_count || result.planned_count} · ${result.plan_id}`);
      if (confirmCreate) {
        await refresh();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setCommanderPlannerError(message);
      setDispatchResult(message);
    } finally {
      setCommanderPlannerBusy(false);
    }
  };

  const dispatchCommanderPackage = async (taskId: string, adapter: (typeof WORKER_ADAPTERS)[number], confirmRun = false) => {
    const actionId = `commander-${adapter}-${taskId}`;
    setDispatching(actionId);
    setDispatchResult(null);
    try {
      const result = await dispatchCommanderWorkPackage({
        task_id: taskId,
        adapter,
        confirm_run: confirmRun,
      });
      setDispatchResult(`${copy.dispatchPackage}: ${result.ok ? "ok" : result.reason || "failed"} · ${result.run_id || result.task_id}`);
      await refresh();
    } catch (err) {
      setDispatchResult(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const dispatchCommanderPlannedBatch = async () => {
    const plannedTaskIds = commanderPackageRows
      .filter(pkg => pkg.package_status === "planned" || pkg.status === "planned")
      .slice(0, 5)
      .map(pkg => pkg.task_id)
      .filter(Boolean);
    if (plannedTaskIds.length === 0) {
      setDispatchResult(locale === "zh" ? "没有可排队的 planned 工作包" : "No planned work packages to queue");
      return;
    }
    setDispatching("commander-batch-mock");
    setDispatchResult(null);
    try {
      const result = await dispatchCommanderWorkPackageBatch({
        task_ids: plannedTaskIds,
        adapter: "mock",
        status: "planned",
        limit: plannedTaskIds.length,
      });
      setDispatchResult(`${copy.dispatchBatchMock}: ${result.ok ? "queued" : result.reason || "failed"} · ${result.job_ids.length} jobs`);
      await refresh();
    } catch (err) {
      setDispatchResult(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const synthesizeCommanderReadyPackages = async () => {
    const readyTaskIds = commanderPackageRows
      .filter(pkg => pkg.package_status === "ready_for_review")
      .slice(0, 10)
      .map(pkg => pkg.task_id)
      .filter(Boolean);
    if (readyTaskIds.length === 0) {
      setDispatchResult(locale === "zh" ? "没有 ready_for_review 工作包可合并" : "No ready_for_review work packages to synthesize");
      return;
    }
    setDispatching("commander-synthesize");
    setDispatchResult(null);
    try {
      const result = await synthesizeCommanderWorkPackages({
        task_ids: readyTaskIds,
        status: "ready_for_review",
        limit: readyTaskIds.length,
        confirm_create: true,
      });
      const reviewGate = result.approval_id ? ` · approval ${result.approval_id}` : "";
      if (result.artifact_id) {
        setLastSynthesis({ artifactId: result.artifact_id, approvalId: result.approval_id });
      }
      setDispatchResult(`${copy.synthesizePackages}: ${result.ok ? result.artifact_id || "created" : "failed"} · ${result.package_count || readyTaskIds.length} packages${reviewGate}`);
      await refresh();
    } catch (err) {
      setDispatchResult(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const promoteLastCommanderSynthesis = async () => {
    if (!lastSynthesis?.artifactId) {
      setDispatchResult(locale === "zh" ? "还没有可晋升的合并报告" : "No synthesis report to promote yet");
      return;
    }
    setDispatching("commander-promote-synthesis");
    setDispatchResult(null);
    try {
      const result = await promoteCommanderSynthesis({
        artifact_id: lastSynthesis.artifactId,
        approval_id: lastSynthesis.approvalId || undefined,
        mode: "both",
        confirm_promote: true,
      });
      setSynthesisPromotion(result);
      setDispatchResult(`${copy.promoteSynthesis}: ${result.status} · memory ${result.memory_id || "n/a"} · delivery ${result.delivery_artifact_id || "n/a"}`);
      await refresh();
    } catch (err) {
      setDispatchResult(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const runLoopLane = async (resume = false) => {
    setLoopLaneBusy(true);
    setLoopLaneError(null);
    setLoopLaneResult(null);
    try {
      const topic = loopLaneForm.topic.trim() || (locale === "zh"
        ? "请审视 AgentOps MIS 下一步产品闭环。"
        : "Review the next AgentOps MIS product closure.");
      const result = await runHermesOpenClawLoopWorkflow({
        topic,
        loop_id: loopLaneForm.loop_id.trim() || undefined,
        rounds: 1,
        mode: "dry-run",
        resume,
        request_timeout: 15,
        max_agent_attempts: 1,
        retry_delay_sec: 0,
        order: ["hermes", "openclaw"],
      });
      setLoopLaneResult(result);
      if (result.loop_id && !loopLaneForm.loop_id.trim()) {
        setLoopLaneForm(prev => ({ ...prev, loop_id: result.loop_id || prev.loop_id }));
      }
      setDispatchResult(`loop: ${result.ok ? "ok" : "blocked"} · ${result.loop_id || "—"}`);
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLoopLaneError(message);
      setDispatchResult(message);
    } finally {
      setLoopLaneBusy(false);
    }
  };

  const runCustomerTask = async (confirmRun: boolean) => {
    setCustomerTaskBusy(true);
    setCustomerTaskError(null);
    setCustomerTaskResult(null);
    setCustomerTaskJob(null);
    try {
      const title = customerTaskForm.title.trim() || (locale === "zh" ? "客户 AI 任务" : "Customer AI task");
      const result = await runCustomerWorkerTaskWorkflow({
        adapter: customerTaskForm.adapter,
        confirm_run: confirmRun,
        title,
        description: customerTaskForm.description.trim() || title,
        acceptance_criteria: locale === "zh"
          ? "Worker 必须创建 run/tool/eval/audit 证据，并返回可展示的任务摘要。"
          : "Worker must create run/tool/eval/audit evidence and return a demonstrable task summary.",
        priority: "high",
        risk_level: customerTaskForm.adapter === "mock" ? "low" : "medium",
        selected_agent_ids: [],
        workflow_kind: "ui_agent_workspace_customer_dispatch",
      });
      setCustomerTaskResult(result);
      setDispatchResult(`${customerTaskForm.adapter}: ${result.ok ? "ok" : result.dry_run ? "dry-run" : "failed"} · ${result.run_id || result.task_id}`);
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setCustomerTaskError(message);
      setDispatchResult(message);
    } finally {
      setCustomerTaskBusy(false);
    }
  };

  const submitCustomerTaskAsync = async () => {
    setCustomerTaskBusy(true);
    setCustomerTaskError(null);
    setCustomerTaskResult(null);
    setCustomerTaskJob(null);
    try {
      const title = customerTaskForm.title.trim() || (locale === "zh" ? "客户 AI 任务" : "Customer AI task");
      const result = await submitCustomerWorkerTaskJob({
        adapter: customerTaskForm.adapter,
        confirm_run: customerTaskForm.adapter !== "mock",
        title,
        description: customerTaskForm.description.trim() || title,
        acceptance_criteria: locale === "zh"
          ? "Worker 必须通过异步 Job 创建 run/tool/eval/audit/artifact/memory/approval 证据。"
          : "Worker must create run/tool/eval/audit/artifact/memory/approval evidence through the async job.",
        priority: "high",
        risk_level: customerTaskForm.adapter === "mock" ? "low" : "medium",
        selected_agent_ids: [],
        workflow_kind: "ui_agent_workspace_customer_dispatch_async",
      });
      setCustomerTaskJob(result.job);
      setDispatchResult(`job: ${result.job_id} · ${result.job.status}`);
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setCustomerTaskError(message);
      setDispatchResult(message);
    } finally {
      setCustomerTaskBusy(false);
    }
  };

  const markStuckWorkflowJobFailed = async (jobId: string) => {
    setWorkflowJobAction(jobId);
    setWorkflowJobResult(null);
    try {
      const result = await markWorkflowJobFailed(
        jobId,
        locale === "zh" ? "操作台标记卡住 workflow job 为 failed" : "Operator marked stuck workflow job as failed",
      );
      setWorkflowJobResult(`${jobId}: ${result.marked_failed ? "failed" : result.reason || "not changed"}`);
      await refresh();
    } catch (err) {
      setWorkflowJobResult(err instanceof Error ? err.message : String(err));
    } finally {
      setWorkflowJobAction(null);
    }
  };

  const runWorkerOnce = async (adapter: "mock" | "hermes" | "openclaw") => {
    setDispatching(adapter);
    setDispatchResult(null);
    try {
      const result = await dispatchLocalWorkerOnce({
        adapter,
        confirm_run: adapter !== "mock",
        title: locale === "zh" ? `${adapter} worker 页面派发任务` : `${adapter} worker UI dispatch task`,
        description: locale === "zh"
          ? "从 AI 员工页面触发一次本地 worker，验证普通任务可以被自动执行并回写 MIS 账本。"
          : "Trigger one local worker run from the AI Employees page and write evidence back to the MIS ledger.",
        acceptance_criteria: "Worker must complete the task and write run/tool/eval/audit.",
      });
      const runId = result.run_id || result.worker_result?.results?.[0]?.run_id || result.task_id;
      setLastWorkerDispatch(result);
      setDispatchResult(`${adapter}: ${result.ok ? "ok" : "failed"} · ${runId}`);
      await refresh();
    } catch (err) {
      setDispatchResult(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const startDaemon = async (adapter: "mock" | "hermes" | "openclaw") => {
    setDispatching(`start-${adapter}`);
    setDispatchResult(null);
    try {
      const result = await startLocalWorkerDaemon({
        adapter,
        confirm_run: adapter !== "mock",
        poll_interval: 2,
        max_tasks: 0,
      });
      if (!result.ok && result.task_intake) {
        const action = result.recommended_action || result.task_intake.next_actions?.[0] || copy.activeIntakeGate;
        setDispatchResult(`${adapter} daemon: blocked · ${action}`);
        return;
      }
      const pid = result.daemon?.pid ? `pid ${result.daemon.pid}` : result.already_running ? "already running" : "started";
      setDispatchResult(`${adapter} daemon: ${result.ok ? "ok" : "failed"} · ${pid}`);
      await refresh();
    } catch (err) {
      setDispatchResult(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const restartDaemon = async (adapter: "mock" | "hermes" | "openclaw") => {
    setDispatching(`restart-${adapter}`);
    setDispatchResult(null);
    try {
      const result = await restartLocalWorkerDaemon({
        adapter,
        confirm_run: adapter !== "mock",
        poll_interval: 2,
        max_tasks: 0,
      });
      if (!result.ok && result.task_intake) {
        const action = result.recommended_action || result.task_intake.next_actions?.[0] || copy.activeIntakeGate;
        setDispatchResult(`${adapter} restart: blocked · ${action}`);
        return;
      }
      const pid = result.daemon?.pid ? `pid ${result.daemon.pid}` : "restart requested";
      setDispatchResult(`${adapter} restart: ${result.ok ? "ok" : "failed"} · ${pid}`);
      await refresh();
    } catch (err) {
      setDispatchResult(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const stopDaemons = async () => {
    setDispatching("stop-daemons");
    setDispatchResult(null);
    try {
      const result = await stopLocalWorkerDaemon("all");
      setDispatchResult(`daemon stop: ${result.ok ? "ok" : "failed"}`);
      await refresh();
    } catch (err) {
      setDispatchResult(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const releaseStuckTask = async (taskId: string) => {
    setDispatching(`release-${taskId}`);
    setDispatchResult(null);
    try {
      const result = await releaseWorkerTask({
        task_id: taskId,
        reason: locale === "zh" ? "操作台释放卡住 worker 任务" : "Operator released stuck worker task",
      });
      setDispatchResult(`${taskId}: ${result.released ? "released" : "not released"} · runs ${result.released_runs.length}`);
      await refresh();
    } catch (err) {
      setDispatchResult(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const runFleetHygiene = async (apply: boolean) => {
    setHygieneBusy(true);
    setHygieneError(null);
    try {
      const result = apply
        ? await applyWorkerFleetHygiene({
            threshold_sec: 900,
            enrollment_age_sec: 900,
            limit: 10,
            release_reason: locale === "zh" ? "操作台 Fleet Hygiene 清理" : "Operator fleet hygiene cleanup",
          })
        : await loadWorkerFleetHygiene({ threshold_sec: 900, enrollment_age_sec: 900, limit: 10 });
      setHygieneResult(result);
      await refresh();
    } catch (err) {
      setHygieneError(err instanceof Error ? err.message : String(err));
    } finally {
      setHygieneBusy(false);
    }
  };

  const handleReviewDecision = async (item: ReviewQueuePayload["review_items"][number], decision: "approve" | "reject") => {
    const actionKey = `${item.item_type}-${item.item_id}-${decision}`;
    setReviewAction(actionKey);
    setReviewResult(null);
    try {
      if (item.item_type === "approval") {
        await decideApproval(item.item_id, decision);
      } else if (item.item_type === "memory_candidate") {
        await decideMemory(item.item_id, decision);
      } else if (item.item_type === "evaluation_case_candidate") {
        await decideEvaluationCase(item.item_id, decision);
      } else {
        setReviewResult(`${copy.reviewActionResult}: ${item.item_type} ${item.item_id}`);
        return;
      }
      setReviewResult(`${copy.reviewActionResult}: ${item.item_type} ${item.item_id} -> ${decision}`);
      await refresh();
    } catch (err) {
      setReviewResult(err instanceof Error ? err.message : String(err));
    } finally {
      setReviewAction(null);
    }
  };

  const updateEnrollmentForm = (field: keyof typeof enrollmentForm, value: string) => {
    setEnrollmentForm(prev => ({ ...prev, [field]: value }));
  };

  const scopeList = enrollmentForm.scopes
    .split(",")
    .map(item => item.trim())
    .filter(Boolean);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      if (scopeList.length === 0) {
        setEnrollmentPolicy(null);
        return;
      }
      try {
        const result = await previewAgentGatewayEnrollmentPolicy({
          workspace_id: enrollmentForm.workspace_id,
          runtime_type: enrollmentForm.runtime_type,
          scopes: scopeList,
        });
        if (!cancelled) {
          setEnrollmentPolicy(result);
          setEnrollmentPolicyError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setEnrollmentPolicyError(err instanceof Error ? err.message : String(err));
        }
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [enrollmentForm.workspace_id, enrollmentForm.runtime_type, enrollmentForm.scopes]);

  const presetLabel = (id: string) => {
    if (id === "worker") return copy.presetWorker;
    if (id === "observer") return copy.presetObserver;
    if (id === "approval") return copy.presetApproval;
    return copy.presetFull;
  };

  const createEnrollment = async () => {
    setEnrollmentAction("create");
    setEnrollmentResult(null);
    setCreatedToken(null);
    try {
      const result = await createAgentGatewayEnrollment({
        agent_id: enrollmentForm.agent_id.trim(),
        name: enrollmentForm.name.trim(),
        runtime_type: enrollmentForm.runtime_type,
        workspace_id: enrollmentForm.workspace_id.trim(),
        label: `${enrollmentForm.name.trim()} enrollment`,
        scopes: scopeList,
        ttl_days: Number(enrollmentForm.ttl_days) || 30,
        heartbeat_timeout_sec: Number(enrollmentForm.heartbeat_timeout_sec) || 300,
      });
      setCreatedToken(result);
      setEnrollmentResult(`${result.agent_id}: ${result.token_id}`);
      await refresh();
    } catch (err) {
      setEnrollmentResult(err instanceof Error ? err.message : String(err));
    } finally {
      setEnrollmentAction(null);
    }
  };

  const requestEnrollment = async () => {
    setEnrollmentAction("request");
    setEnrollmentResult(null);
    setCreatedToken(null);
    setCreatedRequest(null);
    try {
      const result = await requestAgentGatewayEnrollment({
        agent_id: enrollmentForm.agent_id.trim(),
        name: enrollmentForm.name.trim(),
        runtime_type: enrollmentForm.runtime_type,
        workspace_id: enrollmentForm.workspace_id.trim(),
        label: `${enrollmentForm.name.trim()} enrollment request`,
        scopes: scopeList,
        ttl_days: Number(enrollmentForm.ttl_days) || 30,
        heartbeat_timeout_sec: Number(enrollmentForm.heartbeat_timeout_sec) || 300,
        reason: locale === "zh"
          ? "远程 worker 需要带范围权限来处理已分配的 MIS 任务。"
          : "Remote worker needs scoped access to process assigned MIS tasks.",
      });
      setCreatedRequest(result);
      setIssueApprovalId(result.approval.approval_id);
      setEnrollmentResult(`${copy.requestCreated}: ${result.request.request_id}`);
      await refresh();
    } catch (err) {
      setEnrollmentResult(err instanceof Error ? err.message : String(err));
    } finally {
      setEnrollmentAction(null);
    }
  };

  const issueApprovedEnrollment = async (approvalId = issueApprovalId) => {
    setEnrollmentAction(`issue-${approvalId || "manual"}`);
    setEnrollmentResult(null);
    setCreatedToken(null);
    try {
      const result = await issueApprovedAgentGatewayEnrollment({
        approval_id: approvalId.trim(),
        ttl_days: Number(enrollmentForm.ttl_days) || 30,
        heartbeat_timeout_sec: Number(enrollmentForm.heartbeat_timeout_sec) || 300,
        label: `${enrollmentForm.name.trim()} approved enrollment`,
      });
      setCreatedToken(result);
      setEnrollmentResult(`${result.agent_id}: ${result.token_id}`);
      await refresh();
    } catch (err) {
      setEnrollmentResult(err instanceof Error ? err.message : String(err));
    } finally {
      setEnrollmentAction(null);
    }
  };

  const decideEnrollmentApproval = async (approvalId: string, decision: "approve" | "reject") => {
    setEnrollmentAction(`${decision}-${approvalId}`);
    setEnrollmentResult(null);
    try {
      const result = await decideApproval(approvalId, decision);
      setIssueApprovalId(approvalId);
      setEnrollmentResult(`${approvalId}: ${result.decision}`);
      await refresh();
    } catch (err) {
      setEnrollmentResult(err instanceof Error ? err.message : String(err));
    } finally {
      setEnrollmentAction(null);
    }
  };

  const revokeEnrollment = async (tokenId: string) => {
    setEnrollmentAction(`revoke-${tokenId}`);
    setEnrollmentResult(null);
    try {
      const result = await revokeAgentGatewayEnrollment({ token_id: tokenId });
      const sessionNote = result.sessions_revoked ? ` · sessions ${result.sessions_revoked}` : "";
      setEnrollmentResult(`revoked: ${result.tokens.join(", ") || result.revoked}${sessionNote}`);
      await refresh();
    } catch (err) {
      setEnrollmentResult(err instanceof Error ? err.message : String(err));
    } finally {
      setEnrollmentAction(null);
    }
  };

  const revokeSession = async (sessionId: string) => {
    setEnrollmentAction(`revoke-session-${sessionId}`);
    setEnrollmentResult(null);
    try {
      const result = await revokeAgentGatewaySession({ session_id: sessionId });
      setEnrollmentResult(`session revoked: ${result.sessions.join(", ") || result.revoked}`);
      await refresh();
    } catch (err) {
      setEnrollmentResult(err instanceof Error ? err.message : String(err));
    } finally {
      setEnrollmentAction(null);
    }
  };

  const rotateEnrollment = async (tokenId: string) => {
    setEnrollmentAction(`rotate-${tokenId}`);
    setEnrollmentResult(null);
    setCreatedToken(null);
    try {
      const result = await rotateAgentGatewayEnrollment({
        token_id: tokenId,
        ttl_days: Number(enrollmentForm.ttl_days) || 30,
        heartbeat_timeout_sec: Number(enrollmentForm.heartbeat_timeout_sec) || 300,
      });
      setCreatedToken(result);
      setEnrollmentResult(`${result.agent_id}: ${result.rotated_from_token_id} -> ${result.token_id}`);
      await refresh();
    } catch (err) {
      setEnrollmentResult(err instanceof Error ? err.message : String(err));
    } finally {
      setEnrollmentAction(null);
    }
  };

  const eventText = (event: Record<string, unknown>, key: string, fallback = "—") => {
    const value = event[key];
    return value === null || value === undefined || value === "" ? fallback : String(value);
  };

  const formatAge = (ageSec?: number) => {
    const seconds = Number(ageSec || 0);
    if (!Number.isFinite(seconds) || seconds <= 0) return "—";
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
    return `${Math.round(seconds / 86400)}d`;
  };

  return (
    <div className="space-y-5 w-full">
      {/* Header */}
      <div>
        <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
          {copy.summary}
        </p>
        {loading && <p className="text-xs mt-2" style={{ color: "var(--mis-muted)" }}>{copy.loading}</p>}
        {error && <p className="text-xs mt-2" style={{ color: "#F87171" }}>{copy.backendUnavailable}: {error}</p>}
        <button onClick={refresh} className="mt-3 text-[11px] px-3 py-1.5 rounded" style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}>
          {copy.refresh}
        </button>
      </div>

      <div
        data-testid="commander-work-package-planner"
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col xl:flex-row xl:items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Bot size={14} style={{ color: "var(--mis-cyan)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.commanderPlannerTitle}</h2>
              <StatusBadge status={commanderPlannerResult?.status || "preview"} />
            </div>
            <p className="text-[11px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.commanderPlannerSummary}</p>
          </div>
          <div className="flex flex-wrap gap-1.5 xl:justify-end">
            <StatusBadge status="pass" label={`${copy.plannerSafety}: ${copy.yes}`} />
            <StatusBadge status={commanderPlannerResult?.safety.ledger_mutated ? "attention" : "pass"} label={`${copy.ledgerMutationProof}: ${commanderPlannerResult?.safety.ledger_mutated ? copy.yes : copy.no}`} />
            <StatusBadge status={commanderPlannerResult?.live_execution_performed ? "fail" : "pass"} label={`${copy.liveExecutionProof}: ${commanderPlannerResult?.live_execution_performed ? copy.no : copy.yes}`} />
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_160px_auto] gap-3 mt-4">
          <label className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>
            {copy.commanderGoal}
            <textarea
              value={commanderPlannerForm.goal}
              onChange={(event) => updateCommanderPlannerForm("goal", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-[11px] min-h-[76px]"
              style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)", color: "var(--mis-text)" }}
            />
          </label>
          <label className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>
            {copy.commanderMaxPackages}
            <input
              value={commanderPlannerForm.max_packages}
              onChange={(event) => updateCommanderPlannerForm("max_packages", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-[11px]"
              style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)", color: "var(--mis-text)" }}
            />
          </label>
          <div className="flex xl:flex-col gap-2 xl:justify-end">
            <button
              onClick={() => void runCommanderPlanner(false)}
              disabled={commanderPlannerBusy}
              className="inline-flex items-center justify-center gap-1.5 text-[11px] px-3 py-2 rounded disabled:opacity-50"
              style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
            >
              {commanderPlannerBusy ? <RefreshCw size={12} /> : <Inbox size={12} />}
              {commanderPlannerBusy ? copy.planning : copy.previewPlan}
            </button>
            <button
              onClick={() => void runCommanderPlanner(true)}
              disabled={commanderPlannerBusy}
              className="inline-flex items-center justify-center gap-1.5 text-[11px] px-3 py-2 rounded disabled:opacity-50"
              style={{ background: "rgba(45,212,191,0.12)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.22)" }}
            >
              {commanderPlannerBusy ? <RefreshCw size={12} /> : <CheckCircle2 size={12} />}
              {commanderPlannerBusy ? copy.planning : copy.createWorkPackages}
            </button>
          </div>
        </div>

        {commanderPlannerError && (
          <div className="text-[11px] rounded px-3 py-2 mt-3" style={{ color: "#F87171", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
            {commanderPlannerError}
          </div>
        )}

        {commanderPlannerResult && (
          <div className="mt-4 rounded-lg p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>
                  {copy.plannerResult}: {commanderPlannerResult.plan_id}
                </div>
                <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
                  {copy.plannedPackages}: {commanderPlannerResult.planned_count} · {copy.createdPackages}: {commanderPlannerResult.created_count}
                </div>
              </div>
              <StatusBadge status={commanderPlannerResult.created ? "completed" : "planned"} label={commanderPlannerResult.status} />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 mt-3">
              {commanderPlannerResult.work_packages.slice(0, 6).map((pkg) => (
                <div key={pkg.task_id} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{pkg.title}</div>
                    <StatusBadge status={pkg.status} label={pkg.lane_id} />
                  </div>
                  <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
                    {pkg.owner_agent_id} · {pkg.priority} · {pkg.risk_level}
                  </div>
                  <div className="text-[10px] mt-1 line-clamp-2" style={{ color: "var(--mis-dim)" }}>{pkg.scope}</div>
                  {commanderPlannerResult.created_task_ids.includes(pkg.task_id) && (
                    <Link to={`/admin/tasks/${pkg.task_id}`} className="inline-flex mt-2 text-[10px] px-2 py-1 rounded" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>
                      {copy.openTask}
                    </Link>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-4 rounded-lg p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>
                {copy.persistedPackages}
              </div>
              <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
                {copy.packageReadback}: {commanderWorkPackages?.summary.total ?? 0} · {copy.readOnlyProof}: {commanderWorkPackages?.safety.read_only ? copy.yes : copy.no}
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5 lg:justify-end">
              <button
                onClick={() => void dispatchCommanderPlannedBatch()}
                disabled={Boolean(dispatching) || commanderPlannedPackageCount === 0}
                className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded disabled:opacity-50"
                style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}
              >
                {dispatching === "commander-batch-mock" ? <RefreshCw size={10} /> : <Play size={10} />}
                {dispatching === "commander-batch-mock" ? copy.dispatching : `${copy.dispatchBatchMock} (${commanderPlannedPackageCount})`}
              </button>
              <button
                onClick={() => void synthesizeCommanderReadyPackages()}
                disabled={Boolean(dispatching) || commanderReadyPackageCount === 0}
                className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded disabled:opacity-50"
                style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}
              >
                {dispatching === "commander-synthesize" ? <RefreshCw size={10} /> : <CheckCircle2 size={10} />}
                {dispatching === "commander-synthesize" ? copy.dispatching : `${copy.synthesizePackages} (${commanderReadyPackageCount})`}
              </button>
              <button
                onClick={() => void promoteLastCommanderSynthesis()}
                disabled={Boolean(dispatching) || !lastSynthesis?.artifactId}
                className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded disabled:opacity-50"
                style={{ background: "rgba(245,158,11,0.10)", color: "var(--mis-warning)", border: "1px solid rgba(245,158,11,0.20)" }}
              >
                {dispatching === "commander-promote-synthesis" ? <RefreshCw size={10} /> : <Inbox size={10} />}
                {dispatching === "commander-promote-synthesis" ? copy.dispatching : copy.promoteSynthesis}
              </button>
              <StatusBadge status={commanderWorkPackages?.status || "unknown"} />
            </div>
          </div>
          {synthesisPromotion && (
            <div className="text-[10px] mt-2 rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
              {copy.promoteSynthesis}: {synthesisPromotion.status} · {synthesisPromotion.safety.ledger_mutated ? copy.yes : copy.no}
            </div>
          )}
          <div className="space-y-2 mt-3">
            {commanderPackageRows.length === 0 && (
              <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                {copy.noWorkflowJobs}
              </div>
            )}
            {commanderPackageRows.slice(0, 6).map((pkg) => (
              <div key={pkg.work_package_id || pkg.task_id} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{pkg.title}</div>
                      <StatusBadge status={pkg.package_status || pkg.status} label={pkg.lane_id || pkg.status} />
                    </div>
                    <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
                      {pkg.project_id || "project"} · {pkg.owner_agent_id || "agent"} · {copy.packageStatus}: {pkg.package_status}
                    </div>
                    <div className="text-[10px] mt-1 line-clamp-2" style={{ color: "var(--mis-dim)" }}>
                      {pkg.recommended_action || "agentops commander board"}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1.5 shrink-0">
                    {([
                      { adapter: "mock" as const, label: copy.dispatchPackageMock, confirm: false },
                      { adapter: "hermes" as const, label: copy.dispatchPackageHermes, confirm: true },
                      { adapter: "openclaw" as const, label: copy.dispatchPackageOpenClaw, confirm: true },
                    ]).map(action => {
                      const actionId = `commander-${action.adapter}-${pkg.task_id}`;
                      return (
                        <button
                          key={action.adapter}
                          onClick={() => void dispatchCommanderPackage(pkg.task_id, action.adapter, action.confirm)}
                          disabled={Boolean(dispatching)}
                          className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded disabled:opacity-50"
                          style={{ background: "rgba(129,140,248,0.10)", color: "var(--mis-purple)", border: "1px solid rgba(129,140,248,0.18)" }}
                        >
                          {dispatching === actionId ? <RefreshCw size={10} /> : <Play size={10} />}
                          {dispatching === actionId ? copy.dispatching : action.label}
                        </button>
                      );
                    })}
                    <Link to={`/admin/tasks/${pkg.task_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>{copy.openTask}</Link>
                    {pkg.latest_run?.run_id && (
                      <Link to={`/admin/runs/${pkg.latest_run.run_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}>{copy.openRun}</Link>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div
        data-testid="review-queue-panel"
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Inbox size={14} style={{ color: "var(--mis-warning)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.reviewQueueTitle}</h2>
              <StatusBadge status={reviewQueue?.status || "unknown"} />
            </div>
            <p className="text-[11px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.reviewQueueSummary}</p>
          </div>
          <div className="flex flex-wrap gap-1.5 lg:justify-end">
            <StatusBadge status={reviewQueueSafety?.read_only ? "pass" : "fail"} label={`${copy.reviewReadbackProof}: ${reviewQueueSafety?.read_only ? copy.yes : copy.no}`} />
            <StatusBadge status={reviewQueueSafety?.ledger_mutated === false ? "pass" : "fail"} label={`${copy.ledgerMutationProof}: ${reviewQueueSafety?.ledger_mutated === false ? copy.yes : copy.no}`} />
            <StatusBadge status="attention" label={copy.reviewDecisionAuditProof} />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-6 gap-2 mt-3">
          {[
            { label: copy.pendingApprovals, value: reviewQueueSummary?.pending_approvals ?? 0, status: (reviewQueueSummary?.pending_approvals || 0) > 0 ? "attention" : "pass" },
            { label: copy.memoryCandidates, value: reviewQueueSummary?.memory_candidates ?? 0, status: (reviewQueueSummary?.memory_candidates || 0) > 0 ? "attention" : "pass" },
            { label: copy.failedBenchmarks, value: reviewQueueSummary?.failed_evaluation_case_runs ?? 0, status: (reviewQueueSummary?.failed_evaluation_case_runs || 0) > 0 ? "attention" : "pass" },
            { label: copy.waitingDeliveries, value: reviewQueueSummary?.waiting_deliveries ?? 0, status: (reviewQueueSummary?.waiting_deliveries || 0) > 0 ? "attention" : "pass" },
            { label: copy.synthesisLoop, value: `${reviewQueueSummary?.commander_synthesis_promotion_available ?? 0}/${reviewQueueSummary?.commander_synthesis_memory_reviews ?? 0}`, status: ((reviewQueueSummary?.commander_synthesis_promotion_available || 0) + (reviewQueueSummary?.commander_synthesis_memory_reviews || 0)) > 0 ? "attention" : "pass" },
            { label: copy.returnedItems, value: `${reviewQueueSummary?.returned_items ?? 0}/${reviewQueueSummary?.review_items_total ?? 0}`, status: (reviewQueueSummary?.review_items_total || 0) > 0 ? "ready" : "idle" },
          ].map((item) => (
            <div key={item.label} className="rounded px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
              <div className="flex items-center justify-between gap-2 mt-1">
                <div className="text-sm font-semibold truncate" style={{ color: item.status === "attention" ? "var(--mis-warning)" : "var(--mis-text)" }}>{item.value}</div>
                <StatusBadge status={item.status} />
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-2 mt-3">
          {reviewResult && (
            <div className="text-[11px] rounded px-3 py-2" style={{ color: reviewResult.includes("Error") ? "#F87171" : "var(--mis-cyan)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
              {reviewResult}
            </div>
          )}
          {reviewQueueItems.length === 0 && (
            <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
              {copy.reviewQueueEmpty}
            </div>
          )}
          {reviewQueueItems.slice(0, 5).map((item) => (
            <div key={`${item.item_type}-${item.item_id}`} data-testid="review-queue-item" className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
              <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.title}</div>
                    <StatusBadge status={item.status} />
                  </div>
                  <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
                    {item.item_type} · {item.kind || "review"} · {item.agent_id || "agent: —"}
                  </div>
                  {item.summary && (
                    <div className="text-[10px] mt-1 line-clamp-2" style={{ color: "var(--mis-dim)" }}>{item.summary}</div>
                  )}
                  {item.next_action && (
                    <div className="text-[10px] mt-1 line-clamp-2" style={{ color: "var(--mis-cyan)" }}>
                      {copy.nextAction}: {item.next_action}
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap lg:justify-end gap-1.5 shrink-0">
                  {item.task_id && (
                    <Link to={`/admin/tasks/${item.task_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>{copy.openTask}</Link>
                  )}
                  {item.run_id && (
                    <Link to={`/admin/runs/${item.run_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}>{copy.openRun}</Link>
                  )}
                  {item.links?.report_url && (
                    <Link to={item.links.report_url} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(251,191,36,0.10)", color: "var(--mis-warning)", border: "1px solid rgba(251,191,36,0.20)" }}>{copy.openReport}</Link>
                  )}
                  {((item.item_type === "approval" && item.status === "pending") || (item.item_type === "memory_candidate" && item.status === "candidate") || (item.item_type === "evaluation_case_candidate" && item.status === "candidate")) && (
                    <>
                      <button
                        onClick={() => void handleReviewDecision(item, "approve")}
                        disabled={Boolean(reviewAction)}
                        className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded disabled:opacity-50"
                        style={{ background: "rgba(42,157,143,0.15)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.2)" }}
                      >
                        <CheckCircle2 size={11} /> {reviewAction === `${item.item_type}-${item.item_id}-approve` ? copy.dispatching : copy.reviewApprove}
                      </button>
                      <button
                        onClick={() => void handleReviewDecision(item, "reject")}
                        disabled={Boolean(reviewAction)}
                        className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded disabled:opacity-50"
                        style={{ background: "rgba(248,113,113,0.12)", color: "#F87171", border: "1px solid rgba(248,113,113,0.2)" }}
                      >
                        <XCircle size={11} /> {reviewAction === `${item.item_type}-${item.item_id}-reject` ? copy.dispatching : copy.reviewReject}
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="mt-2 grid grid-cols-1 lg:grid-cols-2 gap-1.5">
                {item.cli_action && (
                  <div className="text-[9px] truncate px-2 py-1 rounded" style={{ color: "var(--mis-muted)", background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                    {copy.cliAction}: {item.cli_action}
                  </div>
                )}
                {item.alternate_cli_action && (
                  <div className="text-[9px] truncate px-2 py-1 rounded" style={{ color: "var(--mis-muted)", background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                    {copy.alternateAction}: {item.alternate_cli_action}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Bot size={14} style={{ color: "var(--mis-cyan)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.loopLaneTitle}</h2>
              <StatusBadge status={loopLaneResult?.ok ? "completed" : loopLaneReadback?.status || "ready"} />
            </div>
            <p className="text-[11px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.loopLaneSummary}</p>
          </div>
          <div className="flex flex-wrap gap-1.5 lg:justify-end">
            <StatusBadge status="pass" label={`${copy.readOnlyProof}: ${loopLaneReadback?.token_omitted ? copy.yes : copy.no}`} />
            <StatusBadge status={(loopLaneReadback?.summary?.blocked_plan_evidence_manifests || 0) > 0 ? "blocked" : "pass"} label={`${copy.blockedManifests}: ${loopLaneReadback?.summary?.blocked_plan_evidence_manifests ?? 0}`} />
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.2fr_0.8fr] gap-3 mt-3">
          <div className="rounded-lg p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="grid grid-cols-1 md:grid-cols-[1fr_0.7fr] gap-2">
              <label className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>
                {copy.loopTopic}
                <textarea
                  value={loopLaneForm.topic}
                  onChange={(event) => updateLoopLaneForm("topic", event.target.value)}
                  className="mt-1 w-full rounded px-3 py-2 text-[11px] min-h-[72px]"
                  style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)", color: "var(--mis-text)" }}
                />
              </label>
              <label className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>
                {copy.loopId}
                <input
                  value={loopLaneForm.loop_id}
                  onChange={(event) => updateLoopLaneForm("loop_id", event.target.value)}
                  placeholder="loop_ui_review"
                  className="mt-1 w-full rounded px-3 py-2 text-[11px]"
                  style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)", color: "var(--mis-text)" }}
                />
                <div className="text-[9px] mt-1 normal-case" style={{ color: "var(--mis-dim)" }}>
                  {loopLaneResult?.loop_id || loopLaneReadback?.loop_id || "dry-run · MIS ledger · no live runtime"}
                </div>
              </label>
            </div>
            <div className="flex flex-wrap gap-2 mt-3">
              <button
                onClick={() => runLoopLane(false)}
                disabled={loopLaneBusy}
                className="inline-flex items-center gap-1.5 rounded px-3 py-2 text-[11px] disabled:opacity-50"
                style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.24)" }}
              >
                {loopLaneBusy ? <RefreshCw size={12} /> : <Play size={12} />}
                {loopLaneBusy ? copy.loopRunning : copy.runLoopLane}
              </button>
              <button
                onClick={() => runLoopLane(true)}
                disabled={loopLaneBusy || !loopLaneForm.loop_id.trim()}
                className="inline-flex items-center gap-1.5 rounded px-3 py-2 text-[11px] disabled:opacity-50"
                style={{ background: "var(--mis-bg)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
              >
                {loopLaneBusy ? <RefreshCw size={12} /> : <RotateCw size={12} />}
                {loopLaneBusy ? copy.loopRunning : copy.resumeLoopLane}
              </button>
            </div>
            {(loopLaneError || loopLaneResult) && (
              <div className="mt-3 rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: loopLaneError ? "1px solid rgba(248,113,113,0.24)" : "1px solid var(--mis-border)" }}>
                {loopLaneError && <div className="text-[11px]" style={{ color: "#F87171" }}>{loopLaneError}</div>}
                {loopLaneResult && (
                  <div className="space-y-2">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      {[
                        { label: copy.loopId, value: loopLaneResult.loop_id || "—" },
                        { label: copy.parentRun, value: loopLaneResult.mis_ledger?.parent_run_id || "—" },
                        { label: copy.verifiedManifests, value: loopLaneResult.mis_ledger?.verified_plan_evidence_manifest_ids?.length ?? 0 },
                        { label: copy.blockedManifests, value: loopLaneResult.mis_ledger?.blocked_plan_evidence_manifest_ids?.length ?? 0 },
                      ].map(item => (
                        <div key={item.label} className="rounded px-2 py-1" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                          <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                          <div className="text-[10px] font-semibold truncate mt-0.5" style={{ color: "var(--mis-text)" }}>{item.value}</div>
                        </div>
                      ))}
                    </div>
                    {loopLaneResult.mis_ledger?.parent_run_id && (
                      <Link to={`/admin/runs/${loopLaneResult.mis_ledger.parent_run_id}`} className="inline-flex text-[10px] rounded px-2 py-1" style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}>
                        {copy.openRun}
                      </Link>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="rounded-lg p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between gap-2">
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.loopReadback}</div>
              <StatusBadge status={loopLaneReadback?.status || "unknown"} />
            </div>
            <div className="grid grid-cols-2 gap-2 mt-3">
              {[
                { label: copy.runs, value: loopLaneReadback?.summary?.runs ?? 0 },
                { label: copy.artifactId, value: loopLaneReadback?.summary?.artifacts ?? 0 },
                { label: copy.verifiedManifests, value: loopLaneReadback?.summary?.verified_plan_evidence_manifests ?? 0 },
                { label: copy.blockedManifests, value: loopLaneReadback?.summary?.blocked_plan_evidence_manifests ?? 0 },
              ].map(item => (
                <div key={item.label} className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                  <div className="text-[10px] font-semibold truncate mt-0.5" style={{ color: "var(--mis-text)" }}>{item.value}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 space-y-1.5">
              {(loopLaneReadback?.runs || []).slice(0, 3).map((run) => (
                <Link key={String(run.run_id)} to={`/admin/runs/${String(run.run_id)}`} className="block rounded px-2 py-1.5" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{String(run.run_id || "—")}</div>
                  <div className="text-[9px] mt-0.5 truncate" style={{ color: "var(--mis-muted)" }}>{String(run.status || "unknown")} · {String(run.agent_id || "—")}</div>
                </Link>
              ))}
              {(loopLaneReadback?.runs || []).length === 0 && (
                <div className="text-[10px] rounded px-2 py-1.5" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.inboxEmpty}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <ShieldCheck size={14} style={{ color: "var(--mis-success)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.customerDeliveryBoardTitle}</h2>
              <StatusBadge status={customerDeliveryBoard?.status || "unknown"} />
            </div>
            <p className="text-[11px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.customerDeliveryBoardSummary}</p>
          </div>
          <div className="flex flex-wrap gap-1.5 lg:justify-end">
            <StatusBadge status={customerDeliverySafety?.read_only ? "pass" : "fail"} label={`${copy.deliverySafeReadback}: ${customerDeliverySafety?.read_only ? copy.yes : copy.no}`} />
            <StatusBadge status={customerDeliverySafety?.ledger_mutated === false ? "pass" : "fail"} label={`${copy.ledgerMutationProof}: ${customerDeliverySafety?.ledger_mutated === false ? copy.yes : copy.no}`} />
            <StatusBadge status={customerDeliverySafety?.live_execution_performed === false ? "pass" : "fail"} label={`${copy.liveExecutionProof}: ${customerDeliverySafety?.live_execution_performed === false ? copy.yes : copy.no}`} />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3">
          {[
            { label: copy.deliveriesReady, value: customerDeliverySummary?.ready ?? 0, status: (customerDeliverySummary?.ready || 0) > 0 ? "ready" : "idle" },
            { label: copy.deliveriesWaiting, value: customerDeliverySummary?.waiting_approval ?? 0, status: (customerDeliverySummary?.waiting_approval || 0) > 0 ? "attention" : "pass" },
            { label: copy.deliveriesAttention, value: customerDeliverySummary?.needs_attention ?? 0, status: (customerDeliverySummary?.needs_attention || 0) > 0 ? "blocked" : "pass" },
          ].map((item) => (
            <div key={item.label} className="rounded px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
              <div className="flex items-center justify-between gap-2 mt-1">
                <div className="text-lg font-semibold" style={{ color: item.status === "blocked" ? "#F87171" : "var(--mis-text)" }}>{item.value}</div>
                <StatusBadge status={item.status} />
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-2 mt-3">
          {customerDeliveries.length === 0 && (
            <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
              {copy.deliveryEmpty}
            </div>
          )}
          {customerDeliveries.slice(0, 4).map((delivery) => (
            <div key={delivery.delivery_id} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{delivery.title}</div>
                    <StatusBadge status={delivery.status} />
                  </div>
                  <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
                    {copy.taskId}: {delivery.task_id || "—"} · {copy.runId}: {delivery.run_id || "—"} · {copy.artifactId}: {delivery.artifact_id || "—"}
                  </div>
                  {delivery.summary && (
                    <div className="text-[10px] mt-1 line-clamp-2" style={{ color: "var(--mis-dim)" }}>{delivery.summary}</div>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <span
                      className="text-[9px] px-1.5 py-0.5 rounded"
                      style={{
                        color: delivery.delivery_approval_gate?.pass ? "var(--mis-success)" : delivery.delivery_approval_gate?.manifest_id ? "var(--mis-warning)" : "#F87171",
                        background: "var(--mis-surface2)",
                        border: "1px solid var(--mis-border)",
                      }}
                    >
                      {copy.planEvidenceGate}: {delivery.delivery_approval_gate?.pass ? copy.planEvidenceVerified : delivery.delivery_approval_gate?.manifest_id ? copy.planEvidenceBlocked : copy.planEvidenceMissing}
                    </span>
                    <span className="text-[9px] truncate max-w-[18rem]" style={{ color: "var(--mis-muted)" }}>
                      {delivery.delivery_approval_gate?.manifest_id || delivery.delivery_approval_gate?.message || delivery.next_action || "—"}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap md:justify-end gap-1.5 shrink-0">
                  {delivery.task_id && (
                    <Link to={`/admin/tasks/${delivery.task_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>{copy.openTask}</Link>
                  )}
                  {delivery.run_id && (
                    <Link to={`/admin/runs/${delivery.run_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}>{copy.openRun}</Link>
                  )}
                  {delivery.ui_report_url && (
                    <Link to={delivery.ui_report_url} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(251,191,36,0.10)", color: "var(--mis-warning)", border: "1px solid rgba(251,191,36,0.20)" }}>{copy.openReport}</Link>
                  )}
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {Object.entries(delivery.evidence || {}).slice(0, 6).map(([key, value]) => (
                  <span key={key} className="text-[9px] px-1.5 py-0.5 rounded" style={{ color: "var(--mis-muted)", background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                    {key}: {value}
                  </span>
                ))}
                {(delivery.pending_approval_ids?.length || 0) > 0 && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ color: "var(--mis-warning)", background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.22)" }}>
                    {copy.approvals}: {delivery.pending_approval_ids?.length}
                  </span>
                )}
                {delivery.next_action && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded truncate max-w-full" style={{ color: "var(--mis-cyan)", background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                    {copy.nextAction}: {delivery.next_action}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Activity size={14} style={{ color: "var(--mis-cyan)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.commandCenterTitle}</h2>
              <StatusBadge status={fleetHealth?.overall || workerStatus?.status || "unknown"} />
            </div>
            <p className="text-[11px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.commandCenterSummary}</p>
            {fleetHealth?.contract && (
              <p className="text-[10px] mt-1 max-w-3xl" style={{ color: "var(--mis-muted)" }}>
                {copy.contract}: {fleetHealth.contract}
              </p>
            )}
          </div>
          <div className="text-left lg:text-right shrink-0">
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.recommendedAdapter}</div>
            <div className="text-sm font-semibold mt-0.5" style={{ color: "var(--mis-text)" }}>{recommendedAdapter}</div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mt-4">
          {[
            { label: copy.overallFleetHealth, value: fleetHealth?.overall || workerStatus?.status || "—", status: fleetHealth?.overall || workerStatus?.status || "unknown" },
            { label: copy.daemonStatus, value: `${runningDaemons}/${workerStatus?.daemons?.length ?? 0}`, status: runningDaemons > 0 ? "running" : "ready" },
            { label: copy.pendingTasks, value: workerStatus?.pending_worker_tasks ?? "—", status: (workerStatus?.pending_worker_tasks || 0) > 0 ? "planned" : "pass" },
            { label: copy.stuckTasks, value: stuckWorkerCount, status: stuckWorkerCount > 0 ? "blocked" : "pass" },
            { label: copy.workflowRecovery, value: stuckWorkflowJobCount, status: stuckWorkflowJobCount > 0 ? "blocked" : "pass" },
            { label: copy.remoteWorkersTitle, value: `${workerStatus?.fresh_remote_enrollments ?? 0}/${workerStatus?.active_remote_enrollments ?? 0}`, status: remoteHealth?.status || "unknown" },
          ].map((item) => (
            <div key={item.label} className="rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
              <div className="flex items-center justify-between gap-2 mt-1">
                <div className="text-sm font-semibold truncate" style={{ color: item.status === "blocked" ? "#F87171" : "var(--mis-text)" }}>{item.value}</div>
                <StatusBadge status={item.status} />
              </div>
            </div>
          ))}
        </div>

        <div className="rounded-lg p-3 mt-4" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex flex-col xl:flex-row xl:items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <ShieldCheck size={13} style={{ color: hygieneActionsAvailable > 0 ? "var(--mis-warning)" : "var(--mis-success)" }} />
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.fleetHygieneTitle}</div>
                <StatusBadge status={activeHygiene?.status || "unknown"} />
              </div>
              <p className="text-[10px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.fleetHygieneSummary}</p>
              <div className="flex flex-wrap gap-1.5 mt-2">
                <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ color: "var(--mis-success)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.hygieneSafety}
                </span>
                <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.tokenOmittedProof}
                </span>
                {activeHygiene?.safety?.read_only && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ color: "var(--mis-cyan)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    {copy.readOnlyProof}
                  </span>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2 shrink-0">
              <button
                onClick={() => runFleetHygiene(false)}
                disabled={hygieneBusy}
                className="inline-flex items-center gap-1.5 text-[10px] px-2 py-1 rounded"
                style={{ color: "var(--mis-text)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}
              >
                {hygieneBusy ? <RefreshCw size={11} /> : <Activity size={11} />}
                {hygieneBusy ? copy.hygieneRunning : copy.hygienePlan}
              </button>
              <button
                onClick={() => runFleetHygiene(true)}
                disabled={hygieneBusy || hygieneActionsAvailable <= 0}
                className="inline-flex items-center gap-1.5 text-[10px] px-2 py-1 rounded disabled:opacity-50"
                style={{ color: "#071014", background: hygieneActionsAvailable > 0 ? "var(--mis-warning)" : "var(--mis-muted)", border: "1px solid var(--mis-border)" }}
              >
                {hygieneBusy ? <RefreshCw size={11} /> : <Trash2 size={11} />}
                {hygieneBusy ? copy.hygieneRunning : copy.hygieneApply}
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-3">
            {[
              { label: copy.hygieneActions, value: hygieneActionsAvailable, status: hygieneActionsAvailable > 0 ? "attention" : "pass" },
              { label: copy.stuckTasks, value: hygieneSummary?.stuck_tasks ?? 0, status: (hygieneSummary?.stuck_tasks || 0) > 0 ? "blocked" : "pass" },
              { label: copy.staleNeverSeen, value: hygieneSummary?.stale_never_seen_enrollments ?? 0, status: (hygieneSummary?.stale_never_seen_enrollments || 0) > 0 ? "attention" : "pass" },
              { label: copy.releasedTasks, value: hygieneSummary?.released_tasks ?? activeHygiene?.released_tasks?.length ?? 0, status: (hygieneSummary?.released_tasks || 0) > 0 ? "completed" : "planned" },
              { label: copy.revokedEnrollments, value: hygieneSummary?.revoked_enrollments ?? activeHygiene?.revoked_enrollments?.length ?? 0, status: (hygieneSummary?.revoked_enrollments || 0) > 0 ? "completed" : "planned" },
            ].map((item) => (
              <div key={item.label} className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                <div className="flex items-center justify-between gap-2 mt-0.5">
                  <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.value}</div>
                  <StatusBadge status={item.status} />
                </div>
              </div>
            ))}
          </div>
          {hygieneError && (
            <div className="text-[10px] mt-2" style={{ color: "#F87171" }}>{hygieneError}</div>
          )}
          <div className="mt-2 text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>
            {(activeHygiene?.recommended_actions || [copy.hygieneNoActions])[0] || copy.hygieneNoActions}
          </div>
        </div>

        <div className="rounded-lg p-3 mt-4" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={13} style={{ color: demoReadiness?.demo_ready ? "var(--mis-success)" : "var(--mis-warning)" }} />
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.demoReadinessTitle}</div>
                <StatusBadge status={demoReadiness?.status || "unknown"} label={demoReadiness?.demo_ready ? copy.demoReady : copy.statusAttention} />
              </div>
              <p className="text-[10px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.demoReadinessSummary}</p>
              {demoReadiness?.contract && (
                <p className="text-[10px] mt-1 max-w-3xl" style={{ color: "var(--mis-muted)" }}>{copy.contract}: {demoReadiness.contract}</p>
              )}
            </div>
            <StatusBadge status={demoReadiness?.production_ready ? "ready" : "attention"} label={demoReadiness?.production_ready ? copy.productionReady : copy.localDevOnly} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
            {[
              { label: copy.shotsReady, value: `${demoReadiness?.summary.ready_shots ?? 0}/${demoReadiness?.summary.shot_count ?? 0}`, status: demoReadiness?.demo_ready ? "ready" : "attention" },
              { label: copy.evidenceChains, value: demoReadiness?.summary.closed_loop_runs ?? 0, status: (demoReadiness?.summary.closed_loop_runs || 0) > 0 ? "pass" : "attention" },
              { label: copy.fleetLanes, value: demoReadiness?.summary.fleet_lanes ?? 0, status: (demoReadiness?.summary.fleet_lanes || 0) > 0 ? "pass" : "attention" },
              { label: copy.readyForReview, value: demoReadiness?.summary.ready_inbox_items ?? 0, status: (demoReadiness?.summary.ready_inbox_items || 0) > 0 ? "ready" : "planned" },
            ].map((item) => (
              <div key={item.label} className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                <div className="flex items-center justify-between gap-2 mt-0.5">
                  <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.value}</div>
                  <StatusBadge status={item.status} />
                </div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
            {(demoReadiness?.shots || []).slice(0, 6).map((shot) => (
              <div key={shot.id} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{shot.label}</div>
                  <StatusBadge status={shot.ok ? "pass" : shot.status} />
                </div>
                <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>{shot.route || shot.command || "—"}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg p-3 mt-4" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <GripVertical size={13} style={{ color: "var(--mis-cyan)" }} />
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.actionQueueTitle}</div>
                <StatusBadge status={operatorActionPlan?.status || "unknown"} />
              </div>
              <p className="text-[10px] mt-1" style={{ color: "var(--mis-muted)" }}>
                {copy.actionQueueSummary}
                {operatorPlanSummary && ` · blocked ${operatorPlanSummary.blocked} / attention ${operatorPlanSummary.attention} / adapter ${operatorPlanSummary.recommended_adapter}`}
                {operatorPlanSummary && ` · remediation ${operatorPlanSummary.remediation_packages}/${operatorPlanSummary.remediation_pending_reviews}/${operatorPlanSummary.remediation_promoted_deliveries}`}
                {operatorPlanSummary && ` · evidence gaps ${operatorPlanSummary.evidence_gap_runs}/${operatorPlanSummary.blocked_evidence_gap_runs}/${operatorPlanSummary.remediated_evidence_gap_runs}`}
                {operatorPlanSummary && ` · synth ${operatorPlanSummary.evidence_synthesis_ready_runs}/${operatorPlanSummary.evidence_synthesis_pending_runs}/${operatorPlanSummary.evidence_synthesis_promoted_runs}`}
                {operatorPlanSummary && ` · close ${operatorPlanSummary.evidence_gap_closure_ready_runs}/${operatorPlanSummary.closed_evidence_gap_runs}/${operatorPlanSummary.waived_evidence_gap_runs}`}
                {operatorPlanSummary && ` · intake ${operatorPlanSummary.task_intake_ready}/${operatorPlanSummary.task_intake_blocked}/${operatorPlanSummary.task_intake_attention}`}
              </p>
            </div>
            <button
              onClick={() => setActionQueueOrder(actionQueueCandidates.map(item => item.id))}
              className="text-[10px] px-2 py-1 rounded"
              style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}
            >
              {copy.resetOrder}
            </button>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-2 mt-3">
            {visibleActionQueue.length === 0 && (
              <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                {copy.noRecommendedActions}
              </div>
            )}
            {visibleActionQueue.map((item, index) => {
              const closeGapDetails = closeGapDetailsForAction(item);
              const closeGapBusy = Boolean(closeGapDetails && dispatching === `close-gap:${closeGapDetails.runId}`);
              return (
                <div
                  key={item.id}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", item.id);
                    setDraggedActionId(item.id);
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = "move";
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    const activeId = event.dataTransfer.getData("text/plain") || draggedActionId;
                    if (activeId) moveActionQueueItem(activeId, item.id);
                    setDraggedActionId(null);
                  }}
                  onDragEnd={() => setDraggedActionId(null)}
                  className="grid grid-cols-[auto_1fr] sm:grid-cols-[auto_1fr_auto] items-center gap-2 rounded px-3 py-2 cursor-grab active:cursor-grabbing"
                  style={{
                    background: draggedActionId === item.id ? "rgba(34,211,238,0.08)" : "var(--mis-bg)",
                    border: draggedActionId === item.id ? "1px solid rgba(34,211,238,0.32)" : "1px solid var(--mis-border)",
                  }}
                  title={copy.dragToReorder}
                >
                  <GripVertical size={14} style={{ color: "var(--mis-muted)" }} />
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.action}</div>
                    <div className="text-[10px] truncate mt-0.5" style={{ color: "var(--mis-muted)" }}>
                      {copy.actionSource}: {item.source}
                    </div>
                  </div>
                  <div className="col-span-2 sm:col-span-1 flex items-center gap-1.5 justify-end">
                    {closeGapDetails && (
                      <button
                        onClick={() => void closeEvidenceGapFromQueue(item)}
                        disabled={Boolean(dispatching)}
                        className="inline-flex items-center gap-1 text-[10px] px-2 h-6 rounded disabled:opacity-50"
                        style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.20)" }}
                        title={copy.closeEvidenceGap}
                      >
                        {closeGapBusy ? <RefreshCw size={10} /> : <CheckCircle2 size={10} />}
                        {closeGapBusy ? copy.closingEvidenceGap : copy.closeEvidenceGap}
                      </button>
                    )}
                    <StatusBadge status={item.status} />
                    <button
                      onClick={() => nudgeActionQueueItem(item.id, -1)}
                      disabled={index === 0}
                      className="text-[10px] w-6 h-6 rounded disabled:opacity-30"
                      style={{ color: "var(--mis-dim)", background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}
                      aria-label={copy.moveUp}
                      title={copy.moveUp}
                    >
                      ↑
                    </button>
                    <button
                      onClick={() => nudgeActionQueueItem(item.id, 1)}
                      disabled={index === visibleActionQueue.length - 1}
                      className="text-[10px] w-6 h-6 rounded disabled:opacity-30"
                      style={{ color: "var(--mis-dim)", background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}
                      aria-label={copy.moveDown}
                      title={copy.moveDown}
                    >
                      ↓
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--mis-border)" }}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.evidenceClosureLedger}</div>
                <div className="text-[10px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.evidenceClosureSummary}</div>
              </div>
              <StatusBadge status={(operatorPlanSummary?.closed_evidence_gap_runs || 0) > 0 ? "pass" : (operatorPlanSummary?.evidence_gap_closure_ready_runs || 0) > 0 ? "attention" : "ready"} label={`${operatorPlanSummary?.closed_evidence_gap_runs || 0}/${operatorPlanSummary?.evidence_gap_closure_ready_runs || 0}`} />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 mt-2">
              {evidenceClosureRows.length === 0 && (
                <div className="text-[10px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.noClosureRows}
                </div>
              )}
              {evidenceClosureRows.map((gap) => {
                const canClose = gap.gap_decision_status !== "closed" && isCloseEvidenceGapCommand(gap.command || "");
                const canReopen = gap.gap_decision_status === "closed";
                const closeBusy = dispatching === `close-gap:${gap.run_id}`;
                const reopenBusy = dispatching === `reopen-gap:${gap.run_id}`;
                return (
                  <div key={gap.run_id} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{gap.task_title || gap.run_id}</div>
                        <div className="text-[10px] truncate mt-0.5" style={{ color: "var(--mis-muted)" }}>{gap.run_id}</div>
                      </div>
                      <StatusBadge status={gap.gap_decision_status === "closed" ? "pass" : canClose ? "attention" : gap.severity} />
                    </div>
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>
                        {copy.remediationState}: <span style={{ color: "var(--mis-text)" }}>{gap.remediation_synthesis_status || gap.remediation_status || "—"}</span>
                      </div>
                      <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>
                        {copy.closureDecision}: <span style={{ color: "var(--mis-text)" }}>{gap.gap_decision_type || gap.gap_decision_status || "open"}</span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between gap-2 mt-2">
                      <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>{gap.next_action || gap.command}</div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {canClose && (
                          <button
                            onClick={() => void submitEvidenceGapDecision(evidenceGapDecisionDetails(gap))}
                            disabled={Boolean(dispatching)}
                            className="inline-flex items-center gap-1 text-[10px] px-2 h-6 rounded disabled:opacity-50"
                            style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.20)" }}
                            title={copy.closeEvidenceGap}
                          >
                            {closeBusy ? <RefreshCw size={10} /> : <CheckCircle2 size={10} />}
                            {closeBusy ? copy.closingEvidenceGap : copy.closeEvidenceGap}
                          </button>
                        )}
                        {canReopen && (
                          <button
                            onClick={() => void submitEvidenceGapDecision(evidenceGapDecisionDetails(gap, "reopen"))}
                            disabled={Boolean(dispatching)}
                            className="inline-flex items-center gap-1 text-[10px] px-2 h-6 rounded disabled:opacity-50"
                            style={{ background: "rgba(245,158,11,0.10)", color: "var(--mis-warning)", border: "1px solid rgba(245,158,11,0.20)" }}
                            title={copy.reopenEvidenceGap}
                          >
                            {reopenBusy ? <RefreshCw size={10} /> : <RotateCw size={10} />}
                            {reopenBusy ? copy.reopeningEvidenceGap : copy.reopenEvidenceGap}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="rounded-lg p-3 mt-4" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <ShieldCheck size={13} style={{ color: (taskIntakeSummary?.blocked_for_intake || 0) > 0 ? "var(--mis-warning)" : "var(--mis-success)" }} />
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.taskIntakeTitle}</div>
                <StatusBadge status={taskIntakeChecklist?.status || "unknown"} />
              </div>
              <p className="text-[10px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.taskIntakeSummary}</p>
            </div>
            <StatusBadge status={(taskIntakeSummary?.blocked_for_intake || 0) > 0 ? "blocked" : (taskIntakeSummary?.attention_for_intake || 0) > 0 ? "attention" : "pass"} label={`${taskIntakeSummary?.ready_for_intake || 0}/${taskIntakeSummary?.tasks_checked || 0}`} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3">
            {[
              { label: copy.intakeReady, value: taskIntakeSummary?.ready_for_intake ?? 0, status: "pass" },
              { label: copy.intakeBlocked, value: taskIntakeSummary?.blocked_for_intake ?? 0, status: (taskIntakeSummary?.blocked_for_intake || 0) > 0 ? "blocked" : "pass" },
              { label: copy.intakeAttention, value: taskIntakeSummary?.attention_for_intake ?? 0, status: (taskIntakeSummary?.attention_for_intake || 0) > 0 ? "attention" : "pass" },
            ].map((item) => (
              <div key={item.label} className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                <div className="flex items-center justify-between gap-2 mt-0.5">
                  <div className="text-[10px] font-semibold truncate" style={{ color: item.status === "blocked" ? "#F87171" : "var(--mis-text)" }}>{item.value}</div>
                  <StatusBadge status={item.status} />
                </div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-2 mt-3">
            {taskIntakeRows.length === 0 && (
              <div className="text-[10px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                {copy.noIntakeRows}
              </div>
            )}
            {taskIntakeRows.map((item) => (
              <div key={item.task_id} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.title}</div>
                    <div className="text-[10px] truncate mt-0.5" style={{ color: "var(--mis-muted)" }}>{item.task_id}</div>
                  </div>
                  <StatusBadge status={item.severity} />
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>
                    {copy.assignedAgents}: <span style={{ color: "var(--mis-text)" }}>{item.assigned_agent_ids.join(", ") || "—"}</span>
                  </div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>
                    Agent Plan: <span style={{ color: "var(--mis-text)" }}>{item.plan_verified ? "verified" : item.plan_id || "missing"}</span>
                  </div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>
                    {copy.planReferences}: <span style={{ color: "var(--mis-text)" }}>{item.referenced_specs}/{item.referenced_memories}/{item.referenced_bases}</span>
                  </div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>
                    Risk: <span style={{ color: "var(--mis-text)" }}>{item.risk_level || "—"}</span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {item.gates.slice(0, 6).map((gate) => (
                    <StatusBadge key={gate.id} status={gate.ok ? "pass" : gate.status} label={gate.id} />
                  ))}
                </div>
                <div className="text-[10px] truncate mt-2" style={{ color: "var(--mis-dim)" }}>{item.next_action || item.command}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg p-3 mt-4" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <ShieldCheck size={13} style={{ color: localSafetyOk ? "var(--mis-success)" : "var(--mis-warning)" }} />
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.localReadinessTitle}</div>
                <StatusBadge status={localReadiness?.status || "unknown"} />
              </div>
              <p className="text-[10px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.localReadinessSummary}</p>
              {localReadiness?.contract && (
                <p className="text-[10px] mt-1 truncate max-w-3xl" style={{ color: "var(--mis-muted)" }}>
                  {copy.contract}: {localReadiness.contract}
                </p>
              )}
            </div>
            <StatusBadge status={localReadiness?.ok ? "pass" : "blocked"} label={`${localReadinessReadyGates}/${localReadinessGates.length || 0}`} />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-6 gap-2 mt-3">
            {[
              { label: copy.localReadinessOverall, value: localReadiness?.status || "—", status: localReadiness?.status || "unknown" },
              { label: copy.evidenceChains, value: localEvidence?.closed_loop_runs ?? "—", status: localEvidence?.has_task_run_tool_eval_audit_artifact_chain ? "pass" : "attention" },
              { label: copy.memoryApprovalCounts, value: `${localEvidence?.memories ?? 0}/${localEvidence?.approvals ?? 0}`, status: localEvidence?.has_memory_or_knowledge && localEvidence?.has_approval_flow ? "pass" : "attention" },
              { label: copy.synthesisLoop, value: `${localEvidence?.commander_synthesis_promoted_deliveries ?? 0}/${localEvidence?.commander_synthesis_pending_reviews ?? 0}`, status: (localEvidence?.commander_synthesis_promoted_deliveries ?? 0) > 0 ? "pass" : "attention" },
              { label: copy.recommendedAdapter, value: localRecommendedAdapter, status: localRecommendedAdapter ? "ready" : "unknown" },
              { label: copy.safetyProof, value: localSafetyOk ? copy.statusClear : copy.statusAttention, status: localSafetyOk ? "pass" : "blocked" },
            ].map((item) => (
              <div key={item.label} className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                <div className="flex items-center justify-between gap-2 mt-0.5">
                  <div className="text-[10px] font-semibold truncate" style={{ color: item.status === "blocked" ? "#F87171" : "var(--mis-text)" }}>{item.value}</div>
                  <StatusBadge status={item.status} />
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-[0.9fr_1.1fr] gap-3 mt-3">
            <div className="flex flex-wrap gap-1.5">
              <StatusBadge status={localReadiness?.token_omitted ? "pass" : "fail"} label={`${copy.tokenOmittedProof}: ${localReadiness?.token_omitted ? copy.yes : copy.no}`} />
              <StatusBadge status={localReadiness?.live_execution_performed === false ? "pass" : "fail"} label={`${copy.liveExecutionProof}: ${localReadiness?.live_execution_performed === false ? copy.yes : copy.no}`} />
            </div>
            <div className="flex flex-wrap gap-1.5 md:justify-end">
              {(localReadinessActions.length > 0 ? localReadinessActions : [copy.noRecommendedActions]).slice(0, 3).map((action) => (
                <span key={action} className="text-[10px] px-2 py-1 rounded truncate max-w-full" style={{ color: "var(--mis-cyan)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.nextAction}: {action}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-lg p-3 mt-4" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Inbox size={13} style={{ color: integrationInboxSafe ? "var(--mis-success)" : "var(--mis-cyan)" }} />
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.integrationInboxTitle}</div>
                <StatusBadge status={integrationInbox?.status || "unknown"} />
              </div>
              <p className="text-[10px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.integrationInboxSummary}</p>
            </div>
            <StatusBadge status={(integrationInboxSummary?.blocked || 0) > 0 ? "blocked" : (integrationInboxSummary?.ready_for_review || 0) > 0 ? "attention" : "pass"} label={String(integrationInboxSummary?.total ?? 0)} />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2 mt-3">
            {[
              { label: copy.readyForReview, value: integrationInboxSummary?.ready_for_review ?? 0, status: (integrationInboxSummary?.ready_for_review || 0) > 0 ? "ready" : "pass" },
              { label: copy.stillRunning, value: integrationInboxSummary?.still_running ?? 0, status: (integrationInboxSummary?.still_running || 0) > 0 ? "running" : "pass" },
              { label: copy.blockedItems, value: integrationInboxSummary?.blocked ?? 0, status: (integrationInboxSummary?.blocked || 0) > 0 ? "blocked" : "pass" },
              { label: copy.lateOrStale, value: integrationInboxSummary?.late_or_stale ?? 0, status: (integrationInboxSummary?.late_or_stale || 0) > 0 ? "stale" : "pass" },
              { label: copy.memoryReview, value: integrationInboxSummary?.needs_memory_review ?? 0, status: (integrationInboxSummary?.needs_memory_review || 0) > 0 ? "candidate" : "pass" },
            ].map((item) => (
              <div key={item.label} className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                <div className="flex items-center justify-between gap-2 mt-0.5">
                  <div className="text-[10px] font-semibold truncate" style={{ color: item.status === "blocked" ? "#F87171" : "var(--mis-text)" }}>{item.value}</div>
                  <StatusBadge status={item.status} />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] mr-1" style={{ color: "var(--mis-muted)" }}>{copy.inboxFilter}</span>
            {integrationInboxFilters.map((filter) => {
              const active = integrationInboxBucket === filter.bucket;
              return (
                <button
                  key={filter.bucket}
                  type="button"
                  onClick={() => setIntegrationInboxBucket(filter.bucket)}
                  className="rounded px-2 py-1 text-[10px] font-semibold"
                  style={{
                    color: active ? "var(--mis-bg)" : "var(--mis-text)",
                    background: active ? "var(--mis-cyan)" : "var(--mis-bg)",
                    border: `1px solid ${active ? "var(--mis-cyan)" : "var(--mis-border)"}`,
                  }}
                >
                  {filter.label} · {filter.count}
                </button>
              );
            })}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-[1.35fr_0.85fr] gap-3 mt-3">
            <div className="space-y-2 min-w-0">
              {integrationInboxItems.length === 0 && (
                <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.inboxEmpty}
                </div>
              )}
              {integrationInboxItems.slice(0, 5).map((item) => {
                const primaryRef = item.task_id || item.run_id || item.job_id || item.artifact_id || item.item_id;
                return (
                  <div key={item.item_id || primaryRef} className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.title}</div>
                        <StatusBadge status={item.status} />
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-[10px]" style={{ color: "var(--mis-muted)" }}>
                        <span>{copy.itemBucket}: {item.bucket || "—"}</span>
                        <span>{copy.itemAge}: {formatAge(item.age_sec)}</span>
                        <span>{copy.itemOwner}: {item.owner_agent_id || item.agent_id || "—"}</span>
                      </div>
                      {item.recommended_action && (
                        <div className="text-[10px] truncate mt-1" style={{ color: "var(--mis-cyan)" }}>
                          {copy.nextAction}: {item.recommended_action}
                        </div>
                      )}
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {item.task_id && <Link className="text-[10px]" style={{ color: "var(--mis-cyan)" }} to={`/admin/tasks/${item.task_id}`}>{copy.taskId}: {item.task_id}</Link>}
                        {item.run_id && <Link className="text-[10px]" style={{ color: "var(--mis-cyan)" }} to={`/admin/runs/${item.run_id}`}>{copy.runId}: {item.run_id}</Link>}
                        {item.job_id && <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.jobId}: {item.job_id}</span>}
                        {item.artifact_id && <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.artifactId}: {item.artifact_id}</span>}
                      </div>
                    </div>
                    <StatusBadge status={item.bucket || "unknown"} label={item.bucket || "—"} />
                  </div>
                );
              })}
            </div>

            <div className="space-y-2 min-w-0">
              <div className="flex flex-wrap gap-1.5">
                <StatusBadge status={integrationInboxSafety?.read_only ? "pass" : "fail"} label={`${copy.readOnlyProof}: ${integrationInboxSafety?.read_only ? copy.yes : copy.no}`} />
                <StatusBadge status={integrationInboxSafety?.ledger_mutated === false ? "pass" : "fail"} label={`${copy.ledgerMutationProof}: ${integrationInboxSafety?.ledger_mutated === false ? copy.yes : copy.no}`} />
                <StatusBadge status={integrationInboxSafety?.raw_prompt_omitted ? "pass" : "fail"} label={`${copy.rawPromptProof}: ${integrationInboxSafety?.raw_prompt_omitted ? copy.yes : copy.no}`} />
              </div>
              {(integrationInboxActions.length > 0 ? integrationInboxActions : [copy.noRecommendedActions]).slice(0, 4).map((action) => (
                <div key={action} className="text-[11px] rounded px-3 py-2 truncate" style={{ color: "var(--mis-cyan)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {action}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.35fr_1fr] gap-4 mt-4">
          <div className="rounded-lg p-3 min-w-0" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.healthGates}</div>
              <StatusBadge status={fleetHealth?.overall || "unknown"} label={String(fleetGates.length)} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
              {fleetGates.slice(0, 6).map((gate) => (
                <div key={`${gate.id}-${gate.status}`} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{gate.id}</div>
                    <StatusBadge status={gate.status} />
                  </div>
                  <div className="text-[10px] mt-1 line-clamp-2" style={{ color: "var(--mis-dim)" }}>{gate.summary}</div>
                  {gate.action && (
                    <div className="text-[10px] mt-1 truncate" style={{ color: gate.status === "fail" || gate.status === "warn" ? "var(--mis-warning)" : "var(--mis-muted)" }}>
                      {gate.action}
                    </div>
                  )}
                </div>
              ))}
              {fleetGates.length === 0 && (
                <div className="md:col-span-2 text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.noRecommendedActions}
                </div>
              )}
            </div>
          </div>

          <div className="rounded-lg p-3 min-w-0" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.recommendedActions}</div>
              <StatusBadge status={recommendedActions.length > 0 ? "attention" : "pass"} label={String(recommendedActions.length)} />
            </div>
            <div className="space-y-2 mt-3">
              {recommendedActions.length === 0 && (
                <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.noRecommendedActions}
                </div>
              )}
              {recommendedActions.slice(0, 5).map((action) => (
                <div key={action} className="text-[11px] rounded px-3 py-2 truncate" style={{ color: "var(--mis-cyan)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {action}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.1fr_0.9fr] gap-4 mt-4">
          <div className="rounded-lg p-3 min-w-0" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.remoteWorkersTitle}</div>
              <div className="flex flex-wrap gap-1.5 justify-end">
                <StatusBadge status="fresh" label={`${copy.heartbeatFresh}: ${workerStatus?.fresh_remote_enrollments ?? 0}`} />
                <StatusBadge status="stale" label={`${copy.heartbeatStale}: ${workerStatus?.stale_remote_enrollments ?? 0}`} />
                <StatusBadge status="never_seen" label={`${copy.heartbeatNeverSeen}: ${workerStatus?.never_seen_remote_enrollments ?? 0}`} />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2 mt-3">
              {[
                { label: copy.totalEnrollments, value: workerStatus?.total_remote_enrollments ?? 0 },
                { label: copy.activeEnrollments, value: workerStatus?.active_remote_enrollments ?? 0 },
                { label: copy.activeSessions, value: workerStatus?.active_remote_sessions ?? 0 },
                { label: copy.gatewayWorkspace, value: gatewayStatus?.auth.workspace_id || "local-demo" },
              ].map((item) => (
                <div key={item.label} className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                  <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.value}</div>
                </div>
              ))}
            </div>
            <div className="space-y-2 mt-3">
              {remoteWorkers.length === 0 && (
                <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.noRemoteWorkers}
                </div>
              )}
              {remoteWorkers.slice(0, 4).map((worker) => (
                <div key={`${worker.agent_id}-${worker.token_ref}`} className="grid grid-cols-1 md:grid-cols-[1fr_0.55fr_0.55fr_0.7fr] gap-2 items-start md:items-center rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{worker.agent_name || worker.agent_id || "remote worker"}</div>
                    <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{worker.agent_id || "—"} · {worker.runtime_type || "external"}</div>
                  </div>
                  <StatusBadge status={worker.heartbeat_state || "unknown"} />
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>{copy.activeSessions}: {worker.active_session_count ?? 0}</div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>{worker.last_heartbeat_at || worker.last_used_at || "—"}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg p-3 min-w-0" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.recentRemoteSessionsTitle}</div>
              <StatusBadge status={recentRemoteSessions.length > 0 ? "active" : "idle"} label={String(recentRemoteSessions.length)} />
            </div>
            <div className="space-y-2 mt-3">
              {recentRemoteSessions.length === 0 && (
                <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.noSessions}
                </div>
              )}
              {recentRemoteSessions.slice(0, 5).map((session) => (
                <div key={`${session.agent_id}-${session.session_ref}`} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{session.agent_id || "—"}</div>
                    <StatusBadge status={session.session_state || session.status || "unknown"} />
                  </div>
                  <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
                    {copy.sessionId}: {session.session_ref || "—"} · {copy.expires}: {session.expires_at || "—"}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Bot size={14} style={{ color: "var(--mis-cyan)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.customerTaskTitle}</h2>
              <StatusBadge
                status={customerTaskResult?.ok ? "completed" : customerTaskResult?.dry_run ? "planned" : customerTaskResult ? "failed" : "ready"}
              />
            </div>
            <p className="text-[11px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.customerTaskSummary}</p>
            <p className="text-[10px] mt-1 max-w-3xl" style={{ color: "var(--mis-muted)" }}>{copy.confirmLiveHint}</p>
          </div>
          <div className="flex gap-2 shrink-0 flex-wrap justify-start lg:justify-end">
            <button
              onClick={() => runCustomerTask(false)}
              disabled={customerTaskBusy}
              className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
              style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
            >
              {customerTaskBusy ? <RefreshCw size={12} /> : <Play size={12} />}
              {customerTaskBusy ? copy.customerTaskRunning : copy.runSafeTask}
            </button>
            <button
              onClick={() => runCustomerTask(true)}
              disabled={customerTaskBusy || selectedAdapterLiveBlocked}
              className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
              style={{ background: "rgba(45,212,191,0.12)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.22)" }}
            >
              {customerTaskBusy ? <RefreshCw size={12} /> : <ShieldCheck size={12} />}
              {customerTaskBusy ? copy.customerTaskRunning : copy.confirmLiveTask}
            </button>
            <button
              onClick={submitCustomerTaskAsync}
              disabled={customerTaskBusy || selectedAdapterLiveBlocked}
              className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
              style={{ background: "rgba(251,191,36,0.12)", color: "var(--mis-warning)", border: "1px solid rgba(251,191,36,0.24)" }}
            >
              {customerTaskBusy ? <RefreshCw size={12} /> : <Activity size={12} />}
              {customerTaskBusy ? copy.customerTaskRunning : copy.submitAsyncTask}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-[1fr_180px] gap-3 mt-4">
          <label className="text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.taskTitleLabel}
            <input
              value={customerTaskForm.title}
              onChange={(event) => updateCustomerTaskText("title", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            />
          </label>
          <label className="text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.adapterLabel}
            <select
              value={customerTaskForm.adapter}
              onChange={(event) => updateCustomerTaskAdapter(event.target.value as (typeof WORKER_ADAPTERS)[number])}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            >
              {WORKER_ADAPTERS.map(adapter => (
                <option key={adapter} value={adapter}>{adapter}</option>
              ))}
            </select>
          </label>
          <label className="md:col-span-2 text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.taskDescriptionLabel}
            <textarea
              value={customerTaskForm.description}
              onChange={(event) => updateCustomerTaskText("description", event.target.value)}
              rows={3}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none resize-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            />
          </label>
        </div>

        {renderActiveIntakeGate()}

        <div
          className="rounded-lg p-3 mt-3"
          style={{
            background: selectedAdapterLiveBlocked ? "rgba(248,113,113,0.08)" : "var(--mis-surface2)",
            border: selectedAdapterLiveBlocked ? "1px solid rgba(248,113,113,0.22)" : "1px solid var(--mis-border)",
          }}
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 min-w-0">
              {selectedAdapterLiveBlocked ? <AlertTriangle size={13} style={{ color: "#F87171" }} /> : <CheckCircle2 size={13} style={{ color: "var(--mis-success)" }} />}
              <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>
                {customerTaskForm.adapter} · {selectedAdapterIsReady ? copy.selectedAdapterReady : copy.selectedAdapterBlocked}
              </div>
            </div>
            <StatusBadge status={selectedAdapterRoute?.readiness || "unknown"} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2">
            <div className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{copy.trustStatus}</div>
              <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{selectedAdapterRoute?.trust_status || "—"}</div>
            </div>
            <div className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{copy.targetResource}</div>
              <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{selectedAdapterRoute?.target_resource || "—"}</div>
            </div>
            <div className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{copy.nextAction}</div>
              <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-cyan)" }}>{selectedAdapterRoute?.recommended_action || "agentops worker readiness"}</div>
            </div>
          </div>
        </div>

        <div className="text-[10px] mt-3" style={{ color: "var(--mis-muted)" }}>{copy.asyncTaskHint}</div>

        {(customerTaskError || customerTaskResult || customerTaskJob) && (
          <div
            className="rounded-lg p-3 mt-4"
            style={{
              background: customerTaskError ? "rgba(248,113,113,0.08)" : "var(--mis-surface2)",
              border: customerTaskError ? "1px solid rgba(248,113,113,0.22)" : "1px solid var(--mis-border)",
            }}
          >
            {customerTaskError && (
              <div className="text-[11px]" style={{ color: "#F87171" }}>{customerTaskError}</div>
            )}
            {customerTaskJob && (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2">
                  <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.jobId}</div>
                    <div className="text-[11px] font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{customerTaskJob.job_id}</div>
                  </div>
                  <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.jobType}</div>
                    <div className="text-[11px] font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{customerTaskJob.workflow_type}</div>
                  </div>
                  <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.adapterLabel}</div>
                    <div className="text-[11px] font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{customerTaskJob.adapter || customerTaskForm.adapter}</div>
                  </div>
                  <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.eventStatus}</div>
                    <div className="mt-1"><StatusBadge status={customerTaskJob.status} /></div>
                  </div>
                </div>
                <div className="text-[11px] leading-relaxed rounded px-3 py-2" style={{ background: "var(--mis-bg)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}>
                  {customerTaskJob.input_summary || customerTaskJob.title}
                </div>
              </div>
            )}
            {customerTaskResult && (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2">
                  <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.taskId}</div>
                    <div className="text-[11px] font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{customerTaskResult.task_id}</div>
                  </div>
                  <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.runId}</div>
                    <div className="text-[11px] font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{customerTaskResult.run_id || "—"}</div>
                  </div>
                  <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.artifactId}</div>
                    <div className="text-[11px] font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{customerTaskResult.artifact_id || "—"}</div>
                  </div>
                  <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                    <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.runtime}</div>
                    <div className="text-[11px] font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{customerTaskResult.adapter || customerTaskForm.adapter}</div>
                  </div>
                </div>
                {(customerTaskResult.plan_id || customerTaskResult.plan_evidence_manifest_id) && (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                      <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.agentPlan}</div>
                      <div className="text-[11px] font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{customerTaskResult.plan_id || "—"}</div>
                    </div>
                    <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                      <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.planEvidence}</div>
                      <div className="mt-1"><StatusBadge status={customerTaskResult.plan_evidence_pass ? "pass" : customerTaskResult.plan_evidence_status || "attention"} label={customerTaskResult.plan_evidence_manifest_id || "—"} /></div>
                    </div>
                    <div className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                      <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.approvals}</div>
                      <div className="text-[11px] font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{customerTaskResult.approval_id || "—"}</div>
                    </div>
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  {customerTaskResult.task_id && (
                    <Link
                      to={`/admin/tasks/${customerTaskResult.task_id}`}
                      className="text-[11px] px-3 py-1.5 rounded"
                      style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
                    >
                      {copy.openTask}
                    </Link>
                  )}
                  {customerTaskResult.run_id && (
                    <Link
                      to={`/admin/runs/${customerTaskResult.run_id}`}
                      className="text-[11px] px-3 py-1.5 rounded"
                      style={{ background: "rgba(45,212,191,0.12)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.22)" }}
                    >
                      {copy.openRun}
                    </Link>
                  )}
                  {Object.entries(customerTaskResult.evidence || {}).map(([key, value]) => (
                    <span key={key} className="text-[10px] px-2 py-1 rounded" style={{ background: "var(--mis-bg)", color: "var(--mis-muted)", border: "1px solid var(--mis-border)" }}>
                      {copy.evidence}: {key} {value ?? 0}
                    </span>
                  ))}
                </div>
                {(customerTaskResult.output_summary || customerTaskResult.reason || customerTaskResult.error) && (
                  <div className="text-[11px] leading-relaxed rounded px-3 py-2" style={{ background: "var(--mis-bg)", color: customerTaskResult.error ? "#F87171" : "var(--mis-dim)", border: "1px solid var(--mis-border)" }}>
                    <span className="font-semibold" style={{ color: "var(--mis-text)" }}>{copy.outputSummary}: </span>
                    {customerTaskResult.output_summary || customerTaskResult.reason || customerTaskResult.error}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div className="rounded-lg p-3 mt-4" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.workflowJobsTitle}</div>
              <div className="text-[10px] mt-1" style={{ color: "var(--mis-muted)" }}>{copy.workflowJobsSummary}</div>
              {workflowJobResult && (
                <div className="text-[10px] mt-1" style={{ color: workflowJobResult.includes("failed") ? "var(--mis-success)" : "var(--mis-warning)" }}>
                  {workflowJobResult}
                </div>
              )}
            </div>
            <button
              onClick={refresh}
              className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded"
              style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
            >
              <RefreshCw size={12} />
              {copy.refresh}
            </button>
          </div>

          <div className="rounded-lg p-3 mt-3" style={{ background: stuckWorkflowRecoveryRows.length > 0 ? "rgba(251,191,36,0.08)" : "var(--mis-bg)", border: stuckWorkflowRecoveryRows.length > 0 ? "1px solid rgba(251,191,36,0.24)" : "1px solid var(--mis-border)" }}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-1.5">
                  <AlertTriangle size={13} style={{ color: stuckWorkflowRecoveryRows.length > 0 ? "var(--mis-warning)" : "var(--mis-muted)" }} />
                  <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.stuckWorkflowJobsTitle}</div>
                </div>
                <div className="text-[10px] mt-1" style={{ color: "var(--mis-muted)" }}>{copy.stuckWorkflowJobsSummary}</div>
              </div>
              <StatusBadge status={stuckWorkflowRecoveryRows.length > 0 ? "blocked" : "pass"} label={String(stuckWorkflowRecoveryRows.length)} />
            </div>
            <div className="space-y-2 mt-3">
              {stuckWorkflowRecoveryRows.length === 0 && (
                <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                  {copy.noStuckWorkflowJobs}
                </div>
              )}
              {stuckWorkflowRecoveryRows.slice(0, 4).map((job) => (
                <div key={job.job_id} className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.7fr_0.7fr_auto] gap-3 items-start lg:items-center rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{"title" in job ? job.title || job.job_id : job.job_id}</div>
                    <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{job.job_id} · {job.workflow_type}</div>
                  </div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>
                    {"adapter" in job ? job.adapter || "default" : copy.recoveryRefs} · {job.status}
                  </div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>
                    {copy.age}: {job.age_sec || 0}s
                  </div>
                  <button
                    onClick={() => markStuckWorkflowJobFailed(job.job_id)}
                    disabled={Boolean(workflowJobAction)}
                    className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded disabled:opacity-40"
                    style={{ background: "rgba(248,113,113,0.1)", color: "#F87171", border: "1px solid rgba(248,113,113,0.22)" }}
                  >
                    {workflowJobAction === job.job_id ? <RefreshCw size={12} /> : <Square size={12} />}
                    {workflowJobAction === job.job_id ? copy.markingJobFailed : copy.markJobFailed}
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-2 mt-3">
            {workflowJobs.length === 0 && (
              <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                {copy.noWorkflowJobs}
              </div>
            )}
            {workflowJobs.slice(0, 6).map((job) => (
              <div key={job.job_id} className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.8fr_0.8fr_auto] gap-3 items-start lg:items-center rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="min-w-0">
                  <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{job.title || job.job_id}</div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{job.job_id} · {job.workflow_type}</div>
                </div>
                <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>
                  {job.adapter || "default"} · {job.confirm_run ? "live" : "safe"}
                </div>
                <div className="flex items-center gap-2 min-w-0">
                  <StatusBadge status={job.status} />
                  <span className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{job.updated_at || job.created_at}</span>
                </div>
                <div className="flex gap-1.5 justify-end">
                  {job.result_task_id && (
                    <Link to={`/admin/tasks/${job.result_task_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(34,211,238,0.1)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>
                      {copy.taskId}
                    </Link>
                  )}
                  {job.result_run_id && (
                    <Link to={`/admin/runs/${job.result_run_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(45,212,191,0.1)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}>
                      {copy.runId}
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <CheckCircle2 size={14} style={{ color: "var(--mis-success)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.operatorTitle}</h2>
            </div>
            <p className="text-[11px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.operatorSummary}</p>
          </div>
          <StatusBadge status={gatewayReady ? "ready" : "planned"} label={gatewayReady ? copy.statusReady : copy.statusSetup} />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 mt-4">
          {operatorReadiness.map(item => (
            <div
              key={item.title}
              className="rounded-lg px-3 py-3"
              style={{
                background: item.attention ? "rgba(251,191,36,0.08)" : "var(--mis-surface2)",
                border: item.attention ? "1px solid rgba(251,191,36,0.28)" : "1px solid var(--mis-border)",
              }}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  {item.attention ? <AlertTriangle size={13} style={{ color: "var(--mis-warning)" }} /> : <CheckCircle2 size={13} style={{ color: "var(--mis-success)" }} />}
                  <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.title}</div>
                </div>
                <StatusBadge status={item.status} label={item.label} />
              </div>
              <p className="text-[10px] mt-2 leading-relaxed" style={{ color: "var(--mis-dim)" }}>{item.body}</p>
              <div className="text-[10px] mt-2 truncate" style={{ color: "var(--mis-muted)" }}>{item.meta}</div>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-lg p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.adapterRoutesTitle}</div>
              <div className="text-[10px] mt-0.5" style={{ color: "var(--mis-muted)" }}>{copy.adapterRoutesSummary}</div>
            </div>
            <StatusBadge status={adapterReadiness?.status || "unknown"} label={`${copy.recommendedAdapter}: ${recommendedAdapter}`} />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-3">
            {adapterRouteCards.map(({ item, liveReady, attention, checkSummary }) => (
              <div
                key={item.adapter}
                className="rounded px-3 py-2"
                style={{
                  background: attention ? "rgba(248,113,113,0.08)" : "var(--mis-bg)",
                  border: attention ? "1px solid rgba(248,113,113,0.22)" : "1px solid var(--mis-border)",
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    {attention ? <AlertTriangle size={13} style={{ color: "#F87171" }} /> : <CheckCircle2 size={13} style={{ color: liveReady || item.adapter === "mock" ? "var(--mis-success)" : "var(--mis-muted)" }} />}
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.adapter}</div>
                  </div>
                  <StatusBadge status={item.readiness} />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
                  <div className="rounded px-2 py-1" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
                    <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{copy.trustStatus}</div>
                    <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.trust_status || "—"}</div>
                  </div>
                  <div className="rounded px-2 py-1" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
                    <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{copy.liveReady}</div>
                    <div className="text-[10px] font-semibold truncate" style={{ color: liveReady ? "var(--mis-success)" : "var(--mis-dim)" }}>
                      {liveReady ? copy.yes : item.adapter === "mock" ? copy.no : copy.notLiveReady}
                    </div>
                  </div>
                </div>
                <div className="text-[10px] mt-2 truncate" style={{ color: "var(--mis-dim)" }}>
                  {copy.targetResource}: {item.target_resource || "—"}
                </div>
                <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
                  {checkSummary}
                </div>
                <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-cyan)" }}>
                  {copy.nextAction}: {item.recommended_action || "agentops worker readiness"}
                </div>
                {item.last_error && (
                  <div className="text-[10px] mt-1 truncate" style={{ color: "#F87171" }}>
                    {item.last_error}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck size={14} style={{ color: "var(--mis-cyan)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.gatewayTitle}</h2>
              <StatusBadge status={gatewayStatus?.status || "unknown"} />
            </div>
            <p className="text-[11px] mt-1 max-w-2xl" style={{ color: "var(--mis-dim)" }}>{copy.gatewaySummary}</p>
          </div>
          <div className="text-left lg:text-right">
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.authMode}</div>
            <div className="text-xs font-semibold mt-0.5" style={{ color: "var(--mis-text)" }}>
              {gatewayStatus?.auth.mode || "unknown"}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3 mt-4">
          {[
            { label: copy.authenticated, value: gatewayStatus?.auth.authenticated ? copy.yes : copy.no },
            { label: copy.gatewayWorkspace, value: gatewayStatus?.auth.workspace_id || "local-demo" },
            { label: copy.gatewayScopes, value: gatewayStatus?.auth.scopes.length ?? "—" },
            { label: copy.activeEnrollments, value: activeEnrollments },
            { label: copy.staleEnrollments, value: staleEnrollments },
          ].map((item) => (
            <div key={item.label} className="rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
              <div className="text-sm font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{item.value}</div>
            </div>
          ))}
        </div>
        <div className="rounded-lg p-3 mt-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.productionSecurity}</div>
                <StatusBadge status={securityReadiness?.status || "unknown"} label={securityReadiness?.production_ready ? copy.productionReady : copy.localDevOnly} />
              </div>
              <div className="text-[10px] mt-1 line-clamp-2" style={{ color: "var(--mis-muted)" }}>
                {securityReadiness?.contract || "local_dev_no_token is local-only"}
              </div>
            </div>
            <StatusBadge status={securityReadiness?.safety?.read_only ? "pass" : "fail"} label={securityReadiness?.safety?.read_only ? copy.readOnlyProof : copy.statusAttention} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
            {(securityReadiness?.gates || []).slice(0, 4).map((gate) => (
              <div key={gate.id} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{gate.label || copy.securityGate}</div>
                  <StatusBadge status={gate.status} />
                </div>
                <div className="text-[10px] mt-1 line-clamp-2" style={{ color: "var(--mis-muted)" }}>{gate.detail}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Activity size={14} style={{ color: "var(--mis-success)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.workerTitle}</h2>
              <StatusBadge status={workerStatus?.status || "unknown"} />
            </div>
            <p className="text-[11px] mt-1 max-w-2xl" style={{ color: "var(--mis-dim)" }}>{copy.workerSummary}</p>
            {dispatchResult && (
              <div className="text-[11px] mt-2" style={{ color: dispatchResult.includes("failed") ? "#F87171" : "var(--mis-success)" }}>
                {dispatchResult}
              </div>
            )}
          </div>
          <div className="flex gap-2 flex-wrap justify-end">
            {[
              { adapter: "mock" as const, label: copy.dispatchMock },
              { adapter: "hermes" as const, label: copy.dispatchHermes },
              { adapter: "openclaw" as const, label: copy.dispatchOpenClaw },
            ].map((item) => (
              <button
                key={item.adapter}
                onClick={() => runWorkerOnce(item.adapter)}
                disabled={Boolean(dispatching)}
                className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
                style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
              >
                {dispatching === item.adapter ? <RefreshCw size={12} /> : <Play size={12} />}
                {dispatching === item.adapter ? copy.dispatching : item.label}
              </button>
            ))}
          </div>
        </div>
        {renderActiveIntakeGate()}
        {lastWorkerDispatch && (
          <div className="rounded-lg p-3 mt-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>
                  {lastWorkerDispatch.adapter} · {lastWorkerDispatch.task_id}
                </div>
                <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
                  {copy.runId}: {lastWorkerDispatch.run_id || "—"} · {copy.agentPlan}: {lastWorkerDispatch.agent_plan_id || "—"}
                </div>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <StatusBadge status={lastWorkerDispatch.ok ? "completed" : "failed"} />
                <StatusBadge status={lastWorkerDispatch.evidence?.agent_plan_verified ? "pass" : "attention"} label={copy.agentPlan} />
                <StatusBadge status={lastWorkerDispatch.plan_evidence_pass ? "pass" : "attention"} label={copy.planEvidence} />
                <StatusBadge status={String(lastWorkerDispatch.evidence?.intake?.severity || "unknown")} label={copy.intakeGate} />
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 mt-3">
              {lastWorkerDispatch.task_id && (
                <Link to={`/admin/tasks/${lastWorkerDispatch.task_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>{copy.openTask}</Link>
              )}
              {lastWorkerDispatch.run_id && (
                <Link to={`/admin/runs/${lastWorkerDispatch.run_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}>{copy.openRun}</Link>
              )}
              {Object.entries(lastWorkerDispatch.evidence?.evidence_counts || {}).slice(0, 6).map(([key, value]) => (
                <span key={key} className="text-[10px] px-2 py-1 rounded" style={{ background: "var(--mis-bg)", color: "var(--mis-muted)", border: "1px solid var(--mis-border)" }}>
                  {key}: {value}
                </span>
              ))}
            </div>
          </div>
        )}
        <div className="flex gap-2 flex-wrap mt-4">
          {[
            { adapter: "mock" as const, label: copy.startMockDaemon },
            { adapter: "hermes" as const, label: copy.startHermesDaemon },
            { adapter: "openclaw" as const, label: copy.startOpenClawDaemon },
          ].map((item) => (
            <button
              key={item.adapter}
              onClick={() => startDaemon(item.adapter)}
              disabled={Boolean(dispatching) || workerStartBlocked}
              className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
              style={{ background: "rgba(45,212,191,0.12)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.22)" }}
            >
              {dispatching === `start-${item.adapter}` ? <RefreshCw size={12} /> : <Power size={12} />}
              {dispatching === `start-${item.adapter}` ? copy.starting : item.label}
            </button>
          ))}
          {[
            { adapter: "mock" as const, label: copy.restartMockDaemon },
            { adapter: "hermes" as const, label: copy.restartHermesDaemon },
            { adapter: "openclaw" as const, label: copy.restartOpenClawDaemon },
          ].map((item) => (
            <button
              key={`restart-${item.adapter}`}
              onClick={() => restartDaemon(item.adapter)}
              disabled={Boolean(dispatching) || workerStartBlocked}
              className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
              style={{ background: "rgba(122,90,248,0.1)", color: "#A78BFA", border: "1px solid rgba(122,90,248,0.2)" }}
            >
              {dispatching === `restart-${item.adapter}` ? <RefreshCw size={12} /> : <RotateCw size={12} />}
              {dispatching === `restart-${item.adapter}` ? copy.restarting : item.label}
            </button>
          ))}
          <button
            onClick={stopDaemons}
            disabled={Boolean(dispatching)}
            className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
            style={{ background: "rgba(248,113,113,0.1)", color: "#F87171", border: "1px solid rgba(248,113,113,0.22)" }}
          >
            {dispatching === "stop-daemons" ? <RefreshCw size={12} /> : <Square size={12} />}
            {dispatching === "stop-daemons" ? copy.stopping : copy.stopDaemons}
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 mt-4">
          {[
            { label: copy.workers, value: workerStatus?.worker_count ?? "—" },
            { label: copy.completedRuns, value: workerStatus?.recent_completed_runs ?? "—" },
            { label: copy.pendingTasks, value: workerStatus?.pending_worker_tasks ?? "—" },
            { label: copy.stuckTasks, value: workerStatus?.stuck_worker_tasks ?? "—", danger: (workerStatus?.stuck_worker_tasks || 0) > 0 },
          ].map((item) => (
            <div key={item.label} className="rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
              <div className="text-xs font-semibold truncate mt-1" style={{ color: item.danger ? "#F87171" : "var(--mis-text)" }}>{item.value}</div>
            </div>
          ))}
        </div>
        <div className="rounded-lg p-3 mt-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.stuckTasks}</div>
            <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.recentRun}: {workerStatus?.recent_runs?.[0]?.run_id || "—"}</div>
          </div>
          <div className="space-y-2 mt-2">
            {stuckTasks.length === 0 && (
              <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                {copy.noStuckTasks}
              </div>
            )}
            {stuckTasks.slice(0, 4).map(task => (
              <div key={task.task_id} className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.8fr_0.9fr_auto] gap-3 items-start lg:items-center rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                <div className="min-w-0">
                  <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{task.title}</div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{task.task_id} · {task.owner_agent_id || "—"}</div>
                </div>
                <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>{copy.age}: {task.age_sec || 0}s</div>
                <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>{copy.linkedRun}: {task.running_run_id || "—"}</div>
                <button
                  onClick={() => releaseStuckTask(task.task_id)}
                  disabled={Boolean(dispatching)}
                  className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded disabled:opacity-40"
                  style={{ background: "rgba(251,191,36,0.1)", color: "var(--mis-warning)", border: "1px solid rgba(251,191,36,0.22)" }}
                >
                  {dispatching === `release-${task.task_id}` ? <RefreshCw size={12} /> : <Square size={12} />}
                  {dispatching === `release-${task.task_id}` ? copy.releasingTask : copy.releaseTask}
                </button>
              </div>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-3">
          {(workerStatus?.daemons || []).map((daemon) => (
            <div key={daemon.adapter} className="rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="flex items-center justify-between gap-2">
                <div className="text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>{daemon.adapter}</div>
                <StatusBadge status={daemon.running ? "running" : daemon.status} />
              </div>
              <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-dim)" }}>
                {copy.daemonStatus}: {daemon.worker_status || daemon.status}
              </div>
              <div className="text-[10px] mt-0.5 truncate" style={{ color: "var(--mis-muted)" }}>
                {copy.daemonBackoff}: {daemon.last_sleep_reason || copy.noBackoff}{daemon.last_sleep_sec ? ` · ${daemon.last_sleep_sec}s` : ""}
              </div>
              <div className="text-[10px] mt-0.5 truncate" style={{ color: "var(--mis-dim)" }}>
                {copy.pid}: {daemon.pid || "—"} · {daemon.agent_id || "—"}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-1 mt-2">
                <div className="rounded px-1.5 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{copy.processed}</div>
                  <div className="text-[10px] font-semibold" style={{ color: "var(--mis-text)" }}>{daemon.processed ?? 0}</div>
                </div>
                <div className="rounded px-1.5 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{copy.iterations}</div>
                  <div className="text-[10px] font-semibold" style={{ color: "var(--mis-text)" }}>{daemon.iterations ?? 0}</div>
                </div>
                <div className="rounded px-1.5 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{copy.errors}</div>
                  <div className="text-[10px] font-semibold" style={{ color: (daemon.consecutive_errors || 0) > 0 ? "#F87171" : "var(--mis-text)" }}>
                    {daemon.consecutive_errors ?? 0}/{daemon.total_errors ?? 0}
                  </div>
                </div>
              </div>
              {daemon.last_error && (
                <div className="text-[10px] mt-2 truncate" style={{ color: "#F87171" }}>
                  {copy.lastError}: {String(daemon.last_error.error_message || daemon.last_error.error_type || "error")}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Activity size={14} style={{ color: "var(--mis-cyan)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.fleetTitle}</h2>
            </div>
            <p className="text-[11px] mt-1 max-w-2xl" style={{ color: "var(--mis-dim)" }}>{copy.fleetSummary}</p>
          </div>
          <StatusBadge status={workerFleet?.status || fleetHealth?.overall || "unknown"} label={String(fleetLaneSummary?.lane_count ?? 0)} />
        </div>

        <div className="rounded-lg p-3 mt-4" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.fleetLanes}</div>
              <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
                {workerFleet?.contract || fleetHealth?.contract || "Agent Gateway CLI/API"}
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <StatusBadge status="ready" label={`${copy.daemonStatus}: ${fleetLaneSummary?.running_local_daemons ?? runningDaemons}/${fleetLaneSummary?.local_daemon_count ?? workerStatus?.daemons?.length ?? 0}`} />
              <StatusBadge status={(fleetLaneSummary?.stale_remote_enrollments || 0) > 0 ? "attention" : "ready"} label={`${copy.remoteWorkersTitle}: ${fleetLaneSummary?.remote_worker_count ?? workerStatus?.remote_worker_count ?? 0}`} />
              <StatusBadge status={(fleetLaneSummary?.active_remote_sessions || 0) > 0 ? "ready" : "planned"} label={`${copy.activeSessions}: ${fleetLaneSummary?.active_remote_sessions ?? workerStatus?.active_remote_sessions ?? 0}`} />
            </div>
          </div>
          <div className="space-y-2 mt-3">
            {fleetLanes.length === 0 && (
              <div className="text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                {copy.noFleetLanes}
              </div>
            )}
            {fleetLanes.slice(0, 8).map((lane) => {
              const healthStatus = lane.health === "pass" ? "ready" : lane.health === "warn" ? "attention" : lane.health === "fail" ? "blocked" : "planned";
              return (
                <div key={lane.lane_id} className="grid grid-cols-1 xl:grid-cols-[1.1fr_0.75fr_0.75fr_1fr] gap-2 rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{lane.agent_name || lane.agent_id || lane.lane_id}</div>
                      <StatusBadge status={healthStatus} label={lane.health} />
                    </div>
                    <div className="text-[10px] truncate mt-1" style={{ color: "var(--mis-muted)" }}>
                      {copy.laneType}: {lane.lane_type} · {lane.adapter || lane.runtime_type || "—"} · {lane.safe_ref || "—"}
                    </div>
                  </div>
                  <div className="text-[10px]" style={{ color: "var(--mis-dim)" }}>
                    <div>{copy.laneHeartbeat}: {lane.heartbeat_state || "—"}</div>
                    <div className="truncate">{copy.laneLastSeen}: {lane.last_seen_at || "—"}</div>
                  </div>
                  <div className="text-[10px]" style={{ color: "var(--mis-dim)" }}>
                    <div>{copy.laneSession}: {lane.session_state || "—"}</div>
                    <div>{copy.activeSessions}: {lane.active_session_count ?? 0}</div>
                  </div>
                  <div className="text-[10px] truncate xl:text-right" style={{ color: "var(--mis-cyan)" }}>
                    {copy.laneNextAction}: {lane.next_action || "agentops worker status"}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-4 flex flex-col lg:flex-row lg:items-start justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.daemonLogs}</div>
            <p className="text-[10px] mt-1 max-w-2xl" style={{ color: "var(--mis-muted)" }}>{copy.fleetSummary}</p>
          </div>
          <div className="flex gap-1.5">
            {WORKER_ADAPTERS.map(adapter => (
              <button
                key={adapter}
                onClick={() => setSelectedLogAdapter(adapter)}
                className="text-[11px] px-3 py-1.5 rounded"
                style={{
                  background: selectedLogAdapter === adapter ? "rgba(34,211,238,0.14)" : "var(--mis-surface2)",
                  color: selectedLogAdapter === adapter ? "var(--mis-cyan)" : "var(--mis-muted)",
                  border: "1px solid var(--mis-border)",
                }}
              >
                {adapter}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mt-4">
          <div className="rounded-lg p-3 min-w-0" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between gap-2">
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.daemonLogs}</div>
              <StatusBadge status={selectedDaemonLog?.running ? "running" : selectedDaemonLog?.status || "unknown"} />
            </div>
            <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
              {copy.logPath}: {selectedDaemonLog?.log_path || "—"}
            </div>
            <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
              {copy.statePath}: {selectedDaemonLog?.state_path || "—"}
            </div>
            <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>
              {copy.daemonBackoff}: {selectedDaemonLog?.last_sleep_reason || copy.noBackoff}{selectedDaemonLog?.last_sleep_sec ? ` · ${selectedDaemonLog.last_sleep_sec}s` : ""}
            </div>
            {selectedDaemonLog?.last_error && (
              <div className="text-[10px] mt-2 rounded px-2 py-1" style={{ color: "#F87171", background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.18)" }}>
                {copy.lastError}: {String(selectedDaemonLog.last_error.error_message || selectedDaemonLog.last_error.error_type || "error")}
              </div>
            )}
            <pre
              className="mt-3 h-44 overflow-auto rounded p-3 text-[10px] leading-relaxed whitespace-pre-wrap"
              style={{ background: "var(--mis-bg)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}
            >
              {(selectedDaemonLog?.log_tail || []).length > 0 ? selectedDaemonLog?.log_tail?.slice(-28).join("\n") : copy.noLogs}
            </pre>
          </div>

          <div className="rounded-lg p-3 min-w-0" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="text-[11px] font-semibold mb-2" style={{ color: "var(--mis-text)" }}>{copy.recentEvents}</div>
            <div className="space-y-2 max-h-60 overflow-auto pr-1">
              {recentEvents.length === 0 && (
                <div className="text-[11px] rounded px-3 py-3" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.noEvents}
                </div>
              )}
              {recentEvents.slice(0, 8).map((event, index) => (
                <div key={`${eventText(event, "runtime_event_id", String(index))}-${index}`} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>
                      {eventText(event, "event_type")}
                    </div>
                    <StatusBadge status={eventText(event, "status", "unknown")} />
                  </div>
                  <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-dim)" }}>
                    {copy.eventAgent}: {eventText(event, "agent_id")} · {eventText(event, "created_at")}
                  </div>
                  <div className="text-[10px] mt-1 line-clamp-2" style={{ color: "var(--mis-muted)" }}>
                    {eventText(event, "output_summary", eventText(event, "input_summary"))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <KeyRound size={14} style={{ color: "var(--mis-cyan)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.enrollmentTitle}</h2>
            </div>
            <p className="text-[11px] mt-1 max-w-2xl" style={{ color: "var(--mis-dim)" }}>{copy.enrollmentSummary}</p>
            {enrollmentResult && (
              <div
                className="text-[11px] mt-2"
                style={{ color: enrollmentResult.includes("Error") || enrollmentResult.includes("error") ? "#F87171" : "var(--mis-success)" }}
              >
                {enrollmentResult}
              </div>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 shrink-0 w-full sm:w-auto">
            <div className="rounded-lg px-3 py-2 min-w-28" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.activeEnrollments}</div>
              <div className="text-sm font-semibold mt-1" style={{ color: "var(--mis-text)" }}>{activeEnrollments}</div>
            </div>
            <div className="rounded-lg px-3 py-2 min-w-28" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.staleEnrollments}</div>
              <div className="text-sm font-semibold mt-1" style={{ color: staleEnrollments > 0 ? "var(--mis-warning)" : "var(--mis-text)" }}>{staleEnrollments}</div>
            </div>
            <div className="rounded-lg px-3 py-2 min-w-28 sm:col-span-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.activeSessions}</div>
              <div className="text-sm font-semibold mt-1" style={{ color: "var(--mis-text)" }}>{activeSessions}</div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-6 gap-3 mt-4">
          <label className="md:col-span-2 text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.agentId}
            <input
              value={enrollmentForm.agent_id}
              onChange={(event) => updateEnrollmentForm("agent_id", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            />
          </label>
          <label className="md:col-span-2 text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.agentName}
            <input
              value={enrollmentForm.name}
              onChange={(event) => updateEnrollmentForm("name", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            />
          </label>
          <label className="text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.runtime}
            <select
              value={enrollmentForm.runtime_type}
              onChange={(event) => updateEnrollmentForm("runtime_type", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            >
              {["mock", "hermes", "openclaw", "codex", "claude_code", "openhands", "crewai", "langgraph"].map(runtime => (
                <option key={runtime} value={runtime}>{runtime}</option>
              ))}
            </select>
          </label>
          <label className="text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.workspace}
            <input
              value={enrollmentForm.workspace_id}
              onChange={(event) => updateEnrollmentForm("workspace_id", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            />
          </label>
          <label className="text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.ttlDays}
            <input
              type="number"
              min="1"
              value={enrollmentForm.ttl_days}
              onChange={(event) => updateEnrollmentForm("ttl_days", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            />
          </label>
          <label className="text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.heartbeat}
            <input
              type="number"
              min="30"
              value={enrollmentForm.heartbeat_timeout_sec}
              onChange={(event) => updateEnrollmentForm("heartbeat_timeout_sec", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            />
          </label>
          <label className="md:col-span-4 text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.scopes}
            <input
              value={enrollmentForm.scopes}
              onChange={(event) => updateEnrollmentForm("scopes", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            />
          </label>
          <div className="md:col-span-4 rounded-lg p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <ShieldCheck size={13} style={{ color: enrollmentPolicy?.approval_recommended ? "var(--mis-warning)" : "var(--mis-success)" }} />
                  <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.enrollmentPolicyTitle}</div>
                  <StatusBadge status={enrollmentPolicy?.status || "unknown"} />
                </div>
                <p className="text-[10px] mt-1" style={{ color: "var(--mis-muted)" }}>{copy.enrollmentPolicySummary}</p>
              </div>
              <div className="flex flex-wrap gap-1.5 shrink-0">
                <StatusBadge status={enrollmentPolicy?.risk_level || "unknown"} label={`${copy.riskLevel}: ${enrollmentPolicy?.risk_level || "—"}`} />
                <StatusBadge status={enrollmentPolicy?.approval_recommended ? "attention" : "pass"} label={enrollmentPolicy?.approval_recommended ? copy.approvalPath : copy.directCreatePath} />
              </div>
            </div>
            {enrollmentPolicyError && (
              <div className="text-[10px] mt-2" style={{ color: "#F87171" }}>{enrollmentPolicyError}</div>
            )}
            {enrollmentPolicy && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
                  {[
                    { label: copy.policyType, value: enrollmentPolicy.policy, status: enrollmentPolicy.policy },
                    { label: copy.recommendedPath, value: enrollmentPolicy.recommended_path, status: enrollmentPolicy.approval_recommended ? "attention" : "pass" },
                    { label: copy.workerWriteScopes, value: enrollmentPolicy.worker_write_scopes.length, status: enrollmentPolicy.worker_write_scopes.length > 0 ? "ready" : "planned" },
                    { label: copy.privilegedScopes, value: enrollmentPolicy.privileged_scopes.length, status: enrollmentPolicy.privileged_scopes.length > 0 ? "attention" : "pass" },
                  ].map((item) => (
                    <div key={item.label} className="rounded px-2 py-1" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                      <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                      <div className="flex items-center justify-between gap-2 mt-0.5">
                        <div className="text-[10px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.value}</div>
                        <StatusBadge status={item.status} />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {enrollmentPolicy.invalid_scopes.slice(0, 4).map(scope => (
                    <span key={`invalid-${scope}`} className="text-[9px] px-1.5 py-0.5 rounded" style={{ background: "rgba(248,113,113,0.08)", color: "#F87171", border: "1px solid rgba(248,113,113,0.18)" }}>
                      {copy.invalidScopes}: {scope}
                    </span>
                  ))}
                  {enrollmentPolicy.privileged_scopes.slice(0, 4).map(scope => (
                    <span key={`privileged-${scope}`} className="text-[9px] px-1.5 py-0.5 rounded" style={{ background: "rgba(251,191,36,0.08)", color: "var(--mis-warning)", border: "1px solid rgba(251,191,36,0.18)" }}>
                      {scope}
                    </span>
                  ))}
                  {enrollmentPolicy.missing_worker_scopes.slice(0, 4).map(scope => (
                    <span key={`missing-${scope}`} className="text-[9px] px-1.5 py-0.5 rounded" style={{ background: "var(--mis-bg)", color: "var(--mis-muted)", border: "1px solid var(--mis-border)" }}>
                      {copy.missingWorkerScopes}: {scope}
                    </span>
                  ))}
                </div>
                <div className="text-[10px] mt-2 truncate" style={{ color: "var(--mis-muted)" }}>
                  {(enrollmentPolicy.next_actions || [])[0] || "agentops enrollment policy-preview"}
                </div>
              </>
            )}
          </div>
          <div className="md:col-span-2 flex items-end gap-2">
            <button
              onClick={requestEnrollment}
              disabled={Boolean(enrollmentAction) || !enrollmentForm.agent_id.trim() || !enrollmentForm.name.trim() || scopeList.length === 0}
              className="w-full flex items-center justify-center gap-1.5 text-[11px] px-3 py-2 rounded disabled:opacity-50"
              style={{ background: "rgba(45,212,191,0.12)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.22)" }}
            >
              {enrollmentAction === "request" ? <RefreshCw size={12} /> : <ShieldCheck size={12} />}
              {enrollmentAction === "request" ? copy.requestingEnrollment : copy.requestEnrollment}
            </button>
            <button
              onClick={createEnrollment}
              disabled={Boolean(enrollmentAction) || !enrollmentForm.agent_id.trim() || !enrollmentForm.name.trim() || scopeList.length === 0}
              className="w-full flex items-center justify-center gap-1.5 text-[11px] px-3 py-2 rounded disabled:opacity-50"
              style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
            >
              {enrollmentAction === "create" ? <RefreshCw size={12} /> : <ShieldCheck size={12} />}
              {enrollmentAction === "create" ? copy.creatingToken : copy.createToken}
            </button>
          </div>
        </div>

        {(createdRequest || enrollmentApprovals.length > 0) && (
          <div className="rounded-lg p-3 mt-4" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.approvalRequestTitle}</div>
                {createdRequest && (
                  <div className="text-[10px] mt-1" style={{ color: "var(--mis-dim)" }}>
                    {createdRequest.request.request_id} · {createdRequest.approval.approval_id} · {copy.tokenShownOnce.replace("Copy this token now. It will not be shown again.", "No token is issued until approval.").replace("请现在复制 token。页面不会再次显示原始 token。", "审批前不会发放 token。")}
                  </div>
                )}
              </div>
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 w-full sm:w-auto">
              <input
                value={issueApprovalId}
                onChange={(event) => setIssueApprovalId(event.target.value)}
                placeholder="approval_id"
                className="w-full sm:w-56 rounded px-3 py-2 text-xs outline-none"
                  style={{ background: "var(--mis-bg)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
                />
                <button
                  onClick={() => issueApprovedEnrollment()}
                  disabled={Boolean(enrollmentAction) || !issueApprovalId.trim()}
                  className="flex items-center justify-center gap-1.5 text-[11px] px-3 py-2 rounded disabled:opacity-50"
                  style={{ background: "rgba(251,191,36,0.1)", color: "var(--mis-warning)", border: "1px solid rgba(251,191,36,0.25)" }}
                >
                  {enrollmentAction?.startsWith("issue-") ? <RefreshCw size={12} /> : <KeyRound size={12} />}
                  {enrollmentAction?.startsWith("issue-") ? copy.issuingApproved : copy.issueApproved}
                </button>
              </div>
            </div>
            <div className="space-y-2 mt-3">
              {enrollmentApprovals.length === 0 && (
                <div className="text-[11px] rounded px-3 py-3" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  {copy.noApprovalRequests}
                </div>
              )}
              {enrollmentApprovals.slice(0, 5).map((approval) => (
                <div key={approval.approval_id} className="grid grid-cols-1 lg:grid-cols-[1.1fr_1.3fr_0.8fr_auto] items-start lg:items-center gap-3 rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{approval.requested_by_agent_id}</div>
                    <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{approval.approval_id}</div>
                  </div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>{approval.reason}</div>
                  <StatusBadge status={approval.decision} />
                  <div className="flex flex-wrap justify-start lg:justify-end gap-1.5">
                    <button
                      onClick={() => decideEnrollmentApproval(approval.approval_id, "approve")}
                      disabled={approval.decision !== "pending" || Boolean(enrollmentAction)}
                      className="text-[11px] px-2.5 py-1.5 rounded disabled:opacity-40"
                      style={{ background: "rgba(45,212,191,0.12)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.2)" }}
                    >
                      {enrollmentAction === `approve-${approval.approval_id}` ? copy.creatingToken : copy.approveRequest}
                    </button>
                    <button
                      onClick={() => decideEnrollmentApproval(approval.approval_id, "reject")}
                      disabled={approval.decision !== "pending" || Boolean(enrollmentAction)}
                      className="text-[11px] px-2.5 py-1.5 rounded disabled:opacity-40"
                      style={{ background: "rgba(248,113,113,0.1)", color: "#F87171", border: "1px solid rgba(248,113,113,0.22)" }}
                    >
                      {enrollmentAction === `reject-${approval.approval_id}` ? copy.revokingToken : copy.rejectRequest}
                    </button>
                    <button
                      onClick={() => issueApprovedEnrollment(approval.approval_id)}
                      disabled={approval.decision !== "approved" || Boolean(enrollmentAction)}
                      className="text-[11px] px-2.5 py-1.5 rounded disabled:opacity-40"
                      style={{ background: "rgba(251,191,36,0.1)", color: "var(--mis-warning)", border: "1px solid rgba(251,191,36,0.22)" }}
                    >
                      {enrollmentAction === `issue-${approval.approval_id}` ? copy.issuingApproved : copy.issueApproved}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-1.5 mt-3">
          <span className="text-[10px] px-2 py-1" style={{ color: "var(--mis-muted)" }}>{copy.scopePresets}</span>
          {GATEWAY_SCOPE_PRESETS.map(preset => (
            <button
              key={preset.id}
              onClick={() => updateEnrollmentForm("scopes", preset.scopes.join(", "))}
              className="text-[10px] px-2 py-1 rounded"
              style={{ background: "rgba(122,90,248,0.1)", color: "#A78BFA", border: "1px solid rgba(122,90,248,0.2)" }}
            >
              {presetLabel(preset.id)}
            </button>
          ))}
          {validScopes.map(scope => (
            <button
              key={scope}
              onClick={() => {
                if (scopeList.includes(scope)) return;
                updateEnrollmentForm("scopes", [...scopeList, scope].join(", "));
              }}
              className="text-[10px] px-2 py-1 rounded"
              style={{ background: scopeList.includes(scope) ? "rgba(45,212,191,0.12)" : "var(--mis-surface2)", color: scopeList.includes(scope) ? "var(--mis-success)" : "var(--mis-muted)", border: "1px solid var(--mis-border)" }}
            >
              {scope}
            </button>
          ))}
        </div>

        {createdToken && (
          <div className="rounded-lg p-3 mt-4" style={{ background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.28)" }}>
            <div className="text-[11px] font-semibold" style={{ color: "var(--mis-warning)" }}>{copy.tokenShownOnce}</div>
            <div className="mt-2 text-[11px] font-mono break-all" style={{ color: "var(--mis-text)" }}>{createdToken.token}</div>
            <div className="mt-2 text-[10px]" style={{ color: "var(--mis-dim)" }}>
              {createdToken.agent_id} · {createdToken.token_id} · {copy.expires}: {createdToken.expires_at}
            </div>
            {createdToken.next_steps && (
              <div className="mt-4 rounded-lg p-3" style={{ background: "var(--mis-bg)", border: "1px solid rgba(251,191,36,0.18)" }}>
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.launchPacket}</div>
                <div className="text-[10px] mt-1" style={{ color: "var(--mis-muted)" }}>
                  {createdToken.next_steps.token_policy}
                </div>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 mt-3">
                  <div className="min-w-0">
                    <div className="text-[10px] mb-1" style={{ color: "var(--mis-muted)" }}>{copy.envSetup}</div>
                    <pre className="rounded p-2 text-[10px] whitespace-pre-wrap break-all" style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}>
                      {createdToken.next_steps.env.join("\n")}
                    </pre>
                  </div>
                  <div className="min-w-0 space-y-2">
                    {[
                      { label: copy.installCommand, value: createdToken.next_steps.install || "" },
                      { label: copy.verifyCommand, value: createdToken.next_steps.verify },
                      { label: copy.preflightCommand, value: createdToken.next_steps.preflight || "" },
                      { label: copy.sessionCommand, value: createdToken.next_steps.session || "" },
                      { label: copy.heartbeatCommand, value: createdToken.next_steps.heartbeat },
                      { label: copy.runOnceCommand, value: createdToken.next_steps.run_once },
                      { label: copy.runLoopCommand, value: createdToken.next_steps.run_loop },
                      { label: copy.launchdTemplate, value: createdToken.next_steps.launchd_template || "" },
                      { label: copy.systemdTemplate, value: createdToken.next_steps.systemd_template || "" },
                      { label: copy.fallbackCommand, value: createdToken.next_steps.repo_fallback_run_once || "" },
                    ].filter(item => item.value).map(item => (
                      <div key={item.label}>
                        <div className="text-[10px] mb-1" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                        <code className="block rounded px-2 py-1 text-[10px] break-all" style={{ background: "var(--mis-surface2)", color: "var(--mis-cyan)", border: "1px solid var(--mis-border)" }}>
                          {item.value}
                        </code>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="mt-4">
          <div className="text-[11px] font-semibold mb-2" style={{ color: "var(--mis-text)" }}>{copy.recentEnrollments}</div>
          <div className="space-y-2">
            {enrollments.length === 0 && (
              <div className="text-[11px] rounded-lg px-3 py-3" style={{ color: "var(--mis-muted)", background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                {copy.noEnrollments}
              </div>
            )}
            {enrollments.slice(0, 6).map((item) => (
              <div key={item.token_id} className="grid grid-cols-1 xl:grid-cols-[1.2fr_1.1fr_0.9fr_1.3fr_auto] gap-3 items-start xl:items-center rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                <div className="min-w-0">
                  <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.agent_id}</div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{copy.tokenId}: {item.token_id}</div>
                </div>
                <div className="flex items-center gap-2 min-w-0">
                  <StatusBadge status={item.status} />
                  <StatusBadge status={item.heartbeat_state} />
                </div>
                <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>
                  {copy.lastHeartbeat}: {item.last_heartbeat_at || "—"}
                </div>
                <div className="flex flex-wrap gap-1 min-w-0">
                  {item.scopes.slice(0, 4).map(scope => (
                    <span key={scope} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(34,211,238,0.08)", color: "var(--mis-cyan)" }}>
                      {scope}
                    </span>
                  ))}
                  {item.scopes.length > 4 && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "var(--mis-surface)", color: "var(--mis-muted)" }}>
                      +{item.scopes.length - 4}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5 justify-start xl:justify-end">
                  <button
                    onClick={() => rotateEnrollment(item.token_id)}
                    disabled={item.status !== "active" || Boolean(enrollmentAction)}
                    className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded disabled:opacity-40"
                    style={{ background: "rgba(34,211,238,0.1)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
                  >
                    {enrollmentAction === `rotate-${item.token_id}` ? <RefreshCw size={12} /> : <RotateCw size={12} />}
                    {enrollmentAction === `rotate-${item.token_id}` ? copy.rotatingToken : copy.rotateToken}
                  </button>
                  <button
                    onClick={() => revokeEnrollment(item.token_id)}
                    disabled={item.status !== "active" || Boolean(enrollmentAction)}
                    className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded disabled:opacity-40"
                    style={{ background: "rgba(248,113,113,0.1)", color: "#F87171", border: "1px solid rgba(248,113,113,0.22)" }}
                  >
                    {enrollmentAction === `revoke-${item.token_id}` ? <RefreshCw size={12} /> : <Trash2 size={12} />}
                    {enrollmentAction === `revoke-${item.token_id}` ? copy.revokingToken : copy.revokeToken}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4">
          <div className="text-[11px] font-semibold mb-2" style={{ color: "var(--mis-text)" }}>{copy.recentSessions}</div>
          <div className="space-y-2">
            {sessions.length === 0 && (
              <div className="text-[11px] rounded-lg px-3 py-3" style={{ color: "var(--mis-muted)", background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                {copy.noSessions}
              </div>
            )}
            {sessions.slice(0, 6).map((item) => (
              <div key={item.session_id} className="grid grid-cols-1 xl:grid-cols-[1.1fr_1fr_1.1fr_1.3fr_auto] gap-3 items-start xl:items-center rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                <div className="min-w-0">
                  <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.agent_id}</div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{copy.sessionId}: {item.session_id}</div>
                </div>
                <div className="flex items-center gap-2 min-w-0">
                  <StatusBadge status={item.session_state} />
                  {item.session_state !== item.status && <StatusBadge status={item.status} />}
                </div>
                <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>
                  {copy.lastUsed}: {item.last_used_at || "—"}
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>
                    {copy.parentToken}: {item.parent_token_id || "—"}
                  </div>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {item.scopes.slice(0, 3).map(scope => (
                      <span key={scope} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "rgba(122,90,248,0.1)", color: "#A78BFA" }}>
                        {scope}
                      </span>
                    ))}
                    {item.scopes.length > 3 && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "var(--mis-surface)", color: "var(--mis-muted)" }}>
                        +{item.scopes.length - 3}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex justify-start xl:justify-end">
                  <button
                    onClick={() => revokeSession(item.session_id)}
                    disabled={item.session_state !== "active" || Boolean(enrollmentAction)}
                    className="flex items-center gap-1 text-[11px] px-2.5 py-1.5 rounded disabled:opacity-40"
                    style={{ background: "rgba(248,113,113,0.1)", color: "#F87171", border: "1px solid rgba(248,113,113,0.22)" }}
                  >
                    {enrollmentAction === `revoke-session-${item.session_id}` ? <RefreshCw size={12} /> : <Trash2 size={12} />}
                    {enrollmentAction === `revoke-session-${item.session_id}` ? copy.revokingSession : copy.revokeSession}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Agent cards grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {agents.map(agent => {
          const budgetPct = Math.min(100, (agent.budget_used_usd / agent.budget_limit_usd) * 100);
          const rtColor = RUNTIME_COLOR[agent.runtime_type] ?? "var(--mis-muted)";

          return (
            <Link
              key={agent.agent_id}
              to={`/admin/agents/${agent.agent_id}`}
              className="block rounded-xl p-5 hover:opacity-90 transition-opacity"
              style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
            >
              {/* Top row */}
              <div className="flex items-start gap-3 mb-4">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                  style={{ background: `${rtColor}15`, color: rtColor }}
                >
                  <Bot size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{agent.name}</span>
                    <StatusBadge status={agent.status} />
                  </div>
                  <div className="text-[11px] mt-0.5" style={{ color: "var(--mis-muted)" }}>{agent.role}</div>
                </div>
              </div>

              {/* Runtime + model */}
              <div className="flex gap-3 mb-3">
                <span
                  className="text-[10px] px-2 py-0.5 rounded font-medium"
                  style={{ background: `${rtColor}15`, color: rtColor }}
                >
                  {agent.runtime_type}
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
                  {agent.model_name || "—"}
                </span>
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3">
                <div>
                  <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.runs}</div>
                  <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{agent.run_count}</div>
                </div>
                <div>
                  <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.success}</div>
                  <div
                    className="text-xs font-semibold"
                    style={{ color: agent.success_rate >= 0.8 ? "var(--mis-success)" : "var(--mis-warning)" }}
                  >
                    {Math.round(agent.success_rate * 100)}%
                  </div>
                </div>
                <div>
                  <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.approvals}</div>
                  <div className="text-xs font-semibold" style={{ color: agent.approval_count > 5 ? "#FBBF24" : "var(--mis-text)" }}>
                    {agent.approval_count}
                  </div>
                </div>
              </div>

              {/* Budget bar */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.budget}</span>
                  <span className="text-[10px]" style={{ color: "var(--mis-dim)" }}>
                    ${agent.budget_used_usd.toFixed(2)} / ${agent.budget_limit_usd}
                  </span>
                </div>
                <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--mis-border)" }}>
                  <div
                    className="h-1.5 rounded-full"
                    style={{
                      width: `${budgetPct}%`,
                      background: budgetPct > 80 ? "var(--mis-warning)" : "var(--mis-success)",
                    }}
                  />
                </div>
              </div>

              {/* Allowed tools preview */}
              <div className="flex flex-wrap gap-1 mt-3">
                {agent.allowed_tools.slice(0, 3).map(t => (
                  <span key={t} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
                    {t}
                  </span>
                ))}
                {agent.allowed_tools.length > 3 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
                    +{agent.allowed_tools.length - 3} {copy.more}
                  </span>
                )}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
