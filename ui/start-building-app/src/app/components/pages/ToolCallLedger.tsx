import { useState } from "react";
import { Wrench } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { RiskBadge } from "../shared/RiskBadge";
import { toolCalls, agents } from "../../data/mockData";
import type { RiskLevel } from "../../data/mockData";

type RiskFilter = "all" | RiskLevel;

export function ToolCallLedger() {
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");

  const filtered = riskFilter === "all" ? toolCalls : toolCalls.filter(tc => tc.risk_level === riskFilter);

  const riskCounts = {
    low: toolCalls.filter(t => t.risk_level === "low").length,
    medium: toolCalls.filter(t => t.risk_level === "medium").length,
    high: toolCalls.filter(t => t.risk_level === "high").length,
    critical: toolCalls.filter(t => t.risk_level === "critical").length,
  };

  return (
    <div className="space-y-5 w-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>Tool Call Ledger</h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
            {toolCalls.length} tool calls · {toolCalls.filter(t => t.risk_level === "high" || t.risk_level === "critical").length} high-risk
          </p>
        </div>
      </div>

      {/* Risk filter */}
      <div className="flex gap-2 flex-wrap">
        {([["all", toolCalls.length, "var(--mis-dim)"], ["low", riskCounts.low, "var(--mis-success)"], ["medium", riskCounts.medium, "#FBBF24"], ["high", riskCounts.high, "var(--mis-warning)"], ["critical", riskCounts.critical, "#F87171"]] as const).map(([val, count, color]) => (
          <button
            key={val}
            onClick={() => setRiskFilter(val as RiskFilter)}
            className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg transition-all capitalize"
            style={{
              background: riskFilter === val ? `${color}18` : "var(--mis-surface)",
              color: riskFilter === val ? color : "var(--mis-dim)",
              border: `1px solid ${riskFilter === val ? `${color}30` : "var(--mis-border)"}`,
            }}
          >
            {val} <span className="opacity-60">({count})</span>
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-xl overflow-hidden" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
              {["Tool", "Category", "Agent", "Target Resource", "Risk", "Status", "Duration"].map(h => (
                <th key={h} className="text-left px-4 py-3 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((tc, i) => {
              const agent = agents.find(a => a.agent_id === tc.agent_id);
              const dur = tc.ended_at
                ? `${((new Date(tc.ended_at).getTime() - new Date(tc.started_at).getTime()) / 1000).toFixed(1)}s`
                : "—";
              return (
                <tr
                  key={tc.tool_call_id}
                  style={{
                    color: "var(--mis-dim)",
                    borderTop: i > 0 ? "1px solid var(--mis-border)" : "none",
                    background: tc.risk_level === "high" ? "rgba(231,111,81,0.03)" : "transparent",
                  }}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <Wrench size={11} style={{ color: "var(--mis-muted)" }} />
                      <span className="font-medium" style={{ color: "var(--mis-text)" }}>{tc.tool_name}</span>
                    </div>
                    <div className="text-[10px] mt-0.5 font-mono" style={{ color: "var(--mis-muted)" }}>{tc.run_id}</div>
                  </td>
                  <td className="px-4 py-3">{tc.tool_category}</td>
                  <td className="px-4 py-3">{agent?.name ?? tc.agent_id}</td>
                  <td className="px-4 py-3 max-w-[140px]">
                    <span className="truncate block text-[11px]">{tc.target_resource}</span>
                  </td>
                  <td className="px-4 py-3"><RiskBadge risk={tc.risk_level} /></td>
                  <td className="px-4 py-3"><StatusBadge status={tc.status} /></td>
                  <td className="px-4 py-3">{dur}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
