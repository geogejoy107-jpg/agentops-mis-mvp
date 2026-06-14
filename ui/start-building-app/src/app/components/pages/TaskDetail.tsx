import { useParams } from "react-router";
import { CheckCircle, Users, Clock, ShieldCheck } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { RiskBadge } from "../shared/RiskBadge";
import { loadAgents, loadDashboard, loadTaskDetail, useLiveData } from "../../data/liveApi";

export function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, loading, error } = useLiveData(async () => {
    const metrics = await loadDashboard();
    const [detail, agents] = await Promise.all([loadTaskDetail(id || ""), loadAgents(metrics)]);
    return { detail, agents };
  }, [id]);

  if (loading) {
    return <p className="text-xs" style={{ color: "var(--mis-muted)" }}>Loading live task detail...</p>;
  }
  if (error || !data?.detail?.task) {
    return <p className="text-xs" style={{ color: "#F87171" }}>Live task detail unavailable: {error || "not found"}</p>;
  }

  const task = data.detail.task;
  const taskRuns = data.detail.runs;
  const taskApprovals = data.detail.approvals;
  const taskMemories = data.detail.memories;
  const taskEvals = data.detail.evaluations;
  const latestEval = taskEvals[taskEvals.length - 1];
  const latestScore = latestEval ? (latestEval.score <= 1 ? Math.round(latestEval.score * 100) : Math.round(latestEval.score)) : 0;

  const ownerAgent = data.agents.find(a => a.agent_id === task.owner_agent_id);
  const collabAgents = data.agents.filter(a => task.collaborator_agent_ids.includes(a.agent_id));

  const priorityColor: Record<string, string> = {
    low: "var(--mis-success)", medium: "var(--mis-primary)", high: "var(--mis-warning)", critical: "#F87171",
  };

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div
        className="rounded-xl p-5"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap mb-2">
              <h1 className="text-base font-semibold" style={{ color: "var(--mis-text)" }}>{task.title}</h1>
              <StatusBadge status={task.status} size="md" />
              <RiskBadge risk={task.risk_level} />
              <span
                className="text-[11px] px-2 py-0.5 rounded font-medium capitalize"
                style={{ color: priorityColor[task.priority], background: `${priorityColor[task.priority]}18` }}
              >
                {task.priority} priority
              </span>
            </div>
            <p className="text-xs" style={{ color: "var(--mis-dim)" }}>{task.description}</p>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4 mt-4 pt-4" style={{ borderTop: "1px solid var(--mis-border)" }}>
          <div>
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>Task ID</div>
            <div className="text-xs font-mono mt-0.5" style={{ color: "var(--mis-dim)" }}>{task.task_id}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>Owner Agent</div>
            <div className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>{ownerAgent?.name ?? task.owner_agent_id}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>Budget</div>
            <div className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>${task.budget_limit_usd}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>Due</div>
            <div className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
              {task.due_date ? new Date(task.due_date).toLocaleDateString() : "—"}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Acceptance Criteria */}
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-xs font-semibold flex items-center gap-1.5 mb-3" style={{ color: "var(--mis-text)" }}>
            <CheckCircle size={13} style={{ color: "var(--mis-success)" }} />
            Acceptance Criteria
          </div>
          <p className="text-xs leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {task.acceptance_criteria || "No criteria specified."}
          </p>

          {latestEval && (
            <div className="mt-4">
              <div className="text-[10px] uppercase tracking-wide mb-1.5" style={{ color: "var(--mis-muted)" }}>
                Quality Gate — Latest Eval
              </div>
              <div className="flex items-center gap-3">
                <div className="flex-1 rounded-full h-2 overflow-hidden" style={{ background: "var(--mis-border)" }}>
                  <div
                    className="h-2 rounded-full"
                    style={{
                      width: `${latestScore}%`,
                      background: latestScore >= 80 ? "var(--mis-success)" : "var(--mis-warning)",
                    }}
                  />
                </div>
                <span className="text-xs font-semibold shrink-0" style={{ color: latestScore >= 80 ? "var(--mis-success)" : "var(--mis-warning)" }}>
                  {latestScore}/100
                </span>
                <StatusBadge status={latestEval.pass_fail} />
              </div>
              <p className="text-[11px] mt-2" style={{ color: "var(--mis-muted)" }}>{latestEval.notes}</p>
            </div>
          )}
        </div>

        {/* Collaborators + Approvals */}
        <div className="space-y-3">
          {collabAgents.length > 0 && (
            <div
              className="rounded-xl p-4"
              style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
            >
              <div className="text-xs font-semibold flex items-center gap-1.5 mb-3" style={{ color: "var(--mis-text)" }}>
                <Users size={13} style={{ color: "var(--mis-primary)" }} />
                Collaborating Agents
              </div>
              <div className="space-y-1.5">
                {collabAgents.map(a => (
                  <div key={a.agent_id} className="flex items-center justify-between text-xs">
                    <span style={{ color: "var(--mis-dim)" }}>{a.name}</span>
                    <StatusBadge status={a.status} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {taskApprovals.length > 0 && (
            <div
              className="rounded-xl p-4"
              style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
            >
              <div className="text-xs font-semibold flex items-center gap-1.5 mb-3" style={{ color: "var(--mis-text)" }}>
                <ShieldCheck size={13} style={{ color: "#FBBF24" }} />
                Approvals
              </div>
              <div className="space-y-2">
                {taskApprovals.map(ap => (
                  <div key={ap.approval_id} className="p-2.5 rounded-lg" style={{ background: "var(--mis-surface2)" }}>
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] truncate" style={{ color: "var(--mis-dim)" }}>{ap.reason}</span>
                      <StatusBadge status={ap.decision} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Runs */}
      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-text)" }}>Related Runs</div>
        {taskRuns.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--mis-muted)" }}>No runs yet.</p>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: "var(--mis-muted)" }}>
                {["Run ID", "Agent", "Runtime", "Status", "Cost", "Tokens"].map(h => (
                  <th key={h} className="text-left pb-2 font-medium pr-4">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {taskRuns.map(run => (
                <tr key={run.run_id} style={{ color: "var(--mis-dim)" }}>
                  <td className="py-2 pr-4 font-mono text-[11px]">{run.run_id}</td>
                  <td className="py-2 pr-4">{run.agent_id}</td>
                  <td className="py-2 pr-4">{run.runtime_type}</td>
                  <td className="py-2 pr-4"><StatusBadge status={run.status} /></td>
                  <td className="py-2 pr-4">${run.cost_usd.toFixed(3)}</td>
                  <td className="py-2 pr-4">{run.input_tokens + run.output_tokens}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Memory Candidates */}
      {taskMemories.length > 0 && (
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-text)" }}>Memory Candidates</div>
          <div className="space-y-2">
            {taskMemories.map(m => (
              <div key={m.memory_id} className="p-2.5 rounded-lg flex items-start justify-between gap-3" style={{ background: "var(--mis-surface2)" }}>
                <p className="text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>{m.canonical_text}</p>
                <StatusBadge status={m.review_status} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
