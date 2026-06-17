import { Link } from "react-router";
import { useState } from "react";
import { Bot, Play, RefreshCw, Activity, Power, Square } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { dispatchLocalWorkerOnce, loadAgents, loadDashboard, loadWorkerStatus, startLocalWorkerDaemon, stopLocalWorkerDaemon, useLiveData } from "../../data/liveApi";
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

export function AIEmployees() {
  const { locale } = usePreferences();
  const [dispatching, setDispatching] = useState<string | null>(null);
  const [dispatchResult, setDispatchResult] = useState<string | null>(null);
  const { data, loading, error, refresh } = useLiveData(async () => {
    const [metrics, workerStatus] = await Promise.all([loadDashboard(), loadWorkerStatus()]);
    const agents = await loadAgents(metrics);
    return { agents, workerStatus };
  }, []);
  const agents = data?.agents || [];
  const workerStatus = data?.workerStatus;
  const activeAgents = agents.filter(a => a.status === "running").length;
  const copy = pick(locale, {
    en: {
      title: "AI Employees",
      summary: `${agents.length} registered agents · ${activeAgents} active · live backend`,
      loading: "Loading live agents...",
      backendUnavailable: "Live backend unavailable",
      refresh: "Refresh live agents",
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
    },
    zh: {
      title: "AI 员工",
      summary: `${agents.length} 个已注册代理 · ${activeAgents} 个运行中 · 连接本地后端`,
      loading: "正在加载实时代理...",
      backendUnavailable: "本地后端不可用",
      refresh: "刷新实时代理",
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
            { label: copy.recentRun, value: workerStatus?.recent_runs?.[0]?.run_id || "—" },
          ].map((item) => (
            <div key={item.label} className="rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
              <div className="text-xs font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{item.value}</div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-3 gap-3 mt-3">
          {(workerStatus?.daemons || []).map((daemon) => (
            <div key={daemon.adapter} className="rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="flex items-center justify-between gap-2">
                <div className="text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>{daemon.adapter}</div>
                <StatusBadge status={daemon.running ? "running" : daemon.status} />
              </div>
              <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-dim)" }}>
                {copy.daemonStatus}: {daemon.status}
              </div>
              <div className="text-[10px] mt-0.5 truncate" style={{ color: "var(--mis-dim)" }}>
                {copy.pid}: {daemon.pid || "—"} · {daemon.agent_id || "—"}
              </div>
            </div>
          ))}
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
