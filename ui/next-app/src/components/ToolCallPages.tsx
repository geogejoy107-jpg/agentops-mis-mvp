"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Filter, RefreshCw, Wrench } from "lucide-react";
import { AppFrame } from "./AppFrame";
import { isHumanSessionUnauthorized, loadToolCalls, setActiveWorkspaceId, type ToolCallSummary } from "@/lib/mis";

type LoadState<T> = {
  data: T;
  error: string | null;
  loading: boolean;
};

function statusClass(status?: string) {
  const normalized = status || "unknown";
  if (["completed", "approved"].includes(normalized)) return "status statusGood";
  if (["failed", "blocked", "rejected"].includes(normalized)) return "status statusBad";
  if (["running", "waiting_approval", "pending"].includes(normalized)) return "status statusWarn";
  return "status";
}

function riskClass(risk?: string) {
  const normalized = risk || "unknown";
  if (["critical", "high"].includes(normalized)) return "status statusBad";
  if (normalized === "medium") return "status statusWarn";
  if (normalized === "low") return "status statusGood";
  return "status";
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function durationSeconds(toolCall: ToolCallSummary) {
  if (!toolCall.started_at || !toolCall.ended_at) return "-";
  const started = new Date(toolCall.started_at).getTime();
  const ended = new Date(toolCall.ended_at).getTime();
  if (Number.isNaN(started) || Number.isNaN(ended) || ended < started) return "-";
  return `${((ended - started) / 1000).toFixed(1)}s`;
}

export function ToolCallsParityPage() {
  const [riskFilter, setRiskFilter] = useState("all");
  const [sessionRequired, setSessionRequired] = useState(false);
  const [state, setState] = useState<LoadState<ToolCallSummary[]>>({ data: [], error: null, loading: true });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    setSessionRequired(false);
    try {
      setState({ data: await loadToolCalls(), error: null, loading: false });
    } catch (err) {
      if (isHumanSessionUnauthorized(err)) {
        setActiveWorkspaceId("");
        setSessionRequired(true);
        setState({ data: [], error: null, loading: false });
        return;
      }
      setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const counts = useMemo(() => {
    const byRisk = new Map<string, number>();
    const byStatus = new Map<string, number>();
    for (const toolCall of state.data) {
      const risk = toolCall.risk_level || "unknown";
      const status = toolCall.status || "unknown";
      byRisk.set(risk, (byRisk.get(risk) || 0) + 1);
      byStatus.set(status, (byStatus.get(status) || 0) + 1);
    }
    return { byRisk, byStatus };
  }, [state.data]);

  const filtered = riskFilter === "all" ? state.data : state.data.filter((toolCall) => (toolCall.risk_level || "unknown") === riskFilter);
  const highRiskCount = (counts.byRisk.get("high") || 0) + (counts.byRisk.get("critical") || 0);
  const riskFilters = ["all", "low", "medium", "high", "critical", "unknown"];

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Next.js parity route</p>
          <h1>Tool Call Ledger</h1>
          <p className="subtle">
            {state.data.length} tool calls · {highRiskCount} high-risk · {counts.byStatus.get("completed") || 0} completed
          </p>
        </div>
        <button className="iconButton" onClick={refresh} disabled={state.loading} aria-label="Refresh tool call ledger">
          <RefreshCw size={17} className={state.loading ? "spin" : ""} />
        </button>
      </header>

      {sessionRequired ? (
        <div className="banner error">Human Session required. <Link className="backLink" href="/workspace">Sign in</Link></div>
      ) : null}
      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/tool-calls: {state.error}</div> : null}

      <div className="filterBar">
        {riskFilters.map((risk) => (
          <button className={`filterChip ${riskFilter === risk ? "active" : ""}`} key={risk} onClick={() => setRiskFilter(risk)}>
            {risk}
            <span>{risk === "all" ? state.data.length : counts.byRisk.get(risk) || 0}</span>
          </button>
        ))}
      </div>

      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th>Tool</th>
              <th>Risk</th>
              <th>Status</th>
              <th>Run</th>
              <th>Agent</th>
              <th>Target</th>
              <th>Duration</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 160).map((toolCall) => (
              <tr key={toolCall.tool_call_id}>
                <td>
                  <strong>{toolCall.tool_name || "unknown tool"}</strong>
                  <span>{toolCall.tool_call_id} · {toolCall.tool_category || "custom"}</span>
                </td>
                <td><span className={riskClass(toolCall.risk_level)}>{toolCall.risk_level || "unknown"}</span></td>
                <td><span className={statusClass(toolCall.status)}>{toolCall.status || "unknown"}</span></td>
                <td className="mono">
                  {toolCall.run_id ? (
                    <Link className="tableLink" href={`/workspace/runs/${encodeURIComponent(toolCall.run_id)}`}>
                      {toolCall.run_id}
                    </Link>
                  ) : "-"}
                </td>
                <td className="mono">{toolCall.agent_id || "-"}</td>
                <td>{toolCall.target_resource || "-"}</td>
                <td>{durationSeconds(toolCall)}</td>
                <td>{formatDate(toolCall.started_at || toolCall.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length && !state.loading ? (
          <div className="emptyState">
            <Filter size={24} />
            <p>No tool calls match this risk filter.</p>
          </div>
        ) : null}
        {state.loading ? (
          <div className="emptyState">
            <Wrench size={24} />
            <p>Loading live tool calls...</p>
          </div>
        ) : null}
      </div>
    </AppFrame>
  );
}
