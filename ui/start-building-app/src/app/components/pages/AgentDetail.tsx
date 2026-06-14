import { useParams } from "react-router";
import { Bot, Cpu, DollarSign, ShieldCheck, Activity, Star } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { RiskBadge } from "../shared/RiskBadge";
import { agents, runs, evaluations } from "../../data/mockData";

const HIGH_RISK_TOOLS = ["shell.exec", "github.push", "email.send", "file.delete", "database.write", "mcp.invoke"];

export function AgentDetail() {
  const { id } = useParams<{ id: string }>();
  const agent = agents.find(a => a.agent_id === id) ?? agents[0];
  const agentRuns = runs.filter(r => r.agent_id === agent.agent_id).slice(0, 5);
  const agentEvals = evaluations.filter(e => e.agent_id === agent.agent_id);
  const avgScore = agentEvals.length
    ? Math.round(agentEvals.reduce((s, e) => s + e.score, 0) / agentEvals.length)
    : null;

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div
        className="rounded-xl p-5 flex items-start gap-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div
          className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)" }}
        >
          <Bot size={22} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{agent.name}</h1>
            <StatusBadge status={agent.status} size="md" />
          </div>
          <div className="text-xs mt-1" style={{ color: "var(--mis-dim)" }}>{agent.description}</div>
          <div className="flex gap-4 mt-2 flex-wrap">
            {[
              { label: "Role", value: agent.role },
              { label: "Runtime", value: agent.runtime_type },
              { label: "Model", value: `${agent.model_provider}/${agent.model_name}` },
              { label: "Permission", value: agent.permission_level },
            ].map(({ label, value }) => (
              <div key={label}>
                <span className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{label}</span>
                <div className="text-xs font-medium" style={{ color: "var(--mis-dim)" }}>{value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Stats */}
        <div
          className="rounded-xl p-4 space-y-3"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>Performance</div>
          {[
            { label: "Total Runs", value: agent.run_count, icon: <Activity size={13} /> },
            { label: "Success Rate", value: `${Math.round(agent.success_rate * 100)}%`, icon: <Star size={13} /> },
            { label: "Failures", value: agent.failure_count, icon: <Activity size={13} /> },
            { label: "Approvals Requested", value: agent.approval_count, icon: <ShieldCheck size={13} /> },
          ].map(({ label, value, icon }) => (
            <div key={label} className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--mis-dim)" }}>
                <span style={{ color: "var(--mis-muted)" }}>{icon}</span>
                {label}
              </div>
              <span className="text-xs font-medium" style={{ color: "var(--mis-text)" }}>{value}</span>
            </div>
          ))}
          {avgScore !== null && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--mis-dim)" }}>
                <Star size={13} style={{ color: "var(--mis-muted)" }} />
                Avg Eval Score
              </div>
              <span className="text-xs font-semibold" style={{ color: avgScore >= 80 ? "var(--mis-success)" : "var(--mis-warning)" }}>
                {avgScore}/100
              </span>
            </div>
          )}
        </div>

        {/* Budget */}
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-xs font-semibold mb-3 flex items-center gap-1.5" style={{ color: "var(--mis-text)" }}>
            <DollarSign size={13} style={{ color: "var(--mis-success)" }} />
            Budget
          </div>
          <div className="text-2xl font-semibold" style={{ color: "var(--mis-text)" }}>
            ${agent.budget_used_usd.toFixed(2)}
          </div>
          <div className="text-xs" style={{ color: "var(--mis-muted)" }}>
            of ${agent.budget_limit_usd.toFixed(2)} limit
          </div>
          <div className="mt-3 rounded-full h-2 overflow-hidden" style={{ background: "var(--mis-border)" }}>
            <div
              className="h-2 rounded-full transition-all"
              style={{
                width: `${Math.min(100, (agent.budget_used_usd / agent.budget_limit_usd) * 100)}%`,
                background: agent.budget_used_usd / agent.budget_limit_usd > 0.8 ? "var(--mis-warning)" : "var(--mis-success)",
              }}
            />
          </div>
          <div className="text-[11px] mt-1.5" style={{ color: "var(--mis-muted)" }}>
            {Math.round((agent.budget_used_usd / agent.budget_limit_usd) * 100)}% used
          </div>
        </div>

        {/* Allowed Tools */}
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-xs font-semibold mb-3 flex items-center gap-1.5" style={{ color: "var(--mis-text)" }}>
            <Cpu size={13} style={{ color: "var(--mis-primary)" }} />
            Allowed Tools
          </div>
          <div className="space-y-1.5">
            {agent.allowed_tools.map(tool => {
              const isHighRisk = HIGH_RISK_TOOLS.includes(tool);
              return (
                <div key={tool} className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: "var(--mis-dim)" }}>{tool}</span>
                  {isHighRisk && <RiskBadge risk="high" />}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Recent Runs */}
      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-text)" }}>Recent Runs</div>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: "var(--mis-muted)" }}>
              {["Run ID", "Task", "Status", "Cost", "Tokens", "Duration"].map(h => (
                <th key={h} className="text-left pb-2 font-medium pr-4">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {agentRuns.map(run => (
              <tr key={run.run_id} style={{ color: "var(--mis-dim)" }}>
                <td className="py-2 pr-4 font-mono text-[11px]">{run.run_id}</td>
                <td className="py-2 pr-4 text-[11px]">{run.task_id}</td>
                <td className="py-2 pr-4"><StatusBadge status={run.status} /></td>
                <td className="py-2 pr-4">${run.cost_usd.toFixed(3)}</td>
                <td className="py-2 pr-4">{run.input_tokens + run.output_tokens}</td>
                <td className="py-2 pr-4">{run.duration_ms > 0 ? `${(run.duration_ms / 1000).toFixed(0)}s` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
