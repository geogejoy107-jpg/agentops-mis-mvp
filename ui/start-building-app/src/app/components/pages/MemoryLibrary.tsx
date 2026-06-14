import { useState } from "react";
import { Brain, CheckCircle, XCircle } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { memories, agents, tasks } from "../../data/mockData";
import type { MemoryReviewStatus, MemoryScope } from "../../data/mockData";

type FilterScope = "all" | MemoryScope;
type FilterStatus = "all" | MemoryReviewStatus;

const SCOPE_COLORS: Record<MemoryScope, string> = {
  task: "var(--mis-primary)", project: "var(--mis-cyan)", org: "var(--mis-purple)",
};

const TYPE_LABELS: Record<string, string> = {
  policy: "Policy", sop: "SOP", decision: "Decision", commitment: "Commitment",
  risk: "Risk", failure_case: "Failure Case", project_context: "Project Context",
  customer_preference: "Customer Pref", agent_lesson: "Agent Lesson", artifact_summary: "Artifact Summary",
};

export function MemoryLibrary() {
  const [scopeFilter, setScopeFilter] = useState<FilterScope>("all");
  const [statusFilter, setStatusFilter] = useState<FilterStatus>("all");

  const filtered = memories.filter(m => {
    if (scopeFilter !== "all" && m.scope !== scopeFilter) return false;
    if (statusFilter !== "all" && m.review_status !== statusFilter) return false;
    return true;
  });

  return (
    <div className="space-y-5 max-w-4xl">
      <div>
        <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>Memory Library</h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
          {memories.length} total · {memories.filter(m => m.review_status === "candidate").length} candidates pending review
        </p>
      </div>

      {/* Filters */}
      <div className="flex gap-4 flex-wrap">
        <div className="flex gap-1">
          {(["all", "task", "project", "org"] as FilterScope[]).map(s => (
            <button
              key={s}
              onClick={() => setScopeFilter(s)}
              className="text-[11px] px-2.5 py-1 rounded transition-all capitalize"
              style={{
                background: scopeFilter === s ? "rgba(34,211,238,0.12)" : "var(--mis-surface)",
                color: scopeFilter === s ? "var(--mis-cyan)" : "var(--mis-dim)",
                border: `1px solid ${scopeFilter === s ? "rgba(34,211,238,0.25)" : "var(--mis-border)"}`,
              }}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(["all", "candidate", "approved", "rejected", "stale"] as FilterStatus[]).map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className="text-[11px] px-2.5 py-1 rounded transition-all capitalize"
              style={{
                background: statusFilter === s ? "rgba(122,90,248,0.12)" : "var(--mis-surface)",
                color: statusFilter === s ? "var(--mis-purple)" : "var(--mis-dim)",
                border: `1px solid ${statusFilter === s ? "rgba(122,90,248,0.25)" : "var(--mis-border)"}`,
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Memory cards */}
      <div className="space-y-2">
        {filtered.length === 0 && (
          <div className="py-12 text-center" style={{ color: "var(--mis-muted)" }}>
            <Brain size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-sm">No memories match this filter</p>
          </div>
        )}
        {filtered.map(m => {
          const agent = agents.find(a => a.agent_id === m.agent_id);
          const task = tasks.find(t => t.task_id === m.task_id);
          const scopeColor = SCOPE_COLORS[m.scope];

          return (
            <div
              key={m.memory_id}
              className="rounded-xl p-4"
              style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
            >
              <div className="flex items-start gap-3">
                <div
                  className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
                  style={{ background: `${scopeColor}18`, color: scopeColor }}
                >
                  <Brain size={13} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1.5">
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded font-medium capitalize"
                      style={{ background: `${scopeColor}15`, color: scopeColor }}
                    >
                      {m.scope}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
                      {TYPE_LABELS[m.memory_type] ?? m.memory_type}
                    </span>
                    <StatusBadge status={m.review_status} />
                    <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
                      Confidence: {Math.round(m.confidence * 100)}%
                    </span>
                  </div>

                  <p className="text-xs leading-relaxed mb-2" style={{ color: "var(--mis-text)" }}>
                    {m.canonical_text}
                  </p>

                  <div className="flex gap-3 text-[10px]" style={{ color: "var(--mis-muted)" }}>
                    {agent && <span>Agent: <span style={{ color: "var(--mis-dim)" }}>{agent.name}</span></span>}
                    {task && <span>Task: <span style={{ color: "var(--mis-dim)" }}>{task.title.slice(0, 30)}…</span></span>}
                    <span>Source: <span style={{ color: "var(--mis-dim)" }}>{m.source_type}</span></span>
                    <span>{new Date(m.created_at).toLocaleDateString()}</span>
                  </div>
                </div>

                {m.review_status === "candidate" && (
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      className="flex items-center gap-1 text-[11px] px-2 py-1 rounded"
                      style={{ background: "rgba(42,157,143,0.15)", color: "var(--mis-success)" }}
                    >
                      <CheckCircle size={11} /> Approve
                    </button>
                    <button
                      className="flex items-center gap-1 text-[11px] px-2 py-1 rounded"
                      style={{ background: "rgba(248,113,113,0.12)", color: "#F87171" }}
                    >
                      <XCircle size={11} /> Reject
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
