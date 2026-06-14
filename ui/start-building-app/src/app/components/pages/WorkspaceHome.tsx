import { CheckCircle, Clock, ShieldAlert, Brain, Database, Plus, Play } from "lucide-react";
import { Link } from "react-router";
import { StatusBadge } from "../shared/StatusBadge";
import { RiskBadge } from "../shared/RiskBadge";
import { PixelHero } from "../shared/PixelHero";
import { tasks, approvals, runs, memories, agents } from "../../data/mockData";

const activeTasks = tasks.filter(t => ["running", "waiting_approval", "planned"].includes(t.status));
const pendingApprovals = approvals.filter(a => a.decision === "pending");
const recentRuns = runs.slice(0, 4);
const memoryCandidates = memories.filter(m => m.review_status === "candidate").slice(0, 3);

export function WorkspaceHome() {
  return (
    <div className="space-y-6 max-w-5xl">
      {/* Pixel Hero */}
      <PixelHero />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>
            Workspace Home
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
            Sunday, June 14, 2026 · AgentOps Demo
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded"
            style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}
          >
            <Plus size={13} />
            New Task
          </button>
          <button
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded"
            style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
          >
            <Play size={13} />
            Start Run
          </button>
        </div>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { icon: <Play size={15} />, label: "Active Tasks", value: activeTasks.length, color: "var(--mis-cyan)" },
          { icon: <ShieldAlert size={15} />, label: "Pending Approvals", value: pendingApprovals.length, color: "#FBBF24" },
          { icon: <CheckCircle size={15} />, label: "Runs Today", value: 5, color: "var(--mis-success)" },
          { icon: <Brain size={15} />, label: "Memory Candidates", value: memoryCandidates.length, color: "var(--mis-purple)" },
        ].map(({ icon, label, value, color }) => (
          <div
            key={label}
            className="rounded-xl p-4"
            style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
          >
            <div className="flex items-center gap-2 mb-2" style={{ color }}>
              {icon}
              <span className="text-[11px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{label}</span>
            </div>
            <div className="text-2xl font-semibold" style={{ color: "var(--mis-text)" }}>{value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Pending Approvals */}
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold flex items-center gap-2" style={{ color: "var(--mis-text)" }}>
              <ShieldAlert size={14} style={{ color: "#FBBF24" }} />
              Pending Approvals
            </h2>
            <StatusBadge status="pending" />
          </div>
          <div className="space-y-2">
            {pendingApprovals.map(ap => (
              <div
                key={ap.approval_id}
                className="p-3 rounded-lg"
                style={{ background: "var(--mis-surface2)", border: "1px solid rgba(251,191,36,0.2)" }}
              >
                <div className="text-xs font-medium" style={{ color: "var(--mis-text)" }}>{ap.reason}</div>
                <div className="text-[11px] mt-1" style={{ color: "var(--mis-dim)" }}>
                  Agent: {ap.requested_by_agent_id} · Expires: {new Date(ap.expires_at).toLocaleTimeString()}
                </div>
                <div className="flex gap-2 mt-2">
                  <button className="text-[11px] px-2 py-1 rounded" style={{ background: "rgba(42,157,143,0.2)", color: "var(--mis-success)" }}>
                    Approve
                  </button>
                  <button className="text-[11px] px-2 py-1 rounded" style={{ background: "rgba(248,113,113,0.15)", color: "#F87171" }}>
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Active Tasks */}
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <h2 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: "var(--mis-text)" }}>
            <Clock size={14} style={{ color: "var(--mis-cyan)" }} />
            Active Tasks
          </h2>
          <div className="space-y-2">
            {activeTasks.slice(0, 4).map(task => (
              <Link
                key={task.task_id}
                to={`/admin/tasks/${task.task_id}`}
                className="flex items-center justify-between p-2.5 rounded-lg hover:opacity-80 transition-opacity"
                style={{ background: "var(--mis-surface2)" }}
              >
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate" style={{ color: "var(--mis-text)" }}>{task.title}</div>
                  <div className="text-[11px] mt-0.5" style={{ color: "var(--mis-dim)" }}>
                    {task.owner_agent_id}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-2">
                  <RiskBadge risk={task.risk_level} />
                  <StatusBadge status={task.status} />
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* Recent Runs */}
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <h2 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: "var(--mis-text)" }}>
            <Play size={14} style={{ color: "var(--mis-success)" }} />
            Recent Runs
          </h2>
          <div className="space-y-2">
            {recentRuns.map(run => (
              <Link
                key={run.run_id}
                to={`/admin/runs/${run.run_id}`}
                className="flex items-center justify-between p-2.5 rounded-lg hover:opacity-80 transition-opacity"
                style={{ background: "var(--mis-surface2)" }}
              >
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate" style={{ color: "var(--mis-text)" }}>{run.run_id}</div>
                  <div className="text-[11px] mt-0.5" style={{ color: "var(--mis-dim)" }}>
                    {run.agent_id} · {run.runtime_type}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-2">
                  <span className="text-[11px]" style={{ color: "var(--mis-muted)" }}>${run.cost_usd.toFixed(2)}</span>
                  <StatusBadge status={run.status} />
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* Memory Candidates + Connected Bases */}
        <div className="space-y-3">
          <div
            className="rounded-xl p-4"
            style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
          >
            <h2 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: "var(--mis-text)" }}>
              <Brain size={14} style={{ color: "var(--mis-purple)" }} />
              Memory Candidates
            </h2>
            <div className="space-y-2">
              {memoryCandidates.map(m => (
                <div key={m.memory_id} className="p-2.5 rounded-lg" style={{ background: "var(--mis-surface2)" }}>
                  <div className="text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
                    {m.canonical_text.slice(0, 80)}…
                  </div>
                  <div className="flex items-center gap-2 mt-1.5">
                    <StatusBadge status={m.review_status} />
                    <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
                      Confidence: {Math.round(m.confidence * 100)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div
            className="rounded-xl p-4"
            style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
          >
            <h2 className="text-sm font-semibold flex items-center gap-2 mb-3" style={{ color: "var(--mis-text)" }}>
              <Database size={14} style={{ color: "var(--mis-primary)" }} />
              Connected Bases
            </h2>
            <div className="space-y-2">
              {[
                { name: "Agent-MIS Local", status: "ready", type: "Primary ledger" },
                { name: "Notion", status: "dry_run", type: "External base" },
              ].map(b => (
                <div key={b.name} className="flex items-center justify-between p-2.5 rounded-lg" style={{ background: "var(--mis-surface2)" }}>
                  <div>
                    <div className="text-xs font-medium" style={{ color: "var(--mis-text)" }}>{b.name}</div>
                    <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{b.type}</div>
                  </div>
                  <StatusBadge status={b.status} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
