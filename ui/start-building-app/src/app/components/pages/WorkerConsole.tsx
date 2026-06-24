import { useState } from "react";
import { Link } from "react-router";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Copy,
  Play,
  Power,
  RefreshCw,
  RotateCw,
  ShieldCheck,
  Square,
  TerminalSquare,
} from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import {
  dispatchLocalWorkerOnce,
  loadOperatorExecutionMode,
  loadWorkerAdapterReadiness,
  loadWorkerFleet,
  loadWorkerFleetHygiene,
  loadWorkerStatus,
  applyWorkerFleetHygiene,
  restartLocalWorkerDaemon,
  startLocalWorkerDaemon,
  stopLocalWorkerDaemon,
  useLiveData,
  type OperatorExecutionModePayload,
  type WorkerAdapterName,
  type WorkerAdapterReadinessPayload,
  type WorkerDaemonResult,
  type WorkerDispatchResult,
  type WorkerFleetHygienePayload,
  type WorkerFleetPayload,
  type WorkerStatusPayload,
} from "../../data/liveApi";
import { pick, usePreferences } from "../../context/PreferencesContext";

const WORKER_ADAPTERS: WorkerAdapterName[] = ["mock", "hermes", "openclaw"];

interface WorkerConsoleData {
  workerStatus: WorkerStatusPayload;
  workerFleet: WorkerFleetPayload;
  fleetHygiene: WorkerFleetHygienePayload;
  adapterReadiness: WorkerAdapterReadinessPayload;
  executionMode: OperatorExecutionModePayload;
}

function adapterColor(adapter: string) {
  if (adapter === "hermes") return "#2E86AB";
  if (adapter === "openclaw") return "#2A9D8F";
  return "var(--mis-muted)";
}

function commandLabel(command: string) {
  if (command.length <= 74) return command;
  return `${command.slice(0, 71)}...`;
}

