import { BarChart, Bar, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell } from "recharts";
import { Link } from "react-router";
import { dashboardMetrics, agents, tasks, evaluations } from "../../data/mockData";
import { loadCustomerDeliveryBoard, loadCustomerProjects, useLiveData } from "../../data/liveApi";
import { usePreferences } from "../../context/PreferencesContext";

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
  const { locale } = usePreferences();
  const zh = locale === "zh";
  const customerProjects = useLiveData(() => loadCustomerProjects(8), []);
  const customerDeliveryBoard = useLiveData(() => loadCustomerDeliveryBoard(12), []);
  const projects = customerProjects.data?.projects || [];
  const deliveries = customerDeliveryBoard.data?.deliveries || [];
  const deliverySummary = customerDeliveryBoard.data?.summary;

  const statusLabel = (status: string) => {
    const zhLabels: Record<string, string> = {
      ready: "可交付",
      waiting_approval: "待审批",
      in_progress: "进行中",
      needs_attention: "需处理",
      attention: "注意",
      empty: "暂无",
    };
    const enLabels: Record<string, string> = {
      ready: "Ready",
      waiting_approval: "Waiting approval",
      in_progress: "In progress",
      needs_attention: "Needs attention",
      attention: "Attention",
      empty: "Empty",
    };
    return (zh ? zhLabels : enLabels)[status] || status;
  };

  return (
    <div className="space-y-6 w-full">
      <div>
        <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{zh ? "报告" : "Reports"}</h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>{zh ? "客户交付报告 · 运行绩效 · 质量评估" : "Customer delivery reports · runtime performance · quality evaluation"}</p>
      </div>

      <div className="rounded-xl p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-3">
          <div>
            <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{zh ? "客户交付看板" : "Customer delivery board"}</div>
            <div className="text-[11px] mt-0.5 max-w-3xl" style={{ color: "var(--mis-muted)" }}>
              {zh ? "按客户视角聚合最近交付：artifact、task、run、审批、评估、审计证据和下一步动作。只读，不触发真实运行。"
                : "Customer-facing readback of recent deliveries: artifact, task, run, approvals, evaluations, audit evidence, and next action. Read-only; no live execution."}
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <span className="rounded px-2 py-1 text-[10px]" style={{ color: "var(--mis-success)", background: "rgba(45,212,191,0.10)", border: "1px solid rgba(45,212,191,0.18)" }}>
              {zh ? "只读" : "Read-only"}: {customerDeliveryBoard.data?.safety?.read_only ? (zh ? "是" : "yes") : "—"}
            </span>
            <span className="rounded px-2 py-1 text-[10px]" style={{ color: "var(--mis-cyan)", background: "rgba(34,211,238,0.10)", border: "1px solid rgba(34,211,238,0.18)" }}>
              {zh ? "未触发真实执行" : "No live execution"}: {customerDeliveryBoard.data?.safety?.live_execution_performed === false ? (zh ? "是" : "yes") : "—"}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
          {[
            { label: zh ? "交付总数" : "Deliveries", value: deliverySummary?.deliveries ?? 0, color: "var(--mis-cyan)" },
            { label: zh ? "可交付" : "Ready", value: deliverySummary?.ready ?? 0, color: "var(--mis-success)" },
            { label: zh ? "待审批" : "Waiting approval", value: deliverySummary?.waiting_approval ?? 0, color: "var(--mis-warning)" },
            { label: zh ? "需处理" : "Needs attention", value: deliverySummary?.needs_attention ?? 0, color: "#F87171" },
          ].map((item) => (
            <div key={item.label} className="rounded-lg px-3 py-2" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
              <div className="text-xl font-semibold mt-1" style={{ color: item.color }}>{item.value}</div>
            </div>
          ))}
        </div>

        <div className="mt-3 grid grid-cols-1 xl:grid-cols-2 gap-2">
          {customerDeliveryBoard.loading && (
            <div className="text-[11px]" style={{ color: "var(--mis-dim)" }}>{zh ? "正在加载交付..." : "Loading deliveries..."}</div>
          )}
          {customerDeliveryBoard.error && (
            <div className="text-[11px]" style={{ color: "#FCA5A5" }}>{customerDeliveryBoard.error}</div>
          )}
          {!customerDeliveryBoard.loading && !customerDeliveryBoard.error && deliveries.length === 0 && (
            <div className="text-[11px]" style={{ color: "var(--mis-dim)" }}>{zh ? "还没有客户交付。先从 Pixel Office 或 AI 员工页派发一个客户任务。" : "No customer deliveries yet. Dispatch a customer task from Pixel Office or AI Employees first."}</div>
          )}
          {deliveries.map((delivery) => (
            <div key={delivery.delivery_id} className="rounded-lg p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs font-semibold truncate" style={{ color: "var(--mis-text)" }}>{delivery.title}</div>
                  <div className="mt-1 text-[10px] truncate" style={{ color: "var(--mis-muted)" }}>{delivery.artifact_id}</div>
                </div>
                <span className="rounded px-2 py-1 text-[10px] shrink-0" style={{ color: delivery.status === "needs_attention" ? "#F87171" : delivery.status === "waiting_approval" ? "var(--mis-warning)" : "var(--mis-success)", background: "rgba(148,163,184,0.10)" }}>
                  {statusLabel(delivery.status)}
                </span>
              </div>
              <div className="mt-2 text-[11px] line-clamp-2" style={{ color: "var(--mis-dim)" }}>{delivery.summary}</div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]" style={{ color: "var(--mis-dim)" }}>
                <div>{zh ? "审批" : "Approvals"}<br /><span style={{ color: "var(--mis-text)" }}>{delivery.pending_approval_ids?.length || 0}</span></div>
                <div>{zh ? "评估" : "Evals"}<br /><span style={{ color: "var(--mis-text)" }}>{delivery.evaluation_summary?.count || 0}</span></div>
                <div>{zh ? "审计" : "Audit"}<br /><span style={{ color: "var(--mis-text)" }}>{delivery.evidence?.audit_logs || 0}</span></div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {delivery.task_id && (
                  <Link to={`/admin/tasks/${delivery.task_id}`} className="text-[10px] rounded px-2 py-1" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>
                    {zh ? "打开任务" : "Open task"}
                  </Link>
                )}
                {delivery.run_id && (
                  <Link to={`/admin/runs/${delivery.run_id}`} className="text-[10px] rounded px-2 py-1" style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}>
                    {zh ? "打开 Run" : "Open run"}
                  </Link>
                )}
                {delivery.ui_report_url && (
                  <Link to={delivery.ui_report_url} className="text-[10px] rounded px-2 py-1" style={{ background: "rgba(251,191,36,0.10)", color: "var(--mis-warning)", border: "1px solid rgba(251,191,36,0.20)" }}>
                    {zh ? "打开报告" : "Open report"}
                  </Link>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{zh ? "客户项目报告" : "Customer project reports"}</div>
            <div className="text-[11px] mt-0.5" style={{ color: "var(--mis-muted)" }}>
              {zh ? "从 MIS 账本推导，可打开交付报告并查看是否已归档。" : "Derived from the MIS ledger. Open delivery reports and see whether they are archived."}
            </div>
          </div>
          <Link to="/workspace/pixel-office" className="text-[11px] rounded px-3 py-1.5" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}>
            {zh ? "创建新项目" : "Create project"}
          </Link>
        </div>
        <div className="mt-3 grid grid-cols-1 xl:grid-cols-2 gap-2">
          {customerProjects.loading && (
            <div className="text-[11px]" style={{ color: "var(--mis-dim)" }}>{zh ? "正在加载项目..." : "Loading projects..."}</div>
          )}
          {customerProjects.error && (
            <div className="text-[11px]" style={{ color: "#FCA5A5" }}>{customerProjects.error}</div>
          )}
          {!customerProjects.loading && !customerProjects.error && projects.length === 0 && (
            <div className="text-[11px]" style={{ color: "var(--mis-dim)" }}>{zh ? "还没有客户项目。" : "No customer projects yet."}</div>
          )}
          {projects.map((project) => (
            <Link
              key={project.project_id}
              to={project.ui_report_url}
              className="rounded-lg p-3 hover:opacity-85"
              style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{project.title}</div>
                  <div className="mt-1 text-[10px]" style={{ color: "var(--mis-muted)" }}>{project.project_id}</div>
                </div>
                <span className="rounded px-2 py-1 text-[10px]" style={{ color: project.status === "waiting_approval" ? "var(--mis-warning)" : "var(--mis-success)", background: "rgba(148,163,184,0.10)" }}>
                  {project.status}
                </span>
              </div>
              <div className="mt-2 grid grid-cols-4 gap-2 text-[10px]" style={{ color: "var(--mis-dim)" }}>
                <div>{zh ? "任务" : "Tasks"}<br /><span style={{ color: "var(--mis-text)" }}>{project.task_count}</span></div>
                <div>{zh ? "运行" : "Runs"}<br /><span style={{ color: "var(--mis-text)" }}>{project.run_count}</span></div>
                <div>{zh ? "审批" : "Approvals"}<br /><span style={{ color: "var(--mis-text)" }}>{project.pending_approvals}</span></div>
                <div>{zh ? "归档" : "Archive"}<br /><span style={{ color: "var(--mis-text)" }}>{project.report_artifact_id ? "yes" : "no"}</span></div>
              </div>
            </Link>
          ))}
        </div>
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
