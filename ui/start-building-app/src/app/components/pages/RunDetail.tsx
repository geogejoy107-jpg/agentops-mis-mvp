import { useParams } from "react-router";
import { Cpu, DollarSign, Clock, GitBranch, AlertTriangle } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { RiskBadge } from "../shared/RiskBadge";
import { AuditTimeline } from "../shared/AuditTimeline";
import { runs, toolCalls, evaluations, auditLogs } from "../../data/mockData";

export function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const run = runs.find(r => r.run_id === id) ?? runs[0];
  const runTools = toolCalls.filter(tc => tc.run_id === run.run_id);
  const runEval = evaluations.find(e => e.run_id === run.run_id);
  const runAudit = auditLogs.filter(a => a.entity_id === run.run_id || runTools.some(tc => a.entity_id === tc.tool_call_id)).slice(0, 5);

  const childRuns = runs.filter(r => r.parent_run_id === run.run_id);
  const parentRun = run.parent_run_id ? runs.find(r => r.run_id === run.parent_run_id) : null;

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div
        className="rounded-xl p-5"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex items-center gap-3 mb-3">
          <h1 className="text-base font-semibold font-mono" style={{ color: "var(--mis-text)" }}>{run.run_id}</h1>
          <StatusBadge status={run.status} size="md" />
        </div>

        <div className="grid grid-cols-4 gap-4">
          {[
            { label: "Task", value: run.task_id },
            { label: "Agent", value: run.agent_id },
            { label: "Runtime", value: run.runtime_type },
            { label: "Model", value: run.model_name || "—" },
            { label: "Started", value: new Date(run.started_at).toLocaleTimeString() },
            { label: "Duration", value: run.duration_ms > 0 ? `${(run.duration_ms / 1000).toFixed(0)}s` : "In progress" },
            { label: "Trace ID", value: run.trace_id || "—" },
            { label: "Approval Required", value: run.approval_required ? "Yes" : "No" },
          ].map(({ label, value }) => (
            <div key={label}>
              <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{label}</div>
              <div className="text-xs mt-0.5 font-mono" style={{ color: "var(--mis-dim)" }}>{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Cost + Tokens */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { icon: <DollarSign size={14} />, label: "Cost", value: `$${run.cost_usd.toFixed(4)}`, color: "var(--mis-success)" },
          { icon: <Cpu size={14} />, label: "Input Tokens", value: run.input_tokens.toLocaleString(), color: "var(--mis-primary)" },
          { icon: <Cpu size={14} />, label: "Output Tokens", value: run.output_tokens.toLocaleString(), color: "var(--mis-cyan)" },
          { icon: <Clock size={14} />, label: "Reasoning Tokens", value: run.reasoning_tokens.toLocaleString(), color: "var(--mis-purple)" },
        ].map(({ icon, label, value, color }) => (
          <div
            key={label}
            className="rounded-xl p-4"
            style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
          >
            <div className="flex items-center gap-1.5 mb-1" style={{ color }}>
              {icon}
              <span className="text-[11px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{label}</span>
            </div>
            <div className="text-xl font-semibold" style={{ color: "var(--mis-text)" }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Delegation Graph */}
      {(parentRun || childRuns.length > 0) && (
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-xs font-semibold flex items-center gap-1.5 mb-4" style={{ color: "var(--mis-text)" }}>
            <GitBranch size={13} style={{ color: "var(--mis-cyan)" }} />
            Run Delegation Graph
          </div>
          <div className="flex flex-col items-center gap-2">
            {parentRun && (
              <>
                <div
                  className="px-4 py-2 rounded-lg text-xs text-center"
                  style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}
                >
                  <div className="font-mono font-medium" style={{ color: "var(--mis-text)" }}>{parentRun.run_id}</div>
                  <div style={{ color: "var(--mis-muted)" }}>{parentRun.agent_id} · parent</div>
                </div>
                <div className="w-px h-4" style={{ background: "var(--mis-border)" }} />
              </>
            )}
            <div
              className="px-5 py-2.5 rounded-lg text-xs text-center"
              style={{ background: "rgba(34,211,238,0.08)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
            >
              <div className="font-mono font-semibold">{run.run_id}</div>
              <div style={{ color: "var(--mis-dim)" }}>{run.agent_id} · current</div>
              {run.delegation_id && (
                <div className="text-[10px] mt-0.5" style={{ color: "var(--mis-muted)" }}>del: {run.delegation_id}</div>
              )}
            </div>
            {childRuns.map((child, i) => (
              <div key={child.run_id} className="flex flex-col items-center gap-2">
                <div className="w-px h-4" style={{ background: "var(--mis-border)" }} />
                <div
                  className="px-4 py-2 rounded-lg text-xs text-center"
                  style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}
                >
                  <div className="font-mono font-medium" style={{ color: "var(--mis-text)" }}>{child.run_id}</div>
                  <div style={{ color: "var(--mis-muted)" }}>{child.agent_id} · child {i + 1}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tool Calls */}
      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-text)" }}>Tool Calls ({runTools.length})</div>
        {runTools.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--mis-muted)" }}>No tool calls recorded.</p>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr style={{ color: "var(--mis-muted)" }}>
                {["Tool", "Category", "Target", "Risk", "Status", "Duration"].map(h => (
                  <th key={h} className="text-left pb-2 font-medium pr-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runTools.map(tc => (
                <tr key={tc.tool_call_id} style={{ color: "var(--mis-dim)" }}>
                  <td className="py-2 pr-3 font-medium" style={{ color: "var(--mis-text)" }}>{tc.tool_name}</td>
                  <td className="py-2 pr-3">{tc.tool_category}</td>
                  <td className="py-2 pr-3 text-[11px] max-w-32 truncate">{tc.target_resource}</td>
                  <td className="py-2 pr-3"><RiskBadge risk={tc.risk_level} /></td>
                  <td className="py-2 pr-3"><StatusBadge status={tc.status} /></td>
                  <td className="py-2 pr-3">
                    {tc.ended_at ? `${((new Date(tc.ended_at).getTime() - new Date(tc.started_at).getTime()) / 1000).toFixed(1)}s` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Error Panel */}
      {run.status === "failed" && run.error_message && (
        <div
          className="rounded-xl p-4"
          style={{ background: "rgba(248,113,113,0.06)", border: "1px solid rgba(248,113,113,0.2)" }}
        >
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={14} style={{ color: "#F87171" }} />
            <span className="text-xs font-semibold" style={{ color: "#F87171" }}>{run.error_type}</span>
          </div>
          <p className="text-xs" style={{ color: "var(--mis-dim)" }}>{run.error_message}</p>
        </div>
      )}

      {/* Evaluation */}
      {runEval && (
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>Evaluation Result</div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold" style={{ color: runEval.score >= 80 ? "var(--mis-success)" : "var(--mis-warning)" }}>
                {runEval.score}/100
              </span>
              <StatusBadge status={runEval.pass_fail} size="md" />
            </div>
          </div>
          <p className="text-xs" style={{ color: "var(--mis-dim)" }}>{runEval.notes}</p>
          <div className="text-[11px] mt-1" style={{ color: "var(--mis-muted)" }}>Evaluator: {runEval.evaluator_type}</div>
        </div>
      )}

      {/* Audit Timeline */}
      {runAudit.length > 0 && (
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-xs font-semibold mb-4" style={{ color: "var(--mis-text)" }}>Audit Timeline</div>
          <AuditTimeline logs={runAudit} />
        </div>
      )}
    </div>
  );
}
