import { Link } from "react-router";
import { useState } from "react";
import { Bot, Play, RefreshCw, Activity, Power, Square, KeyRound, ShieldCheck, Trash2, RotateCw } from "lucide-react";
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
  loadWorkerDaemonLogs,
  loadWorkerStatus,
  releaseWorkerTask,
  revokeAgentGatewayEnrollment,
  revokeAgentGatewaySession,
  rotateAgentGatewayEnrollment,
  requestAgentGatewayEnrollment,
  startLocalWorkerDaemon,
  stopLocalWorkerDaemon,
  useLiveData,
  type AgentGatewayEnrollmentCreateResult,
  type AgentGatewayEnrollmentRequestResult,
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
    scopes: ["agents:write", "agents:heartbeat", "tasks:read", "tasks:claim", "runs:write", "toolcalls:write", "artifacts:write", "approvals:request", "memories:propose", "evaluations:submit", "audit:write"],
  },
];

const WORKER_ADAPTERS = ["mock", "hermes", "openclaw"] as const;

export function AIEmployees() {
  const { locale } = usePreferences();
  const [dispatching, setDispatching] = useState<string | null>(null);
  const [dispatchResult, setDispatchResult] = useState<string | null>(null);
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
    const [metrics, workerStatus, enrollmentPayload, sessionPayload, gatewayStatus, approvals, daemonLogs] = await Promise.all([
      loadDashboard(),
      loadWorkerStatus(),
      loadAgentGatewayEnrollments(),
      loadAgentGatewaySessions(),
      loadAgentGatewayStatus(),
      loadApprovals(),
      Promise.all(WORKER_ADAPTERS.map(adapter => loadWorkerDaemonLogs(adapter))),
    ]);
    const agents = await loadAgents(metrics);
    return { agents, workerStatus, enrollmentPayload, sessionPayload, gatewayStatus, approvals, daemonLogs };
  }, []);
  const agents = data?.agents || [];
  const workerStatus = data?.workerStatus;
  const daemonLogs = data?.daemonLogs || [];
  const selectedDaemonLog = daemonLogs.find(item => item.daemon.adapter === selectedLogAdapter)?.daemon;
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
  const copy = pick(locale, {
    en: {
      title: "AI Employees",
      summary: `${agents.length} registered agents · ${activeAgents} active · live backend`,
      loading: "Loading live agents...",
      backendUnavailable: "Live backend unavailable",
      refresh: "Refresh live agents",
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
      verifyCommand: "Verify",
      sessionCommand: "Mint session",
      heartbeatCommand: "Heartbeat",
      runOnceCommand: "Run once",
      runLoopCommand: "Run loop",
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
    },
    zh: {
      title: "AI 员工",
      summary: `${agents.length} 个已注册代理 · ${activeAgents} 个运行中 · 连接本地后端`,
      loading: "正在加载实时代理...",
      backendUnavailable: "本地后端不可用",
      refresh: "刷新实时代理",
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
      verifyCommand: "自检",
      sessionCommand: "换取短期 Session",
      heartbeatCommand: "心跳",
      runOnceCommand: "单轮运行",
      runLoopCommand: "常驻运行",
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
    },
  });

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
                      { label: copy.verifyCommand, value: createdToken.next_steps.verify },
                      { label: copy.sessionCommand, value: createdToken.next_steps.session || "" },
                      { label: copy.heartbeatCommand, value: createdToken.next_steps.heartbeat },
                      { label: copy.runOnceCommand, value: createdToken.next_steps.run_once },
                      { label: copy.runLoopCommand, value: createdToken.next_steps.run_loop },
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
