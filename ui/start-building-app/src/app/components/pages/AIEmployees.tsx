import { Link } from "react-router";
import { useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, Play, RefreshCw, Activity, Power, Square, KeyRound, ShieldCheck, Trash2, RotateCw } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import {
  createAgentGatewayEnrollment,
  decideApproval,
  dispatchLocalWorkerOnce,
  issueApprovedAgentGatewayEnrollment,
  loadApprovals,
  loadAgentGatewayEnrollments,
  loadAgentGatewaySessions,
  loadAgentGatewayStatus,
  loadAgents,
  loadDashboard,
  loadStuckWorkflowJobs,
  loadWorkerAdapterReadiness,
  loadWorkerDaemonLogs,
  loadWorkerStatus,
  loadWorkflowJobs,
  markWorkflowJobFailed,
  releaseWorkerTask,
  revokeAgentGatewayEnrollment,
  revokeAgentGatewaySession,
  rotateAgentGatewayEnrollment,
  runCustomerWorkerTaskWorkflow,
  requestAgentGatewayEnrollment,
  startLocalWorkerDaemon,
  stopLocalWorkerDaemon,
  submitCustomerWorkerTaskJob,
  useLiveData,
  type AgentGatewayEnrollmentCreateResult,
  type AgentGatewayEnrollmentRequestResult,
  type CustomerTaskWorkflowResult,
  type WorkerAdapterName,
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
    scopes: ["agents:write", "agents:heartbeat", "tasks:create", "tasks:read", "tasks:claim", "runs:write", "toolcalls:write", "artifacts:write", "approvals:request", "memories:propose", "evaluations:submit", "audit:write"],
  },
];

const WORKER_ADAPTERS = ["mock", "hermes", "openclaw"] as const;

