import { useState } from "react";
import { Link } from "react-router";
import { RefreshCw, Wrench } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { RiskBadge } from "../shared/RiskBadge";
import { loadAgents, loadDashboard, loadToolCalls, useLiveData } from "../../data/liveApi";
import { pick, usePreferences } from "../../context/PreferencesContext";
import type { RiskLevel } from "../../data/mockData";

type RiskFilter = "all" | RiskLevel;

export function ToolCallLedger() {
  const { locale } = usePreferences();
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const { data, loading, error, refresh } = useLiveData(async () => {
    const metrics = await loadDashboard();
    const [toolCalls, agents] = await Promise.all([loadToolCalls(), loadAgents(metrics)]);
    return { toolCalls, agents };
  }, []);
  const toolCalls = data?.toolCalls || [];
  const agents = data?.agents || [];
  const filtered = riskFilter === "all" ? toolCalls : toolCalls.filter(tc => tc.risk_level === riskFilter);
  const highRiskCount = toolCalls.filter(t => t.risk_level === "high" || t.risk_level === "critical").length;
  const zh = locale === "zh";

  const copy = pick(locale, {
    en: {
      title: "Tool Call Ledger",
      summary: `${toolCalls.length} live tool calls · ${highRiskCount} high-risk`,
      loading: "Loading live tool calls...",
      backendUnavailable: "Live backend unavailable",
      refresh: "Refresh",
      headers: ["Tool", "Category", "Agent", "Target Resource", "Risk", "Status", "Duration"],
      empty: "No live tool calls recorded.",
      filters: { all: "all", low: "low", medium: "medium", high: "high", critical: "critical" },
    },
    zh: {
      title: "工具调用账本",
      summary: `${toolCalls.length} 条实时工具调用 · ${highRiskCount} 条高风险`,
      loading: "正在加载实时工具调用...",
      backendUnavailable: "本地后端不可用",
      refresh: "刷新",
      headers: ["工具", "类别", "代理", "目标资源", "风险", "状态", "耗时"],
      empty: "暂无实时工具调用记录。",
      filters: { all: "全部", low: "低", medium: "中", high: "高", critical: "严重" },
    },
  });

  const riskCounts = {
    low: toolCalls.filter(t => t.risk_level === "low").length,
    medium: toolCalls.filter(t => t.risk_level === "medium").length,
    high: toolCalls.filter(t => t.risk_level === "high").length,
    critical: toolCalls.filter(t => t.risk_level === "critical").length,
  };

  return (
    <div className="space-y-5 w-full">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>{copy.summary}</p>
          {loading && <p className="text-xs mt-2" style={{ color: "var(--mis-muted)" }}>{copy.loading}</p>}
          {error && <p className="text-xs mt-2" style={{ color: "#F87171" }}>{copy.backendUnavailable}: {error}</p>}
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded"
          style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
        >
          <RefreshCw size={13} />
          {copy.refresh}
        </button>
      </div>

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
            {copy.filters[val]} <span className="opacity-60">({count})</span>
          </button>
        ))}
      </div>

      <div className="rounded-xl overflow-hidden" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
              {copy.headers.map(h => (
                <th key={h} className="text-left px-4 py-3 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 160).map((tc, i) => {
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
                    <Link to={`/workspace/runs/${tc.run_id}`} className="text-[10px] mt-0.5 font-mono hover:opacity-80" style={{ color: "var(--mis-cyan)" }}>{tc.run_id}</Link>
                  </td>
                  <td className="px-4 py-3">{tc.tool_category}</td>
                  <td className="px-4 py-3">{agent?.name ?? tc.agent_id}</td>
                  <td className="px-4 py-3 max-w-[140px]">
                    <span className="truncate block text-[11px]">{tc.target_resource || "—"}</span>
                  </td>
                  <td className="px-4 py-3"><RiskBadge risk={tc.risk_level} label={zh ? ({ low: "低", medium: "中", high: "高", critical: "严重" }[tc.risk_level]) : undefined} /></td>
                  <td className="px-4 py-3"><StatusBadge status={tc.status} /></td>
                  <td className="px-4 py-3">{dur}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && !loading && (
          <div className="py-12 text-center" style={{ color: "var(--mis-muted)" }}>
            <Wrench size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-sm">{copy.empty}</p>
          </div>
        )}
      </div>
    </div>
  );
}
