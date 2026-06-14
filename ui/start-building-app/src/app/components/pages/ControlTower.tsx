import {
  Bot, ListChecks, Play, ShieldAlert, Activity, AlertTriangle,
  DollarSign, Brain, Download, ClipboardList,
} from "lucide-react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { MetricCard } from "../shared/MetricCard";
import { StatusBadge } from "../shared/StatusBadge";
import { dashboardMetrics, agents } from "../../data/mockData";

const metrics = dashboardMetrics;

export function ControlTower() {
  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>Control Tower</h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>Admin overview · v1.2.2 · June 14, 2026</p>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-5 gap-3">
        <MetricCard icon={<Bot size={15} />} label="Total Agents" value={metrics.total_agents} iconColor="var(--mis-cyan)" trend="up" />
        <MetricCard icon={<ListChecks size={15} />} label="Total Tasks" value={metrics.total_tasks} iconColor="var(--mis-primary)" />
        <MetricCard icon={<Play size={15} />} label="Total Runs" value={metrics.total_runs} iconColor="var(--mis-success)" trend="up" />
        <MetricCard icon={<ShieldAlert size={15} />} label="Pending Approvals" value={metrics.pending_approvals} iconColor="#FBBF24" />
        <MetricCard icon={<Brain size={15} />} label="Memory Candidates" value={metrics.memory_candidates} iconColor="var(--mis-purple)" />
      </div>
      <div className="grid grid-cols-5 gap-3">
        <MetricCard
          icon={<Activity size={15} />}
          label="Runtime Health"
          value="2/3"
          sub="Hermes unavailable"
          iconColor="var(--mis-warning)"
          trend="down"
        />
        <MetricCard
          icon={<AlertTriangle size={15} />}
          label="Failure Rate"
          value={`${Math.round(metrics.failure_rate * 100)}%`}
          iconColor="#F87171"
        />
        <MetricCard
          icon={<DollarSign size={15} />}
          label="Total Cost"
          value={`$${metrics.total_cost_usd.toFixed(2)}`}
          iconColor="var(--mis-success)"
        />
        <MetricCard
          icon={<Download size={15} />}
          label="OpenClaw Imports"
          value={metrics.openclaw_import.runs}
          sub={`${metrics.openclaw_import.agents} agents, ${metrics.openclaw_import.tasks} tasks`}
          iconColor="var(--mis-cyan)"
        />
        <MetricCard
          icon={<ClipboardList size={15} />}
          label="Audit Risk Flags"
          value={metrics.audit_risk_flags}
          iconColor="var(--mis-warning)"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-4">
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-sm font-semibold mb-4" style={{ color: "var(--mis-text)" }}>Run Volume (Last 7 Days)</div>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={metrics.run_volume_by_day}>
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
              <Area name="Runs" type="monotone" dataKey="runs" stroke="#22D3EE" strokeWidth={2} fill="url(#runGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-sm font-semibold mb-4" style={{ color: "var(--mis-text)" }}>Cost by Agent (USD)</div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={metrics.cost_by_agent} barSize={24}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--mis-border)" />
              <XAxis dataKey="agent" tick={{ fill: "var(--mis-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--mis-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)", borderRadius: 8, fontSize: 11 }}
                labelStyle={{ color: "var(--mis-dim)" }}
                itemStyle={{ color: "var(--mis-purple)" }}
              />
              <Bar name="Cost (USD)" dataKey="cost" fill="#7A5AF8" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Runtime Health */}
      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="text-sm font-semibold mb-3" style={{ color: "var(--mis-text)" }}>Runtime Health</div>
        <div className="flex gap-4">
          {[
            { name: "OpenClaw", status: metrics.runtime_health.openclaw },
            { name: "Hermes Default", status: metrics.runtime_health.hermes },
            { name: "Notion Base", status: metrics.runtime_health.notion },
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
        <div className="text-sm font-semibold mb-3" style={{ color: "var(--mis-text)" }}>Agent Performance Summary</div>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: "var(--mis-muted)" }}>
              {["Agent", "Runtime", "Status", "Runs", "Success Rate", "Cost Used", "Approvals"].map(h => (
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
      </div>
    </div>
  );
}
