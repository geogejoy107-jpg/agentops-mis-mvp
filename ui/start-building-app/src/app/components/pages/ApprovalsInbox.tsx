import { ShieldAlert, Clock, CheckCircle, XCircle } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { approvals, agents, tasks, toolCalls } from "../../data/mockData";

export function ApprovalsInbox() {
  const pending = approvals.filter(a => a.decision === "pending");
  const decided = approvals.filter(a => a.decision !== "pending");

  const renderCard = (ap: typeof approvals[number]) => {
    const agent = agents.find(a => a.agent_id === ap.requested_by_agent_id);
    const task = tasks.find(t => t.task_id === ap.task_id);
    const tool = toolCalls.find(tc => tc.tool_call_id === ap.tool_call_id);
    const isPending = ap.decision === "pending";

    return (
      <div
        key={ap.approval_id}
        className="rounded-xl p-4"
        style={{
          background: "var(--mis-surface)",
          border: `1px solid ${isPending ? "rgba(251,191,36,0.25)" : "var(--mis-border)"}`,
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <ShieldAlert size={13} style={{ color: isPending ? "#FBBF24" : "var(--mis-muted)" }} />
              <span className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>
                {tool?.tool_name ?? "Tool action"}
              </span>
              <StatusBadge status={ap.decision} />
            </div>
            <p className="text-[11px] mb-2" style={{ color: "var(--mis-dim)" }}>{ap.reason}</p>

            <div className="flex flex-wrap gap-3 text-[10px]" style={{ color: "var(--mis-muted)" }}>
              <span>Agent: <span style={{ color: "var(--mis-dim)" }}>{agent?.name ?? ap.requested_by_agent_id}</span></span>
              <span>Task: <span style={{ color: "var(--mis-dim)" }}>{task?.title?.slice(0, 30) ?? ap.task_id}</span></span>
              {tool && <span>Risk: <span style={{ color: tool.risk_level === "high" ? "var(--mis-warning)" : "var(--mis-dim)" }}>{tool.risk_level}</span></span>}
              {isPending && (
                <span>Expires: <span style={{ color: "#FBBF24" }}>{new Date(ap.expires_at).toLocaleTimeString()}</span></span>
              )}
              {!isPending && ap.decided_at && (
                <span>Decided: <span style={{ color: "var(--mis-dim)" }}>{new Date(ap.decided_at).toLocaleString()}</span></span>
              )}
            </div>
          </div>

          {isPending && (
            <div className="flex gap-2 shrink-0">
              <button
                className="flex items-center gap-1 text-[11px] px-3 py-1.5 rounded"
                style={{ background: "rgba(42,157,143,0.15)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.2)" }}
              >
                <CheckCircle size={11} /> Approve
              </button>
              <button
                className="flex items-center gap-1 text-[11px] px-3 py-1.5 rounded"
                style={{ background: "rgba(248,113,113,0.12)", color: "#F87171", border: "1px solid rgba(248,113,113,0.2)" }}
              >
                <XCircle size={11} /> Reject
              </button>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6 w-full">
      <div>
        <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>Approvals Inbox</h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
          {pending.length} pending · {decided.length} decided
        </p>
      </div>

      {/* Pending */}
      {pending.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Clock size={13} style={{ color: "#FBBF24" }} />
            <span className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>Pending Approval</span>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-semibold"
              style={{ background: "rgba(251,191,36,0.15)", color: "#FBBF24" }}
            >
              {pending.length}
            </span>
          </div>
          <div className="space-y-2">{pending.map(renderCard)}</div>
        </div>
      )}

      {/* Decided */}
      {decided.length > 0 && (
        <div>
          <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-muted)" }}>Decision History</div>
          <div className="space-y-2">{decided.map(renderCard)}</div>
        </div>
      )}
    </div>
  );
}
