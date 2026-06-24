import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { ArrowRight, ExternalLink, Map, MonitorCog, ShieldCheck, Sparkles } from "lucide-react";
import { OperationsBar } from "../pixel/OperationsBar";
import { CustomerDispatchPanel } from "../pixel/CustomerDispatchPanel";
import { PixelOperatingMap } from "../pixel/PixelOperatingMap";
import {
  derivePixelAgents,
  derivePixelMetrics,
  deriveTaskCards,
  PIXEL_ZONES,
  type PixelMetrics,
  zoneDisplay,
} from "../pixel/pixelModel";
import {
  loadAgents,
  loadApprovals,
  loadAudit,
  loadDashboard,
  loadMemories,
  loadRuns,
  loadTasks,
  type DashboardMetrics,
} from "../../data/liveApi";
import { pick, usePreferences } from "../../context/PreferencesContext";
import {
  agents as mockAgents,
  approvals as mockApprovals,
  auditLogs as mockAudit,
  memories as mockMemories,
  runtimeConnectors as mockRuntimeConnectors,
  runs as mockRuns,
  tasks as mockTasks,
  type Agent,
  type Approval,
  type AuditLog,
  type Memory,
  type Run,
  type Task,
} from "../../data/mockData";

const configuredStarOfficeUrl = import.meta.env.VITE_STAR_OFFICE_URL as string | undefined;

interface PixelOfficeSnapshot {
  metrics: DashboardMetrics;
  agents: Agent[];
  tasks: Task[];
  approvals: Approval[];
  runs: Run[];
  memories: Memory[];
  audit: AuditLog[];
}

function buildFallbackMetrics(): DashboardMetrics {
  const completedTasks = mockTasks.filter((task) => task.status === "completed").length;
  const failedRuns = mockRuns.filter((run) => ["failed", "error", "blocked", "timeout"].includes(run.status)).length;
  const pendingApprovals = mockApprovals.filter((approval) => approval.decision === "pending").length;
  const totalCost = mockRuns.reduce((sum, run) => sum + (Number.isFinite(run.cost_usd) ? run.cost_usd : 0), 0);
  const statusCounts = mockTasks.reduce<Record<string, number>>((acc, task) => {
    acc[task.status] = (acc[task.status] || 0) + 1;
    return acc;
  }, {});

  return {
    agents_total: mockAgents.length,
    agents_running: mockAgents.filter((agent) => agent.status === "running").length,
    tasks_completed_total: completedTasks,
    total_cost_usd: totalCost,
    avg_task_cost_usd: mockTasks.length ? totalCost / mockTasks.length : 0,
    failure_rate: mockRuns.length ? failedRuns / mockRuns.length : 0,
    pending_approvals: pendingApprovals,
    stale_or_due_memories: mockMemories.filter((memory) => ["candidate", "stale"].includes(memory.review_status)).length,
    task_status_distribution: Object.entries(statusCounts).map(([status, count]) => ({ status, count })),
    top_cost_agents: mockAgents.slice(0, 3).map((agent) => ({ agent_id: agent.agent_id, name: agent.name, cost_usd: agent.budget_used_usd })),
    top_failing_agents: mockAgents.slice(0, 3).map((agent) => ({ agent_id: agent.agent_id, name: agent.name, failures: agent.failure_count })),
    runtime_health: mockRuntimeConnectors.map((connector) => ({
      provider: connector.provider,
      status: connector.status,
      mode: connector.mode,
      last_checked: connector.last_checked,
    })),
    openclaw_import: {
      agents: mockAgents.filter((agent) => agent.runtime_type === "openclaw").length,
      cron_tasks: mockTasks.length,
      enabled_cron_tasks: mockTasks.filter((task) => task.status !== "completed").length,
      cron_runs: mockRuns.length,
      failed_runs: failedRuns,
      failed_quality_gates: failedRuns,
    },
    agent_performance_summary: mockAgents.map((agent) => ({
      agent_id: agent.agent_id,
      name: agent.name,
      runtime_type: agent.runtime_type,
      total_runs: agent.run_count,
      success_rate: agent.success_rate,
      avg_duration_ms: 0,
      total_cost_usd: agent.budget_used_usd,
      failures: agent.failure_count,
      approval_required_count: agent.approval_count,
    })),
    recent_runs: mockRuns.slice(0, 5),
  };
}