export function AIEmployees() {
  const { locale } = usePreferences();
  const [dispatching, setDispatching] = useState<string | null>(null);
  const [dispatchResult, setDispatchResult] = useState<string | null>(null);
  const [customerTaskBusy, setCustomerTaskBusy] = useState(false);
  const [customerTaskError, setCustomerTaskError] = useState<string | null>(null);
  const [customerTaskResult, setCustomerTaskResult] = useState<CustomerTaskWorkflowResult | null>(null);
  const [customerTaskJob, setCustomerTaskJob] = useState<WorkflowJob | null>(null);
  const [workflowJobAction, setWorkflowJobAction] = useState<string | null>(null);
  const [workflowJobResult, setWorkflowJobResult] = useState<string | null>(null);
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
  const [enrollmentAction, setEnrollmentAction] = useState<string | null>(null);
  const [enrollmentResult, setEnrollmentResult] = useState<string | null>(null);
  const [createdToken, setCreatedToken] = useState<AgentGatewayEnrollmentCreateResult | null>(null);
  const [createdRequest, setCreatedRequest] = useState<AgentGatewayEnrollmentRequestResult | null>(null);
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
    const [metrics, workerStatus, adapterReadiness, enrollmentPayload, sessionPayload, gatewayStatus, approvals, daemonLogs, workflowJobs, stuckWorkflowJobs] = await Promise.all([
      loadDashboard(),
      loadWorkerStatus(),
      loadWorkerAdapterReadiness(),
      loadAgentGatewayEnrollments(),
      loadAgentGatewaySessions(),
      loadAgentGatewayStatus(),
      loadApprovals(),
      Promise.all(WORKER_ADAPTERS.map(adapter => loadWorkerDaemonLogs(adapter))),
      loadWorkflowJobs(8),
      loadStuckWorkflowJobs(30, 8),
    ]);
    const agents = await loadAgents(metrics);
    return { agents, workerStatus, adapterReadiness, enrollmentPayload, sessionPayload, gatewayStatus, approvals, daemonLogs, workflowJobs, stuckWorkflowJobs };
  }, []);
  const agents = data?.agents || [];
  const workerStatus = data?.workerStatus;
  const adapterReadiness = data?.adapterReadiness;
  const fleetHealth = workerStatus?.fleet_health;
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
      overallFleetHealth: "Fleet health",
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
      stopDaemons: "Stop daemons",
      dispatching: "Dispatching...",
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
      daemonLogs: "Daemon logs",
      recentEvents: "Recent gateway events",
      logPath: "Log path",
      noLogs: "No log lines yet.",
      noEvents: "No runtime events yet.",
      eventStatus: "Status",
      eventAgent: "Agent",
      enrollmentTitle: "Remote Agent Enrollment",
      enrollmentSummary: "Issue scoped tokens for agents running on another laptop or server. The token is shown once; MIS stores only a hash.",
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
      overallFleetHealth: "Fleet 健康",
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
      stopDaemons: "停止常驻 worker",
      dispatching: "正在派发...",
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
      daemonLogs: "Daemon 日志",
      recentEvents: "最近网关事件",
      logPath: "日志路径",
      noLogs: "暂无日志行。",
      noEvents: "暂无运行事件。",
      eventStatus: "状态",
      eventAgent: "Agent",
      enrollmentTitle: "远程 Agent 接入",
      enrollmentSummary: "给运行在另一台电脑或服务器上的 agent 发放带权限范围的 token。token 只显示一次，MIS 只保存 hash。",
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

  const updateCustomerTaskText = (field: "title" | "description", value: string) => {
    setCustomerTaskForm(prev => ({ ...prev, [field]: value }));
  };

  const updateCustomerTaskAdapter = (adapter: (typeof WORKER_ADAPTERS)[number]) => {
    setCustomerTaskForm(prev => ({ ...prev, adapter }));
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
      const runId = result.worker_result?.results?.[0]?.run_id || result.task_id;
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
      const pid = result.daemon?.pid ? `pid ${result.daemon.pid}` : result.already_running ? "already running" : "started";
      setDispatchResult(`${adapter} daemon: ${result.ok ? "ok" : "failed"} · ${pid}`);
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

  const updateEnrollmentForm = (field: keyof typeof enrollmentForm, value: string) => {
    setEnrollmentForm(prev => ({ ...prev, [field]: value }));
  };

  const scopeList = enrollmentForm.scopes
    .split(",")
    .map(item => item.trim())
    .filter(Boolean);

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
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex items-start justify-between gap-4">
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
          <div className="text-right shrink-0">
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.recommendedAdapter}</div>
            <div className="text-sm font-semibold mt-0.5" style={{ color: "var(--mis-text)" }}>{recommendedAdapter}</div>
          </div>
        </div>

        <div className="grid grid-cols-6 gap-3 mt-4">
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

        <div className="grid grid-cols-[1.35fr_1fr] gap-4 mt-4">
          <div className="rounded-lg p-3 min-w-0" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.healthGates}</div>
              <StatusBadge status={fleetHealth?.overall || "unknown"} label={String(fleetGates.length)} />
            </div>
            <div className="grid grid-cols-2 gap-2 mt-3">
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
                <div className="col-span-2 text-[11px] rounded px-3 py-2" style={{ color: "var(--mis-muted)", background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
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

        <div className="grid grid-cols-[1.1fr_0.9fr] gap-4 mt-4">
          <div className="rounded-lg p-3 min-w-0" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between gap-3">
              <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.remoteWorkersTitle}</div>
              <div className="flex gap-1.5">
                <StatusBadge status="fresh" label={`${copy.heartbeatFresh}: ${workerStatus?.fresh_remote_enrollments ?? 0}`} />
                <StatusBadge status="stale" label={`${copy.heartbeatStale}: ${workerStatus?.stale_remote_enrollments ?? 0}`} />
                <StatusBadge status="never_seen" label={`${copy.heartbeatNeverSeen}: ${workerStatus?.never_seen_remote_enrollments ?? 0}`} />
              </div>
            </div>
            <div className="grid grid-cols-4 gap-2 mt-3">
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
                <div key={`${worker.agent_id}-${worker.token_ref}`} className="grid grid-cols-[1fr_0.55fr_0.55fr_0.7fr] gap-2 items-center rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
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
        <div className="flex items-start justify-between gap-4">
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
          <div className="flex gap-2 shrink-0 flex-wrap justify-end">
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

        <div className="grid grid-cols-[1fr_180px] gap-3 mt-4">
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
          <label className="col-span-2 text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
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
          <div className="grid grid-cols-3 gap-2 mt-2">
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
                <div className="grid grid-cols-4 gap-2">
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
                <div className="grid grid-cols-4 gap-2">
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
                <div key={job.job_id} className="grid grid-cols-[1.1fr_0.7fr_0.7fr_auto] gap-3 items-center rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
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
              <div key={job.job_id} className="grid grid-cols-[1.1fr_0.8fr_0.8fr_auto] gap-3 items-center rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
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
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <CheckCircle2 size={14} style={{ color: "var(--mis-success)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.operatorTitle}</h2>
            </div>
            <p className="text-[11px] mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>{copy.operatorSummary}</p>
          </div>
          <StatusBadge status={gatewayReady ? "ready" : "planned"} label={gatewayReady ? copy.statusReady : copy.statusSetup} />
        </div>
        <div className="grid grid-cols-4 gap-3 mt-4">
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
          <div className="grid grid-cols-3 gap-3 mt-3">
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
                <div className="grid grid-cols-2 gap-2 mt-2">
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
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck size={14} style={{ color: "var(--mis-cyan)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.gatewayTitle}</h2>
              <StatusBadge status={gatewayStatus?.status || "unknown"} />
            </div>
            <p className="text-[11px] mt-1 max-w-2xl" style={{ color: "var(--mis-dim)" }}>{copy.gatewaySummary}</p>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.authMode}</div>
            <div className="text-xs font-semibold mt-0.5" style={{ color: "var(--mis-text)" }}>
              {gatewayStatus?.auth.mode || "unknown"}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-5 gap-3 mt-4">
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
      </div>

      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex items-start justify-between gap-4">
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
        <div className="flex gap-2 flex-wrap mt-4">
          {[
            { adapter: "mock" as const, label: copy.startMockDaemon },
            { adapter: "hermes" as const, label: copy.startHermesDaemon },
            { adapter: "openclaw" as const, label: copy.startOpenClawDaemon },
          ].map((item) => (
            <button
              key={item.adapter}
              onClick={() => startDaemon(item.adapter)}
              disabled={Boolean(dispatching)}
              className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
              style={{ background: "rgba(45,212,191,0.12)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.22)" }}
            >
              {dispatching === `start-${item.adapter}` ? <RefreshCw size={12} /> : <Power size={12} />}
              {dispatching === `start-${item.adapter}` ? copy.starting : item.label}
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
        <div className="grid grid-cols-4 gap-3 mt-4">
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
              <div key={task.task_id} className="grid grid-cols-[1.1fr_0.8fr_0.9fr_auto] gap-3 items-center rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
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
        <div className="grid grid-cols-3 gap-3 mt-3">
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
              <div className="grid grid-cols-3 gap-1 mt-2">
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
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Activity size={14} style={{ color: "var(--mis-cyan)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.fleetTitle}</h2>
            </div>
            <p className="text-[11px] mt-1 max-w-2xl" style={{ color: "var(--mis-dim)" }}>{copy.fleetSummary}</p>
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

        <div className="grid grid-cols-2 gap-4 mt-4">
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
        <div className="flex items-start justify-between gap-4">
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
          <div className="grid grid-cols-2 gap-2 shrink-0">
            <div className="rounded-lg px-3 py-2 min-w-28" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.activeEnrollments}</div>
              <div className="text-sm font-semibold mt-1" style={{ color: "var(--mis-text)" }}>{activeEnrollments}</div>
            </div>
            <div className="rounded-lg px-3 py-2 min-w-28" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.staleEnrollments}</div>
              <div className="text-sm font-semibold mt-1" style={{ color: staleEnrollments > 0 ? "var(--mis-warning)" : "var(--mis-text)" }}>{staleEnrollments}</div>
            </div>
            <div className="rounded-lg px-3 py-2 min-w-28 col-span-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.activeSessions}</div>
              <div className="text-sm font-semibold mt-1" style={{ color: "var(--mis-text)" }}>{activeSessions}</div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-6 gap-3 mt-4">
          <label className="col-span-2 text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.agentId}
            <input
              value={enrollmentForm.agent_id}
              onChange={(event) => updateEnrollmentForm("agent_id", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            />
          </label>
          <label className="col-span-2 text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
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
          <label className="col-span-4 text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>
            {copy.scopes}
            <input
              value={enrollmentForm.scopes}
              onChange={(event) => updateEnrollmentForm("scopes", event.target.value)}
              className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            />
          </label>
          <div className="flex items-end gap-2">
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
              <div className="flex items-center gap-2">
                <input
                  value={issueApprovalId}
                  onChange={(event) => setIssueApprovalId(event.target.value)}
                  placeholder="approval_id"
                  className="w-56 rounded px-3 py-2 text-xs outline-none"
                  style={{ background: "var(--mis-bg)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
                />
                <button
                  onClick={() => issueApprovedEnrollment()}
                  disabled={Boolean(enrollmentAction) || !issueApprovalId.trim()}
                  className="flex items-center gap-1.5 text-[11px] px-3 py-2 rounded disabled:opacity-50"
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
                <div key={approval.approval_id} className="grid grid-cols-[1.1fr_1.3fr_0.8fr_auto] items-center gap-3 rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                  <div className="min-w-0">
                    <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{approval.requested_by_agent_id}</div>
                    <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{approval.approval_id}</div>
                  </div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-dim)" }}>{approval.reason}</div>
                  <StatusBadge status={approval.decision} />
                  <div className="flex justify-end gap-1.5">
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
                <div className="grid grid-cols-2 gap-3 mt-3">
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
              <div key={item.token_id} className="grid grid-cols-[1.2fr_1.1fr_0.9fr_1.3fr_auto] gap-3 items-center rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
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
                <div className="flex gap-1.5 justify-end">
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
              <div key={item.session_id} className="grid grid-cols-[1.1fr_1fr_1.1fr_1.3fr_auto] gap-3 items-center rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
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
                <div className="flex justify-end">
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
      <div className="grid grid-cols-2 gap-4">
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
              <div className="grid grid-cols-3 gap-2 mb-3">
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
