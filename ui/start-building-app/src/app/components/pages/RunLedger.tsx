import { Link } from "react-router";
import { Clock, List, RefreshCw } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { loadRuns, useLiveData } from "../../data/liveApi";
import { pick, usePreferences } from "../../context/PreferencesContext";

export function RunLedger() {
  const { locale } = usePreferences();
  const { data: runs, loading, error, refresh } = useLiveData(() => loadRuns(), []);
  const rows = runs || [];
  const copy = pick(locale, {
    en: {
      title: "Run Ledger",
      summary: `${rows.length} live runs from AgentOps MIS SQLite ledger`,
      loading: "Loading live runs...",
      backendUnavailable: "Live backend unavailable",
      refresh: "Refresh",
      empty: "No live runs loaded.",
      headers: ["Run", "Status", "Agent", "Runtime", "Duration", "Summary", "Created"],
    },
    zh: {
      title: "运行账本",
      summary: `${rows.length} 条来自 AgentOps MIS SQLite 账本的运行记录`,
      loading: "正在加载实时运行记录...",
      backendUnavailable: "本地后端不可用",
      refresh: "刷新",
      empty: "暂无实时运行记录。",
      headers: ["运行", "状态", "代理", "运行时", "耗时", "摘要", "创建时间"],
    },
  });

  return (
    <div className="space-y-5 w-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
            {copy.summary}
          </p>
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
            {rows.slice(0, 120).map((run, i) => (
              <tr key={run.run_id} style={{ color: "var(--mis-dim)", borderTop: i > 0 ? "1px solid var(--mis-border)" : "none" }}>
                <td className="px-4 py-3">
                  <Link to={`/workspace/runs/${run.run_id}`} className="font-mono font-medium hover:opacity-80" style={{ color: "var(--mis-cyan)" }}>
                    {run.run_id}
                  </Link>
                </td>
                <td className="px-4 py-3"><StatusBadge status={run.status} /></td>
                <td className="px-4 py-3 font-mono text-[11px]">{run.agent_id}</td>
                <td className="px-4 py-3">{run.runtime_type}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center gap-1">
                    <Clock size={11} />
                    {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : "—"}
                  </span>
                </td>
                <td className="px-4 py-3 max-w-xs truncate">{run.output_summary || run.error_message || run.input_summary || "—"}</td>
                <td className="px-4 py-3 text-[11px]" style={{ color: "var(--mis-muted)" }}>
                  {run.created_at ? new Date(run.created_at).toLocaleString(locale === "zh" ? "zh-CN" : "en-US") : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className="py-12 text-center" style={{ color: "var(--mis-muted)" }}>
            <List size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-sm">{copy.empty}</p>
          </div>
        )}
      </div>
    </div>
  );
}