const fallbackSnapshot: PixelOfficeSnapshot = {
  metrics: buildFallbackMetrics(),
  agents: mockAgents,
  tasks: mockTasks,
  approvals: mockApprovals,
  runs: mockRuns,
  memories: mockMemories,
  audit: mockAudit,
};

function readSettled<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

export function PixelOffice() {
  const navigate = useNavigate();
  const { locale } = usePreferences();
  const [snapshot, setSnapshot] = useState<PixelOfficeSnapshot>(fallbackSnapshot);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = pick(locale, {
    en: {
      title: "Agent-MIS Pixel Operating Floor",
      liveState: "Live MIS state",
      demoSafe: "Demo-safe",
      legacyAvailable: "Legacy Star Office available",
      legacyMissing: "Legacy Star Office not configured",
      legacyLink: "Legacy Star Office",
      controlTower: "Control Tower",
      subtitle: "A clickable operations floor for AI digital employees. Zones visualize AgentOps MIS state and jump into the formal ledgers for agents, tasks, runs, approvals, tools, memory, evaluations, audit and external bases.",
      routingTitle: "Zone routing contract",
      routingBody: "Every room is a route into an existing MIS page. The floor is an orientation layer, not a duplicate ledger.",
      stateTitle: "State source",
      stateBody: "Agent placement comes from AgentOps MIS agents, tasks, runs, approvals, memories and audit events. Demo sprites appear only when live data is sparse.",
      agentsPlaced: "Agents placed",
      taskCards: "Task cards",
      boundaryTitle: "Asset and authority boundary",
      boundaryBody: "This v1.3 map uses original React/CSS geometry only. No Star-Office, paid tileset or third-party sprite assets are copied into the product UI.",
      authority: "AgentOps MIS remains the authority system for state, permissions, evaluations and audit.",
      zones: "Mapped rooms",
    },
    zh: {
      title: "Agent-MIS 像素运营大厅",
      liveState: "实时 MIS 状态",
      demoSafe: "演示安全",
      legacyAvailable: "可打开旧 Star Office",
      legacyMissing: "未配置旧 Star Office",
      legacyLink: "旧 Star Office",
      controlTower: "控制塔",
      subtitle: "面向 AI 数字员工的可点击运营大厅。各区域把 AgentOps MIS 状态可视化，并跳转到代理、任务、运行、审批、工具、记忆、评估、审计和外部库等正式账本。",
      routingTitle: "区域路由契约",
      routingBody: "每个房间都对应一个已有 MIS 页面。运营大厅负责定位和导航，不重复替代正式账本。",
      stateTitle: "状态来源",
      stateBody: "代理位置来自 AgentOps MIS 的正式账本：代理、任务、运行、审批、记忆和审计事件。只有实时数据不足时才使用演示占位角色。",
      agentsPlaced: "已放置代理",
      taskCards: "任务卡片",
      boundaryTitle: "资产与权威边界",
      boundaryBody: "v1.3 地图只使用原创 React/CSS 几何结构，不把 Star-Office、付费 tileset 或第三方 sprite 资产复制进产品 UI。",
      authority: "AgentOps MIS 仍然是状态、权限、评估和审计的权威系统。",
      zones: "已映射房间",
    },
  });

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const metrics = await loadDashboard();
      const [agentsResult, tasksResult, approvalsResult, runsResult, memoriesResult, auditResult] = await Promise.allSettled([
        loadAgents(metrics),
        loadTasks(),
        loadApprovals(),
        loadRuns(),
        loadMemories(),
        loadAudit(),
      ]);

      setSnapshot({
        metrics,
        agents: readSettled(agentsResult, fallbackSnapshot.agents),
        tasks: readSettled(tasksResult, fallbackSnapshot.tasks),
        approvals: readSettled(approvalsResult, fallbackSnapshot.approvals),
        runs: readSettled(runsResult, fallbackSnapshot.runs),
        memories: readSettled(memoriesResult, fallbackSnapshot.memories),
        audit: readSettled(auditResult, fallbackSnapshot.audit),
      });
    } catch (err) {
      setSnapshot(fallbackSnapshot);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const pixelMetrics: PixelMetrics = useMemo(
    () =>
      derivePixelMetrics({
        metrics: snapshot.metrics,
        tasks: snapshot.tasks,
        approvals: snapshot.approvals,
        runs: snapshot.runs,
        memories: snapshot.memories,
        audit: snapshot.audit,
      }),
    [snapshot],
  );

  const pixelAgents = useMemo(
    () =>
      derivePixelAgents({
        agents: snapshot.agents,
        tasks: snapshot.tasks,
        approvals: snapshot.approvals,
        runs: snapshot.runs,
        memories: snapshot.memories,
      }),
    [snapshot],
  );

  const taskCards = useMemo(() => deriveTaskCards(snapshot.tasks), [snapshot.tasks]);

  const openRoute = (route: string) => {
    if (route.startsWith("http")) {
      window.open(route, "_blank", "noreferrer");
      return;
    }
    navigate(route);
  };

  return (
    <div className="space-y-4 max-w-none">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>
              {copy.title}
            </h1>
            <span
              className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-[10px] uppercase tracking-wide"
              style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
            >
              <Sparkles size={11} />
              {copy.liveState}
            </span>
            <span
              className="rounded px-2 py-1 text-[10px] uppercase tracking-wide"
              style={{ background: "rgba(168,85,247,0.12)", color: "var(--mis-purple)", border: "1px solid rgba(168,85,247,0.24)" }}
            >
              {copy.demoSafe}
            </span>
            {configuredStarOfficeUrl && (
              <span
                className="rounded px-2 py-1 text-[10px] uppercase tracking-wide"
                style={{ background: "rgba(42,157,143,0.12)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.24)" }}
              >
                {copy.legacyAvailable}
              </span>
            )}
          </div>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {copy.subtitle}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {configuredStarOfficeUrl ? (
            <a
              href={configuredStarOfficeUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}
            >
              <ExternalLink size={13} />
              {copy.legacyLink}
            </a>
          ) : (
            <span className="rounded px-3 py-1.5 text-[11px]" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)", border: "1px solid var(--mis-border)" }}>
              {copy.legacyMissing}
            </span>
          )}
          <Link
            to="/admin"
            className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs"
            style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
          >
            {copy.controlTower}
            <ArrowRight size={13} />
          </Link>
        </div>
      </div>

      <CustomerDispatchPanel agents={snapshot.agents} locale={locale} onRefresh={refresh} />

      <OperationsBar metrics={pixelMetrics} loading={loading} error={error} onRefresh={refresh} locale={locale} />

      <PixelOperatingMap agents={pixelAgents} taskCards={taskCards} metrics={pixelMetrics} onOpenRoute={openRoute} locale={locale} />

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--mis-text)" }}>
            <Map size={15} style={{ color: "var(--mis-cyan)" }} />
            {copy.routingTitle}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {copy.routingBody}
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {PIXEL_ZONES.slice(0, 8).map((zone) => (
              <button
                key={zone.id}
                type="button"
                onClick={() => openRoute(zone.route)}
                className="rounded px-2 py-1 text-[10px] hover:opacity-80"
                style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)", border: "1px solid rgba(148,163,184,0.14)" }}
              >
                {zoneDisplay(zone, locale).label}
              </button>
            ))}
          </div>
        </div>
        <div className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--mis-text)" }}>
            <MonitorCog size={15} style={{ color: "var(--mis-purple)" }} />
            {copy.stateTitle}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {copy.stateBody}
          </p>
          <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
            <div className="rounded p-2" style={{ background: "var(--mis-surface2)" }}>
              <div style={{ color: "var(--mis-muted)" }}>{copy.agentsPlaced}</div>
              <div className="text-base font-semibold" style={{ color: "var(--mis-text)" }}>{pixelAgents.length}</div>
            </div>
            <div className="rounded p-2" style={{ background: "var(--mis-surface2)" }}>
              <div style={{ color: "var(--mis-muted)" }}>{copy.taskCards}</div>
              <div className="text-base font-semibold" style={{ color: "var(--mis-text)" }}>{taskCards.length}</div>
            </div>
            <div className="rounded p-2" style={{ background: "var(--mis-surface2)" }}>
              <div style={{ color: "var(--mis-muted)" }}>{copy.zones}</div>
              <div className="text-base font-semibold" style={{ color: "var(--mis-text)" }}>{PIXEL_ZONES.length}</div>
            </div>
          </div>
        </div>
        <div className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--mis-text)" }}>
            <ShieldCheck size={15} style={{ color: "var(--mis-success)" }} />
            {copy.boundaryTitle}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {copy.boundaryBody}
          </p>
          <div className="mt-3 rounded p-2 text-[10px]" style={{ background: "rgba(42,157,143,0.10)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.22)" }}>
            {copy.authority}
          </div>
        </div>
      </section>
    </div>
  );
}
