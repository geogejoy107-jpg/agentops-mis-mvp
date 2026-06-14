import { BarChart, Bar, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell } from "recharts";
import { dashboardMetrics, agents, tasks, evaluations } from "../../data/mockData";

const taskStatusDist = [
  { name: "Running",          value: tasks.filter(t => t.status === "running").length,          color: "#22D3EE" },
  { name: "Awaiting Approval",value: tasks.filter(t => t.status === "waiting_approval").length,  color: "#FBBF24" },
  { name: "Completed",        value: tasks.filter(t => t.status === "completed").length,         color: "#2A9D8F" },
  { name: "Failed",           value: tasks.filter(t => t.status === "failed").length,            color: "#F87171" },
  { name: "Blocked",          value: tasks.filter(t => t.status === "blocked").length,           color: "#E76F51" },
  { name: "Planned",          value: tasks.filter(t => t.status === "planned").length,           color: "#2E86AB" },
  { name: "Backlog",          value: tasks.filter(t => t.status === "backlog").length,           color: "#6B7280" },
].filter(d => d.value > 0);

const agentSuccessData = agents.map(a => ({
  name: a.name.split(" ")[0],
  success: Math.round(a.success_rate * 100),
  runs: a.run_count,
}));

const evalScores = evaluations.map(e => ({
  id: e.evaluation_id.replace("eval_", "#"),
  score: e.score,
  pass: e.pass_fail === "pass",
}));

export function Reports() {
  return (
    <div className="space-y-6 w-full">
      <div>
        <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>Reports</h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>Sprint summary · June 2026</p>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Total Cost", value: `$${dashboardMetrics.total_cost_usd.toFixed(2)}`, color: "var(--mis-success)" },
          { label: "Failure Rate", value: `${Math.round(dashboardMetrics.failure_rate * 100)}%`, color: "var(--mis-warning)" },
          { label: "Total Runs", value: dashboardMetrics.total_runs, color: "var(--mis-cyan)" },
          { label: "Avg Eval Score", value: `${Math.round(evaluations.reduce((s, e) => s + e.score, 0) / evaluations.length)}/100`, color: "var(--mis-purple)" },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-xl p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="text-[10px] uppercase tracking-wide mb-1" style={{ color: "var(--mis-muted)" }}>{label}</div>
            <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Run volume */}
        <div className="rounded-xl p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="text-xs font-semibold mb-4" style={{ color: "var(--mis-text)" }}>Run Volume (Last 7 Days)</div>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={dashboardMetrics.run_volume_by_day}>
              <defs>
                <linearGradient id="repRunGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22D3EE" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#22D3EE" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--mis-border)" />
              <XAxis dataKey="date" tick={{ fill: "var(--mis-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--mis-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)", borderRadius: 8, fontSize: 11 }} labelStyle={{ color: "var(--mis-dim)" }} />
              <Area name="Runs" type="monotone" dataKey="runs" stroke="#22D3EE" strokeWidth={2} fill="url(#repRunGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Task status pie */}
        <div className="rounded-xl p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="text-xs font-semibold mb-4" style={{ color: "var(--mis-text)" }}>Task Status Distribution</div>
          <div className="flex items-center gap-4">
            <PieChart width={130} height={130}>
              <Pie data={taskStatusDist} cx={60} cy={60} innerRadius={35} outerRadius={58} dataKey="value" paddingAngle={2}>
                {taskStatusDist.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
            </PieChart>
            <div className="space-y-1.5">
              {taskStatusDist.map(d => (
                <div key={d.name} className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: d.color }} />
                  <span className="text-[11px]" style={{ color: "var(--mis-dim)" }}>{d.name}</span>
                  <span className="text-[11px] font-semibold ml-auto" style={{ color: "var(--mis-text)" }}>{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Agent success rates */}
        <div className="rounded-xl p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="text-xs font-semibold mb-4" style={{ color: "var(--mis-text)" }}>Agent Success Rate (%)</div>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={agentSuccessData} barSize={22}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--mis-border)" />
              <XAxis dataKey="name" tick={{ fill: "var(--mis-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fill: "var(--mis-muted)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)", borderRadius: 8, fontSize: 11 }} />
              <Bar name="Success %" dataKey="success" fill="#2A9D8F" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Evaluation scores */}
        <div className="rounded-xl p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-text)" }}>Evaluation Scores</div>
          <div className="space-y-3">
            {evaluations.map(e => (
              <div key={e.evaluation_id}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px]" style={{ color: "var(--mis-dim)" }}>{e.run_id} · {e.evaluator_type}</span>
                  <span
                    className="text-[11px] font-semibold"
                    style={{ color: e.score >= 80 ? "var(--mis-success)" : "var(--mis-warning)" }}
                  >
                    {e.score}/100 {e.pass_fail === "pass" ? "✓" : "✗"}
                  </span>
                </div>
                <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--mis-border)" }}>
                  <div
                    className="h-1.5 rounded-full"
                    style={{
                      width: `${e.score}%`,
                      background: e.score >= 80 ? "var(--mis-success)" : "var(--mis-warning)",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Notion export CTA */}
      <div
        className="rounded-xl p-4 flex items-center justify-between"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div>
          <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>Export Sprint Report to Notion</div>
          <div className="text-[11px] mt-0.5" style={{ color: "var(--mis-muted)" }}>
            Dry-run preview · no real write unless confirmed
          </div>
        </div>
        <button
          className="text-xs px-4 py-2 rounded-lg"
          style={{ background: "rgba(46,134,171,0.15)", color: "var(--mis-primary)", border: "1px solid rgba(46,134,171,0.25)" }}
        >
          Preview Export
        </button>
      </div>
    </div>
  );
}