export function WorkerConsole() {
  const { locale } = usePreferences();
  const [selectedAdapter, setSelectedAdapter] = useState<WorkerAdapterName>("mock");
  const [confirmRun, setConfirmRun] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [copiedCommand, setCopiedCommand] = useState<string | null>(null);
  const [lastDispatch, setLastDispatch] = useState<WorkerDispatchResult | null>(null);
  const [lastDaemonResult, setLastDaemonResult] = useState<WorkerDaemonResult | null>(null);
  const [lastHygieneResult, setLastHygieneResult] = useState<WorkerFleetHygienePayload | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const copy = pick(locale, {
    en: {
      title: "Worker Control Console",
      subtitle: "Operate real AgentOps workers from one focused surface: mode, readiness, dispatch, daemon control, recovery signals and ledger links.",
      backToTeam: "Full AI Employees board",
      refresh: "Refresh",
      loading: "Loading live worker state...",
      unavailable: "Worker backend unavailable",
      selectedAdapter: "Selected adapter",
      confirmLive: "Confirm live run",
      confirmHint: "Hermes/OpenClaw stay disabled until this is explicit.",
      executionMode: "Execution Mode",
      adapterReadiness: "Adapter readiness",
      workerFleet: "Worker fleet",
      fleetHygiene: "Fleet hygiene",
      hygieneSummary: "Plan and apply cleanup for stuck worker tasks plus never-seen or stale remote enrollments. Apply requires explicit confirmation and never executes live runtimes.",
      previewHygiene: "Preview hygiene",
      applyHygiene: "Apply confirmed cleanup",
      confirmCleanup: "Confirm cleanup",
      confirmCleanupHint: "Releases stale running tasks, blocks linked stale runs, and revokes stale enrollments/sessions.",
      actionsAvailable: "Actions available",
      staleNeverSeen: "Never seen",
      staleHeartbeat: "Heartbeat stale",
      releasedTasks: "Released tasks",
      revokedEnrollments: "Revoked enrollments",
      hygieneReadOnly: "read-only plan",
      hygieneApplied: "cleanup applied",
      remoteLanes: "Remote lanes",
      localLanes: "Local lanes",
      daemonControl: "Daemon control",
      dispatchOnce: "Dispatch once",
      startDaemon: "Start daemon",
      restartDaemon: "Restart daemon",
      stopDaemons: "Stop all daemons",
      runningDaemons: "Running daemons",
      pendingTasks: "Pending tasks",
      stuckTasks: "Stuck tasks",
      completedRuns: "Completed runs",
      remoteWorkers: "Remote workers",
      activeSessions: "Active sessions",
      activeJobs: "Active jobs",
      approvals: "Approvals",
      confirmWall: "Confirm wall",
      approvalWall: "Approval wall",
      selectedPath: "Selected path",
      recommendedAction: "Recommended action",
      trust: "Trust",
      liveReady: "Live ready",
      target: "Target",
      remediation: "Remediation",
      copyCommand: "Copy command",
      copied: "Copied",
      noCommand: "No command",
      readOnlyProof: "read-only proof",
      noServerShell: "no server shell",
      noLiveExecution: "no live execution",
      tokenOmitted: "token omitted",
      openTask: "Open task",
      openRun: "Open run",
      runId: "Run",
      planEvidence: "Plan evidence",
      daemon: "Daemon",
      pid: "PID",
      processed: "Processed",
      errors: "Errors",
      lastSleep: "Backoff",
      recentTasks: "Recent worker tasks",
      recentRuns: "Recent worker runs",
      liveBlocked: "Live adapter needs explicit confirmation.",
      noStuckTasks: "No stuck worker tasks.",
    },
    zh: {
      title: "Worker 控制台",
      subtitle: "一个聚焦的真实 Worker 操作面：运行模式、adapter 就绪、一次性派发、常驻进程控制、恢复信号和账本链接。",
      backToTeam: "完整 AI 员工面板",
      refresh: "刷新",
      loading: "正在加载真实 worker 状态...",
      unavailable: "Worker 后端不可用",
      selectedAdapter: "当前 adapter",
      confirmLive: "确认真实运行",
      confirmHint: "Hermes/OpenClaw 必须显式确认后才可执行。",
      executionMode: "执行模式",
      adapterReadiness: "Adapter 就绪",
      workerFleet: "Worker Fleet",
      fleetHygiene: "Fleet 清理",
      hygieneSummary: "规划并执行卡住 worker 任务、从未 heartbeat 或 heartbeat 过期远程 enrollment 的清理。应用清理必须显式确认，且不会执行真实 runtime。",
      previewHygiene: "预览清理计划",
      applyHygiene: "确认执行清理",
      confirmCleanup: "确认清理",
      confirmCleanupHint: "会释放 stale running 任务、阻断关联 stale run，并吊销 stale enrollment/session。",
      actionsAvailable: "可用动作",
      staleNeverSeen: "从未 heartbeat",
      staleHeartbeat: "Heartbeat 过期",
      releasedTasks: "已释放任务",
      revokedEnrollments: "已吊销 enrollment",
      hygieneReadOnly: "只读计划",
      hygieneApplied: "已执行清理",
      remoteLanes: "远程 lane",
      localLanes: "本地 lane",
      daemonControl: "常驻控制",
      dispatchOnce: "派发一次",
      startDaemon: "启动常驻",
      restartDaemon: "重启常驻",
      stopDaemons: "停止全部常驻",
      runningDaemons: "运行中的常驻",
      pendingTasks: "待处理任务",
      stuckTasks: "卡住任务",
      completedRuns: "已完成运行",
      remoteWorkers: "远程 Worker",
      activeSessions: "活跃 session",
      activeJobs: "活跃 Job",
      approvals: "审批",
      confirmWall: "确认墙",
      approvalWall: "审批墙",
      selectedPath: "执行路径",
      recommendedAction: "建议动作",
      trust: "信任状态",
      liveReady: "真实可跑",
      target: "目标资源",
      remediation: "修复/准备命令",
      copyCommand: "复制命令",
      copied: "已复制",
      noCommand: "暂无命令",
      readOnlyProof: "只读证明",
      noServerShell: "服务端不执行 shell",
      noLiveExecution: "未触发真实运行",
      tokenOmitted: "token 已省略",
      openTask: "打开任务",
      openRun: "打开运行",
      runId: "运行",
      planEvidence: "计划证据",
      daemon: "常驻",
      pid: "PID",
      processed: "已处理",
      errors: "错误",
      lastSleep: "退避",
      recentTasks: "最近 Worker 任务",
      recentRuns: "最近 Worker 运行",
      liveBlocked: "真实 adapter 需要显式确认。",
      noStuckTasks: "没有卡住的 worker 任务。",
    },
  });

  const { data, loading, error, refresh } = useLiveData<WorkerConsoleData>(async () => {
    const [workerStatus, workerFleet, fleetHygiene, adapterReadiness, executionMode] = await Promise.all([
      loadWorkerStatus(),
      loadWorkerFleet(),
      loadWorkerFleetHygiene({ limit: 8 }),
      loadWorkerAdapterReadiness(),
      loadOperatorExecutionMode(selectedAdapter, confirmRun, 8),
    ]);
    return { workerStatus, workerFleet, fleetHygiene, adapterReadiness, executionMode };
  }, [selectedAdapter, confirmRun]);

  const workerStatus = data?.workerStatus;
  const workerFleet = data?.workerFleet;
  const fleetHygiene = lastHygieneResult || data?.fleetHygiene;
  const adapterReadiness = data?.adapterReadiness;
  const executionMode = data?.executionMode;
  const selectedRoute = executionMode?.selected_route;
  const selectedReadiness = adapterReadiness?.adapters?.[selectedAdapter];
  const liveBlocked = selectedAdapter !== "mock" && !confirmRun;
  const primaryCommand = executionMode?.commands?.execution_mode
    || selectedRoute?.recommended_action
    || selectedReadiness?.remediation?.primary_next_action
    || "agentops operator execution-mode";

  const copyCommand = async (command?: string | null) => {
    const text = String(command || "");
    if (!text) return;
    await navigator.clipboard?.writeText(text);
    setCopiedCommand(text);
  };

  const runAction = async (action: string, handler: () => Promise<void>) => {
    setBusyAction(action);
    setActionMessage(null);
    try {
      await handler();
      await refresh();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyAction(null);
    }
  };

  const dispatchOnce = () => runAction(`dispatch:${selectedAdapter}`, async () => {
    const result = await dispatchLocalWorkerOnce({
      adapter: selectedAdapter,
      confirm_run: selectedAdapter !== "mock" && confirmRun,
      title: locale === "zh" ? `${selectedAdapter} worker 控制台任务` : `${selectedAdapter} worker console task`,
      description: locale === "zh"
        ? "从 Worker 控制台派发一次任务，验证 worker 能通过 Agent Gateway 执行并回写账本。"
        : "Dispatch one task from the Worker Console and verify Gateway writeback.",
      acceptance_criteria: "Worker writes run/tool/evaluation/audit/artifact evidence.",
    });
    setLastDispatch(result);
    setActionMessage(`${selectedAdapter}: ${result.ok ? "ok" : result.error || "failed"} · ${result.run_id || result.task_id}`);
  });

  const startDaemon = () => runAction(`start:${selectedAdapter}`, async () => {
    const result = await startLocalWorkerDaemon({
      adapter: selectedAdapter,
      confirm_run: selectedAdapter !== "mock" && confirmRun,
      poll_interval: 2,
      max_tasks: 0,
    });
    setLastDaemonResult(result);
    setActionMessage(`${selectedAdapter}: ${result.ok ? "ok" : result.error || "blocked"} · ${result.daemon?.pid || result.recommended_action || "daemon"}`);
  });

  const restartDaemon = () => runAction(`restart:${selectedAdapter}`, async () => {
    const result = await restartLocalWorkerDaemon({
      adapter: selectedAdapter,
      confirm_run: selectedAdapter !== "mock" && confirmRun,
      poll_interval: 2,
      max_tasks: 0,
    });
    setLastDaemonResult(result);
    setActionMessage(`${selectedAdapter}: ${result.ok ? "ok" : result.error || "blocked"} · ${result.daemon?.pid || result.recommended_action || "daemon"}`);
  });

  const stopAll = () => runAction("stop:all", async () => {
    const result = await stopLocalWorkerDaemon("all");
    setLastDaemonResult(result);
    setActionMessage(result.ok ? "stopped" : result.error || "stop failed");
  });

  const previewHygiene = () => runAction("hygiene:preview", async () => {
    const result = await loadWorkerFleetHygiene({ limit: 8 });
    setLastHygieneResult(result);
    setActionMessage(`${copy.fleetHygiene}: ${result.status} · ${copy.actionsAvailable}: ${result.summary.actions_available}`);
  });

  const applyHygiene = () => runAction("hygiene:apply", async () => {
    const result = await applyWorkerFleetHygiene({
      limit: 8,
      release_reason: "worker_console_confirmed_cleanup",
    });
    setLastHygieneResult(result);
    setConfirmCleanup(false);
    setActionMessage(`${copy.fleetHygiene}: ${result.status} · ${copy.releasedTasks}: ${result.summary.released_tasks ?? 0} · ${copy.revokedEnrollments}: ${result.summary.revoked_enrollments ?? 0}`);
  });

  const hygieneActionsAvailable = fleetHygiene?.summary.actions_available || 0;
  const remoteLaneCount = workerFleet?.summary.remote_worker_count ?? workerStatus?.remote_worker_count ?? 0;
  const localLaneCount = workerFleet?.summary.local_daemon_count ?? workerStatus?.worker_count ?? 0;

  const statCards = [
    { label: copy.runningDaemons, value: workerStatus?.running_workers ?? workerFleet?.summary.running_local_daemons ?? "—", status: (workerStatus?.running_workers || 0) > 0 ? "running" : "ready" },
    { label: copy.pendingTasks, value: workerStatus?.pending_worker_tasks ?? "—", status: (workerStatus?.pending_worker_tasks || 0) > 0 ? "planned" : "pass" },
    { label: copy.stuckTasks, value: workerStatus?.stuck_worker_tasks ?? "—", status: (workerStatus?.stuck_worker_tasks || 0) > 0 ? "attention" : "pass" },
    { label: copy.completedRuns, value: workerStatus?.recent_completed_runs ?? "—", status: "completed" },
    { label: copy.remoteWorkers, value: workerStatus?.remote_worker_count ?? workerFleet?.summary.remote_worker_count ?? "—", status: (workerStatus?.stale_remote_enrollments || 0) > 0 ? "attention" : "ready" },
    { label: copy.activeSessions, value: workerStatus?.active_remote_sessions ?? "—", status: (workerStatus?.active_remote_sessions || 0) > 0 ? "ready" : "planned" },
    { label: copy.activeJobs, value: executionMode?.summary.active_workflow_jobs ?? workerStatus?.stuck_workflow_jobs ?? "—", status: (executionMode?.summary.active_workflow_jobs || 0) > 0 ? "running" : "pass" },
    { label: copy.approvals, value: executionMode?.summary.pending_approvals ?? "—", status: (executionMode?.summary.pending_approvals || 0) > 0 ? "attention" : "pass" },
  ];

  return (
    <div className="space-y-4 max-w-none">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <TerminalSquare size={18} style={{ color: "var(--mis-cyan)" }} />
            <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
            <StatusBadge status={workerStatus?.status || "unknown"} />
            <StatusBadge status={executionMode?.status || "unknown"} label={executionMode?.mode || executionMode?.status || "mode"} />
          </div>
          <p className="text-xs mt-1 max-w-4xl" style={{ color: "var(--mis-dim)" }}>{copy.subtitle}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/workspace/agents" className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded" style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}>
            <Bot size={13} />
            {copy.backToTeam}
          </Link>
          <button onClick={refresh} className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded" style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}>
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            {copy.refresh}
          </button>
        </div>
      </div>

      {loading && <p className="text-xs" style={{ color: "var(--mis-muted)" }}>{copy.loading}</p>}
      {error && <p className="text-xs" style={{ color: "#F87171" }}>{copy.unavailable}: {error}</p>}

      <section className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
        <div className="flex flex-col xl:flex-row xl:items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Activity size={14} style={{ color: "var(--mis-success)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.executionMode}</h2>
              <StatusBadge status={selectedRoute?.readiness || selectedReadiness?.readiness || "unknown"} />
              <StatusBadge status={executionMode?.summary.confirm_run_wall || (liveBlocked ? "attention" : "pass")} label={copy.confirmWall} />
              <StatusBadge status={executionMode?.summary.prepared_action_wall || "planned"} label={copy.approvalWall} />
            </div>
            <div className="text-[11px] mt-1 truncate" style={{ color: "var(--mis-dim)" }}>
              {copy.selectedPath}: {executionMode?.selected_path || selectedAdapter} · {copy.recommendedAction}: {primaryCommand}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.selectedAdapter}</label>
            <select
              value={selectedAdapter}
              onChange={(event) => setSelectedAdapter(event.target.value as WorkerAdapterName)}
              className="rounded px-2 py-1 text-xs"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            >
              {WORKER_ADAPTERS.map((adapter) => <option key={adapter} value={adapter}>{adapter}</option>)}
            </select>
            <label className="inline-flex items-center gap-2 text-[11px] rounded px-2 py-1" style={{ color: confirmRun ? "var(--mis-success)" : "var(--mis-warning)", background: confirmRun ? "rgba(45,212,191,0.10)" : "rgba(251,191,36,0.10)", border: confirmRun ? "1px solid rgba(45,212,191,0.20)" : "1px solid rgba(251,191,36,0.24)" }}>
              <input type="checkbox" checked={confirmRun} onChange={(event) => setConfirmRun(event.target.checked)} />
              {copy.confirmLive}
            </label>
            <button onClick={() => void copyCommand(primaryCommand)} className="inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-[11px]" style={{ background: "var(--mis-surface2)", color: "var(--mis-cyan)", border: "1px solid var(--mis-border)" }}>
              <Copy size={11} />
              {copiedCommand === primaryCommand ? copy.copied : copy.copyCommand}
            </button>
          </div>
        </div>
        {liveBlocked && (
          <div className="mt-3 flex items-center gap-2 rounded px-3 py-2 text-[11px]" style={{ background: "rgba(251,191,36,0.10)", border: "1px solid rgba(251,191,36,0.22)", color: "var(--mis-warning)" }}>
            <AlertTriangle size={13} />
            {copy.liveBlocked} {copy.confirmHint}
          </div>
        )}
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2 mt-4">
          {statCards.map((item) => (
            <div key={item.label} className="rounded px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
              <div className="flex items-center justify-between gap-2 mt-1">
                <div className="text-sm font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.value}</div>
                <StatusBadge status={item.status} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_0.85fr] gap-4">
        <section className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Power size={14} style={{ color: "var(--mis-cyan)" }} />
                <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.daemonControl}</h2>
              </div>
              <p className="text-[11px] mt-1" style={{ color: "var(--mis-dim)" }}>{copy.confirmHint}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={dispatchOnce} disabled={Boolean(busyAction) || liveBlocked} className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-[11px] disabled:opacity-45" style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}>
                {busyAction === `dispatch:${selectedAdapter}` ? <RefreshCw size={12} /> : <Play size={12} />}
                {copy.dispatchOnce}
              </button>
              <button onClick={startDaemon} disabled={Boolean(busyAction) || liveBlocked} className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-[11px] disabled:opacity-45" style={{ background: "rgba(45,212,191,0.12)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.22)" }}>
                {busyAction === `start:${selectedAdapter}` ? <RefreshCw size={12} /> : <Power size={12} />}
                {copy.startDaemon}
              </button>
              <button onClick={restartDaemon} disabled={Boolean(busyAction) || liveBlocked} className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-[11px] disabled:opacity-45" style={{ background: "rgba(122,90,248,0.10)", color: "#A78BFA", border: "1px solid rgba(122,90,248,0.2)" }}>
                {busyAction === `restart:${selectedAdapter}` ? <RefreshCw size={12} /> : <RotateCw size={12} />}
                {copy.restartDaemon}
              </button>
              <button onClick={stopAll} disabled={Boolean(busyAction)} className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-[11px] disabled:opacity-45" style={{ background: "rgba(248,113,113,0.10)", color: "#F87171", border: "1px solid rgba(248,113,113,0.22)" }}>
                {busyAction === "stop:all" ? <RefreshCw size={12} /> : <Square size={12} />}
                {copy.stopDaemons}
              </button>
            </div>
          </div>

          {actionMessage && (
            <div className="mt-3 text-[11px] rounded px-3 py-2" style={{ color: actionMessage.includes("failed") || actionMessage.includes("blocked") ? "#F87171" : "var(--mis-success)", background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              {actionMessage}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
            {(workerStatus?.daemons || []).map((daemon) => (
              <div key={daemon.adapter} className="rounded px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[11px] font-semibold" style={{ color: adapterColor(daemon.adapter) }}>{daemon.adapter}</div>
                  <StatusBadge status={daemon.running ? "running" : daemon.status} />
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{copy.pid}: <span style={{ color: "var(--mis-text)" }}>{daemon.pid || "—"}</span></div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{copy.processed}: <span style={{ color: "var(--mis-text)" }}>{daemon.processed ?? 0}</span></div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{copy.errors}: <span style={{ color: daemon.total_errors ? "#F87171" : "var(--mis-text)" }}>{daemon.total_errors ?? 0}</span></div>
                  <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{copy.lastSleep}: <span style={{ color: "var(--mis-text)" }}>{daemon.last_sleep_reason || "—"}</span></div>
                </div>
                <div className="text-[10px] mt-2 truncate" style={{ color: "var(--mis-dim)" }}>{daemon.agent_id || daemon.worker_status || "—"}</div>
              </div>
            ))}
          </div>

          {(lastDispatch || lastDaemonResult) && (
            <div className="rounded p-3 mt-4" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="flex flex-wrap items-center gap-2">
                <ShieldCheck size={13} style={{ color: "var(--mis-cyan)" }} />
                <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{lastDispatch ? copy.dispatchOnce : copy.daemonControl}</div>
                {lastDispatch && <StatusBadge status={lastDispatch.ok ? "completed" : "failed"} />}
                {lastDispatch?.plan_evidence_status && <StatusBadge status={lastDispatch.plan_evidence_pass ? "pass" : "attention"} label={copy.planEvidence} />}
                {lastDaemonResult && <StatusBadge status={lastDaemonResult.ok ? "ready" : "blocked"} />}
              </div>
              {lastDispatch && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {lastDispatch.task_id && <Link to={`/admin/tasks/${lastDispatch.task_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>{copy.openTask}</Link>}
                  {lastDispatch.run_id && <Link to={`/admin/runs/${lastDispatch.run_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}>{copy.openRun}</Link>}
                  <span className="text-[10px] px-2 py-1 rounded" style={{ background: "var(--mis-bg)", color: "var(--mis-muted)", border: "1px solid var(--mis-border)" }}>{copy.runId}: {lastDispatch.run_id || "—"}</span>
                </div>
              )}
              {lastDaemonResult?.recommended_action && (
                <button onClick={() => void copyCommand(lastDaemonResult.recommended_action)} className="mt-3 inline-flex items-center gap-1.5 rounded px-2 py-1 text-[10px]" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)", color: "var(--mis-cyan)" }}>
                  <Copy size={10} />
                  {copiedCommand === lastDaemonResult.recommended_action ? copy.copied : commandLabel(lastDaemonResult.recommended_action)}
                </button>
              )}
            </div>
          )}
        </section>

        <section className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 size={14} style={{ color: "var(--mis-success)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.adapterReadiness}</h2>
            </div>
            <StatusBadge status={adapterReadiness?.status || "unknown"} />
          </div>
          <div className="space-y-3 mt-3">
            {WORKER_ADAPTERS.map((adapter) => {
              const item = adapterReadiness?.adapters?.[adapter];
              const commands = item?.remediation?.commands || [];
              return (
                <div key={adapter} className="rounded px-3 py-2" style={{ background: adapter === selectedAdapter ? "rgba(34,211,238,0.07)" : "var(--mis-surface2)", border: adapter === selectedAdapter ? "1px solid rgba(34,211,238,0.22)" : "1px solid var(--mis-border)" }}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-[11px] font-semibold" style={{ color: adapterColor(adapter) }}>{adapter}</div>
                    <div className="flex items-center gap-1.5">
                      <StatusBadge status={item?.readiness || "unknown"} />
                      <StatusBadge status={item?.trust_status || "unknown"} label={`${copy.trust}: ${item?.trust_status || "—"}`} />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
                    <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{copy.liveReady}: <span style={{ color: item?.ok ? "var(--mis-success)" : "var(--mis-dim)" }}>{item?.ok ? "yes" : "no"}</span></div>
                    <div className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{copy.target}: <span style={{ color: "var(--mis-text)" }}>{item?.target_resource || "—"}</span></div>
                  </div>
                  <div className="text-[10px] mt-2 truncate" style={{ color: "var(--mis-cyan)" }}>{copy.recommendedAction}: {item?.remediation?.primary_next_action || item?.recommended_action || "agentops worker readiness"}</div>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {(commands.length ? commands.slice(0, 4) : [{ command: item?.remediation?.primary_next_action || item?.recommended_action || "" }]).map((command, index) => (
                      <button key={`${adapter}:${index}:${command.command}`} onClick={() => void copyCommand(command.command)} disabled={!command.command} className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] disabled:opacity-40" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)", color: command.confirm_required ? "var(--mis-warning)" : "var(--mis-cyan)" }}>
                        <Copy size={8} />
                        {command.command ? (copiedCommand === command.command ? copy.copied : command.phase || copy.copyCommand) : copy.noCommand}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="grid grid-cols-2 gap-2 mt-4">
            <StatusBadge status={executionMode?.safety.read_only ? "pass" : "attention"} label={copy.readOnlyProof} />
            <StatusBadge status={executionMode?.safety.server_executes_shell === false ? "pass" : "attention"} label={copy.noServerShell} />
            <StatusBadge status={executionMode?.safety.live_execution_performed ? "attention" : "pass"} label={copy.noLiveExecution} />
            <StatusBadge status={executionMode?.safety.token_omitted ? "pass" : "attention"} label={copy.tokenOmitted} />
          </div>
        </section>
      </div>

      <section
        data-testid="worker-fleet-hygiene-panel"
        className="rounded-lg p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <AlertTriangle size={14} style={{ color: hygieneActionsAvailable > 0 ? "#FBBF24" : "var(--mis-success)" }} />
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.fleetHygiene}</h2>
              <StatusBadge status={fleetHygiene?.status || "unknown"} />
              <StatusBadge status={fleetHygiene?.safety.read_only ? "pass" : "attention"} label={copy.hygieneReadOnly} />
              <StatusBadge status={fleetHygiene?.applied ? "completed" : "planned"} label={fleetHygiene?.applied ? copy.hygieneApplied : copy.actionsAvailable} />
            </div>
            <p className="mt-1 max-w-4xl text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>{copy.hygieneSummary}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex items-center gap-2 rounded px-2 py-1 text-[11px]" style={{ background: confirmCleanup ? "rgba(251,191,36,0.12)" : "var(--mis-surface2)", color: confirmCleanup ? "#FBBF24" : "var(--mis-muted)", border: confirmCleanup ? "1px solid rgba(251,191,36,0.24)" : "1px solid var(--mis-border)" }}>
              <input type="checkbox" checked={confirmCleanup} onChange={(event) => setConfirmCleanup(event.target.checked)} />
              {copy.confirmCleanup}
            </label>
            <button onClick={previewHygiene} disabled={Boolean(busyAction)} className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-[11px] disabled:opacity-45" style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}>
              {busyAction === "hygiene:preview" ? <RefreshCw size={12} /> : <Activity size={12} />}
              {copy.previewHygiene}
            </button>
            <button onClick={applyHygiene} disabled={Boolean(busyAction) || !confirmCleanup || hygieneActionsAvailable === 0} className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-[11px] disabled:opacity-45" style={{ background: "rgba(251,191,36,0.12)", color: "#FBBF24", border: "1px solid rgba(251,191,36,0.24)" }}>
              {busyAction === "hygiene:apply" ? <RefreshCw size={12} /> : <ShieldCheck size={12} />}
              {copy.applyHygiene}
            </button>
          </div>
        </div>

        <div className="mt-3 rounded px-3 py-2 text-[11px]" style={{ background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.18)", color: "var(--mis-dim)" }}>
          {copy.confirmCleanupHint} {copy.noLiveExecution}: {fleetHygiene?.live_execution_performed ? "false" : "true"} · {copy.tokenOmitted}: {fleetHygiene?.token_omitted ? "true" : "unknown"}
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2">
          {[
            { label: copy.actionsAvailable, value: hygieneActionsAvailable, status: hygieneActionsAvailable > 0 ? "attention" : "pass" },
            { label: copy.stuckTasks, value: fleetHygiene?.summary.stuck_tasks ?? 0, status: (fleetHygiene?.summary.stuck_tasks || 0) > 0 ? "attention" : "pass" },
            { label: copy.staleNeverSeen, value: fleetHygiene?.summary.stale_never_seen_enrollments ?? 0, status: (fleetHygiene?.summary.stale_never_seen_enrollments || 0) > 0 ? "attention" : "pass" },
            { label: copy.staleHeartbeat, value: fleetHygiene?.summary.stale_heartbeat_enrollments ?? 0, status: (fleetHygiene?.summary.stale_heartbeat_enrollments || 0) > 0 ? "attention" : "pass" },
            { label: copy.releasedTasks, value: fleetHygiene?.summary.released_tasks ?? 0, status: fleetHygiene?.applied ? "completed" : "planned" },
            { label: copy.revokedEnrollments, value: fleetHygiene?.summary.revoked_enrollments ?? 0, status: fleetHygiene?.applied ? "completed" : "planned" },
            { label: copy.remoteLanes, value: remoteLaneCount, status: remoteLaneCount > 0 ? "ready" : "planned" },
            { label: copy.localLanes, value: localLaneCount, status: localLaneCount > 0 ? "ready" : "planned" },
          ].map((item) => (
            <div key={item.label} className="rounded px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
              <div className="flex items-center justify-between gap-2 mt-1">
                <div className="text-sm font-semibold truncate" style={{ color: "var(--mis-text)" }}>{item.value}</div>
                <StatusBadge status={item.status} />
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-3">
          <div className="rounded p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.recommendedAction}</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(fleetHygiene?.recommended_actions || ["agentops worker hygiene"]).slice(0, 4).map((command) => (
                <button key={command} onClick={() => void copyCommand(command)} className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px]" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)", color: command.includes("--apply") ? "#FBBF24" : "var(--mis-cyan)" }}>
                  <Copy size={8} />
                  {copiedCommand === command ? copy.copied : commandLabel(command)}
                </button>
              ))}
            </div>
          </div>
          <div className="rounded p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.staleNeverSeen}</div>
            <div className="mt-2 space-y-1">
              {(fleetHygiene?.stale_never_seen_enrollments || []).slice(0, 4).map((enrollment) => (
                <div key={enrollment.token_ref || enrollment.agent_id} className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>
                  {enrollment.agent_id} · {enrollment.token_ref || "token_ref"} · {enrollment.heartbeat_state}
                </div>
              ))}
              {(fleetHygiene?.stale_never_seen_enrollments || []).length === 0 && <div className="text-[10px]" style={{ color: "var(--mis-dim)" }}>—</div>}
            </div>
          </div>
          <div className="rounded p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
            <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.staleHeartbeat}</div>
            <div className="mt-2 space-y-1">
              {(fleetHygiene?.stale_heartbeat_enrollments || []).slice(0, 4).map((enrollment) => (
                <div key={enrollment.token_ref || enrollment.agent_id} className="text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>
                  {enrollment.agent_id} · {enrollment.token_ref || "token_ref"} · {enrollment.heartbeat_state}
                </div>
              ))}
              {(fleetHygiene?.stale_heartbeat_enrollments || []).length === 0 && <div className="text-[10px]" style={{ color: "var(--mis-dim)" }}>—</div>}
            </div>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <section className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.recentTasks}</h2>
            <StatusBadge status={(workerStatus?.stuck_tasks?.length || 0) > 0 ? "attention" : "pass"} label={(workerStatus?.stuck_tasks?.length || 0) > 0 ? `${copy.stuckTasks}: ${workerStatus?.stuck_tasks?.length}` : copy.noStuckTasks} />
          </div>
          <div className="space-y-2 mt-3">
            {(workerStatus?.recent_tasks || []).slice(0, 5).map((task) => (
              <Link key={task.task_id} to={`/admin/tasks/${task.task_id}`} className="block rounded px-3 py-2 hover:opacity-85" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{task.title}</div>
                  <StatusBadge status={task.status} />
                </div>
                <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>{task.task_id} · {task.owner_agent_id || "—"}</div>
              </Link>
            ))}
          </div>
        </section>

        <section className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.recentRuns}</h2>
            <StatusBadge status={workerFleet?.status || "unknown"} label={copy.workerFleet} />
          </div>
          <div className="space-y-2 mt-3">
            {(workerStatus?.recent_runs || []).slice(0, 5).map((run) => (
              <Link key={run.run_id} to={`/admin/runs/${run.run_id}`} className="block rounded px-3 py-2 hover:opacity-85" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[11px] font-semibold truncate" style={{ color: "var(--mis-text)" }}>{run.run_id}</div>
                  <StatusBadge status={run.status} />
                </div>
                <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-muted)" }}>{run.agent_id || "—"} · {run.runtime_type || "worker"}</div>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
