import { useState } from "react";
import { Link } from "react-router";
import { Plus, Filter } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { RiskBadge } from "../shared/RiskBadge";
import { tasks } from "../../data/mockData";

type FilterStatus = "all" | "running" | "waiting_approval" | "planned" | "completed" | "failed" | "blocked";

const STATUS_TABS: { label: string; value: FilterStatus }[] = [
  { label: "All", value: "all" },
  { label: "Running", value: "running" },
  { label: "Awaiting Approval", value: "waiting_approval" },
  { label: "Planned", value: "planned" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
  { label: "Blocked", value: "blocked" },
];

const PRIORITY_COLOR: Record<string, string> = {
  low: "var(--mis-success)", medium: "var(--mis-primary)", high: "var(--mis-warning)", critical: "#F87171",
};

export function MyTasks() {
  const [filter, setFilter] = useState<FilterStatus>("all");

  const filtered = filter === "all" ? tasks : tasks.filter(t => t.status === filter);

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>My Tasks</h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
            {tasks.length} tasks · {tasks.filter(t => t.status === "running").length} active
          </p>
        </div>
        <button
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded"
          style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
        >
          <Plus size={13} /> New Task
        </button>
      </div>

      {/* Status filter tabs */}
      <div className="flex gap-1 flex-wrap">
        {STATUS_TABS.map(tab => (
          <button
            key={tab.value}
            onClick={() => setFilter(tab.value)}
            className="text-[11px] px-3 py-1.5 rounded-lg transition-all"
            style={{
              background: filter === tab.value ? "rgba(34,211,238,0.12)" : "var(--mis-surface)",
              color: filter === tab.value ? "var(--mis-cyan)" : "var(--mis-dim)",
              border: `1px solid ${filter === tab.value ? "rgba(34,211,238,0.25)" : "var(--mis-border)"}`,
            }}
          >
            {tab.label}
            <span className="ml-1.5 opacity-60">
              {tab.value === "all" ? tasks.length : tasks.filter(t => t.status === tab.value).length}
            </span>
          </button>
        ))}
      </div>

      {/* Task list */}
      <div className="space-y-2">
        {filtered.length === 0 && (
          <div className="py-12 text-center" style={{ color: "var(--mis-muted)" }}>
            <Filter size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-sm">No tasks in this status</p>
          </div>
        )}
        {filtered.map(task => (
          <Link
            key={task.task_id}
            to={`/admin/tasks/${task.task_id}`}
            className="block rounded-xl p-4 hover:opacity-90 transition-opacity"
            style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-sm font-medium" style={{ color: "var(--mis-text)" }}>{task.title}</span>
                  <StatusBadge status={task.status} />
                  <RiskBadge risk={task.risk_level} />
                </div>
                <p className="text-[11px] line-clamp-1" style={{ color: "var(--mis-dim)" }}>{task.description}</p>
                <div className="flex items-center gap-4 mt-2">
                  <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
                    Agent: <span style={{ color: "var(--mis-dim)" }}>{task.owner_agent_id}</span>
                  </span>
                  {task.due_date && (
                    <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
                      Due: <span style={{ color: "var(--mis-dim)" }}>{new Date(task.due_date).toLocaleDateString()}</span>
                    </span>
                  )}
                  <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
                    Budget: <span style={{ color: "var(--mis-dim)" }}>${task.budget_limit_usd}</span>
                  </span>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <span
                  className="text-[11px] px-2 py-0.5 rounded font-medium capitalize"
                  style={{ color: PRIORITY_COLOR[task.priority], background: `${PRIORITY_COLOR[task.priority]}18` }}
                >
                  {task.priority}
                </span>
                {task.acceptance_criteria && (
                  <div className="text-[10px] mt-1.5 max-w-48 text-right line-clamp-1" style={{ color: "var(--mis-muted)" }}>
                    {task.acceptance_criteria.slice(0, 40)}…
                  </div>
                )}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
