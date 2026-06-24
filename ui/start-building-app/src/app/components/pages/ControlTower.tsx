import {
  Bot, ListChecks, Play, ShieldAlert, Activity, AlertTriangle,
  DollarSign, Brain, Download, ClipboardList,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { MetricCard } from "../shared/MetricCard";
import { StatusBadge } from "../shared/StatusBadge";
import { loadAgents, loadDashboard, useLiveData } from "../../data/liveApi";
import { pick, usePreferences } from "../../context/PreferencesContext";

export function ControlTower() {
  const { locale } = usePreferences();
  const { data, loading, error, refresh } = useLiveData(async () => {
    const metrics = await loadDashboard();
    const agents = await loadAgents(metrics);
    return { metrics, agents };
  }, []);

  const metrics = data?.metrics;
  const agents = data?.agents || [];
  const taskStatus = metrics?.task_status_distribution || [];
  const runVolume = (metrics?.recent_runs || []).slice(0, 12).reverse().map((run, idx) => ({
    date: run.created_at ? new Date(run.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : `R${idx + 1}`,
    runs: idx + 1,
  }));
  const costByAgent = (metrics?.top_cost_agents || []).map(a => ({ agent: a.name.slice(0, 12), cost: Number(a.cost_usd || 0) }));
  const runtimeHealth = metrics?.runtime_health || [];
  const runtimeStatus = (provider: string) => {
    const row = runtimeHealth.find(item => String((item as any).provider || "").toLowerCase() === provider);
    return String((row as any)?.status || "unknown");
  };
  const totalTasks = taskStatus.reduce((sum, item) => sum + Number(item.count || 0), 0);
  const totalRuns = metrics?.recent_runs ? Number(metrics.openclaw_import?.cron_runs || 0) + Number(metrics.recent_runs.length || 0) : 0;
  const copy = pick(locale, {
    en: {
      title: "Control Tower",
      subtitle: "Admin overview · live AgentOps MIS backend · June 14, 2026",
      loading: "Loading live MIS metrics...",
      backendUnavailable: "Live backend unavailable",
      totalAgents: "Total Agents",
      totalTasks: "Total Tasks",
      recentRuns: "OpenClaw + Recent Runs",
      pendingApprovals: "Pending Approvals",
      memoryDue: "Memory Due",
      runtimeHealth: "Runtime Health",
      failureRate: "Failure Rate",
      totalCost: "Total Cost",
      openclawImports: "OpenClaw Imports",
      agents: "agents",
      tasks: "tasks",
      refresh: "Refresh",
      live: "Live",
      clickToReload: "Click to reload",
      runVolume: "Run Volume (Last 7 Days)",
      costByAgent: "Cost by Agent (USD)",
      hermesDefault: "Hermes Default",
      notionBase: "Notion Base",
      taskStatus: "Task Status",
      topAgentsByCost: "Top Agents by Cost",
      agentPerformance: "Agent Performance Summary",
      performanceHeaders: ["Agent", "Runtime", "Status", "Runs", "Success Rate", "Cost Used", "Approvals"],
      refreshMetrics: "Refresh live metrics",
    },
    zh: {
      title: "控制塔",
      subtitle: "后台总览 · 连接本地 AgentOps MIS 后端 · 2026 年 6 月 14 日",
      loading: "正在加载实时 MIS 指标...",
      backendUnavailable: "本地后端不可用",
      totalAgents: "代理总数",
      totalTasks: "任务总数",
      recentRuns: "OpenClaw + 近期运行",
      pendingApprovals: "待审批",
      memoryDue: "待处理记忆",
      runtimeHealth: "运行时健康",
      failureRate: "失败率",
      totalCost: "总成本",
      openclawImports: "OpenClaw 导入",
      agents: "代理",
      tasks: "任务",
      refresh: "刷新",
      live: "实时",
      clickToReload: "点击重新加载",
      runVolume: "运行量（最近 7 天）",
      costByAgent: "按代理统计成本（美元）",
      hermesDefault: "Hermes 默认通道",
      notionBase: "Notion 外部库",
      taskStatus: "任务状态",
      topAgentsByCost: "成本最高的代理",
      agentPerformance: "AI 员工绩效摘要",
      performanceHeaders: ["代理", "运行时", "状态", "运行", "成功率", "已用成本", "审批"],
      refreshMetrics: "刷新实时指标",
    },
  });

  return (
    <div className="space-y-6 w-full">
      <div>
        <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>{copy.subtitle}</p>
        {loading && <p className="text-xs mt-2" style={{ color: "var(--mis-muted)" }}>{copy.loading}</p>}
        {error && <p className="text-xs mt-2" style={{ color: "#F87171" }}>{copy.backendUnavailable}: {error}</p>}
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-5 gap-3">
        <MetricCard icon={<Bot size={15} />} label={copy.totalAgents} value={metrics?.agents_total ?? "—"} iconColor="var(--mis-cyan)" trend="up" />
        <MetricCard icon={<ListChecks size={15} />} label={copy.totalTasks} value={totalTasks || "—"} iconColor="var(--mis-primary)" />
        <MetricCard icon={<Play size={15} />} label={copy.recentRuns} value={totalRuns || "—"} iconColor="var(--mis-success)" trend="up" />
        <MetricCard icon={<ShieldAlert size={15} />} label={copy.pendingApprovals} value={metrics?.pending_approvals ?? "—"} iconColor="#FBBF24" />
        <MetricCard icon={<Brain size={15} />} label={copy.memoryDue} value={metrics?.stale_or_due_memories ?? "—"} iconColor="var(--mis-purple)" />
      </div>
      <div className="grid grid-cols-5 gap-3">
        <MetricCard
          icon={<Activity size={15} />}
          label={copy.runtimeHealth}
          value={`${runtimeHealth.filter((r: any) => ["ready", "configured"].includes(String(r.status))).length}/${runtimeHealth.length || 3}`}
          sub={`Hermes ${runtimeStatus("hermes")}`}
          iconColor="var(--mis-warning)"
          trend="down"
        />
        <MetricCard
          icon={<AlertTriangle size={15} />}
          label={copy.failureRate}
          value={`${Math.round(Number(metrics?.failure_rate || 0) * 100)}%`}
          iconColor="#F87171"
        />
        <MetricCard
          icon={<DollarSign size={15} />}
          label={copy.totalCost}
          value={`$${Number(metrics?.total_cost_usd || 0).toFixed(2)}`}
          iconColor="var(--mis-success)"
        />
        <MetricCard
          icon={<Download size={15} />}
          label={copy.openclawImports}
          value={metrics?.openclaw_import?.cron_runs ?? "—"}
          sub={`${metrics?.openclaw_import?.agents ?? 0} ${copy.agents}, ${metrics?.openclaw_import?.cron_tasks ?? 0} ${copy.tasks}`}
          iconColor="var(--mis-cyan)"
        />
        <MetricCard
          icon={<ClipboardList size={15} />}
          label={copy.refresh}
          value={copy.live}
          sub={copy.clickToReload}
          iconColor="var(--mis-warning)"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-4">
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-sm font-semibold mb-4" style={{ color: "var(--mis-text)" }}>{copy.runVolume}</div>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={runVolume}>
              <defs>
                <linearGradient id="runGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22D3EE" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#22D3EE" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--mis-border)" />
              <XAxis dataKey="date" tick={{ fill: "var(--mis-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--mis-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)", borderRadius: 8, fontSize: 11 }}
                labelStyle={{ color: "var(--mis-dim)" }}
                itemStyle={{ color: "var(--mis-cyan)" }}
              />
              <Area name={copy.recentRuns} type="monotone" dataKey="runs" stroke="#22D3EE" strokeWidth={2} fill="url(#runGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-sm font-semibold mb-4" style={{ color: "var(--mis-text)" }}>{copy.costByAgent}</div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={costByAgent} barSize={24}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--mis-border)" />
              <XAxis dataKey="agent" tick={{ fill: "var(--mis-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--mis-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)", borderRadius: 8, fontSize: 11 }}
                labelStyle={{ color: "var(--mis-dim)" }}
                itemStyle={{ color: "var(--mis-purple)" }}
              />
              <Bar name={copy.totalCost} dataKey="cost" fill="#7A5AF8" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Runtime Health */}
      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="text-sm font-semibold mb-3" style={{ color: "var(--mis-text)" }}>{copy.runtimeHealth}</div>
        <div className="flex gap-4">
          {[
            { name: "OpenClaw", status: runtimeStatus("openclaw") },
            { name: copy.hermesDefault, status: runtimeStatus("hermes") },
            { name: copy.notionBase, status: runtimeStatus("notion") },
          ].map(({ name, status }) => (
            <div key={name} className="flex items-center gap-2">
              <span className="text-xs" style={{ color: "var(--mis-dim)" }}>{name}</span>
              <StatusBadge status={status} />
            </div>
          ))}
        </div>
      </div>

      {/* Agent Performance Table */}
      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="text-sm font-semibold mb-3" style={{ color: "var(--mis-text)" }}>{copy.agentPerformance}</div>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: "var(--mis-muted)" }}>
              {copy.performanceHeaders.map(h => (
                <th key={h} className="text-left pb-2 font-medium pr-4">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="space-y-1">
            {agents.map(agent => (
              <tr key={agent.agent_id} style={{ color: "var(--mis-dim)" }}>
                <td className="py-2 pr-4">
                  <div className="font-medium" style={{ color: "var(--mis-text)" }}>{agent.name}</div>
                  <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{agent.agent_id}</div>
                </td>
                <td className="py-2 pr-4">{agent.runtime_type}</td>
                <td className="py-2 pr-4"><StatusBadge status={agent.status} /></td>
                <td className="py-2 pr-4">{agent.run_count}</td>
                <td className="py-2 pr-4">
                  <span style={{ color: agent.success_rate >= 0.8 ? "var(--mis-success)" : "var(--mis-warning)" }}>
                    {Math.round(agent.success_rate * 100)}%
                  </span>
                </td>
                <td className="py-2 pr-4">${agent.budget_used_usd.toFixed(2)}</td>
                <td className="py-2 pr-4">{agent.approval_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <button onClick={refresh} className="mt-4 text-[11px] px-3 py-1.5 rounded" style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}>
          {copy.refreshMetrics}
        </button>
      </div>
    </div>
  );
}
