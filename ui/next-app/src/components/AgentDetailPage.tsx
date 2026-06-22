"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Activity, Bot, Cpu, DollarSign, RefreshCw, ShieldCheck, Star } from "lucide-react";
import { AppFrame } from "./AppFrame";
import { loadAgentPerformance, type AgentPerformancePayload } from "@/lib/mis";

type LoadState = {
  data: AgentPerformancePayload | null;
  error: string | null;
  loading: boolean;
};

const HIGH_RISK_TOOLS = new Set(["shell.exec", "github.push", "email.send", "file.delete", "database.write", "mcp.invoke"]);

function statusClass(status?: string) {
  if (["completed", "approved", "ready", "running", "idle"].includes(status || "")) return "status statusGood";
  if (["failed", "blocked", "rejected", "error", "disabled"].includes(status || "")) return "status statusBad";
  if (["waiting_approval", "pending", "paused"].includes(status || "")) return "status statusWarn";
  return "status";
}

function numberValue(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num : 0;
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function parseTools(value: unknown) {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.map(String);
    } catch {
      return value.split(",").map((item) => item.trim()).filter(Boolean);
    }
  }
  return [];
}

export function AgentDetailParityPage({ agentId }: Readonly<{ agentId: string }>) {
  const [state, setState] = useState<LoadState>({ data: null, error: null, loading: true });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      setState({ data: await loadAgentPerformance(agentId), error: null, loading: false });
    } catch (err) {
      setState({ data: null, error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    void refresh();
  }, [agentId]);

  const agent = state.data?.agent;
  const tools = useMemo(() => parseTools(agent?.allowed_tools), [agent?.allowed_tools]);
  const totalRuns = numberValue(state.data?.total_runs);
  const completedRuns = numberValue(state.data?.completed_runs);
  const failures = numberValue(state.data?.failures);
  const successRate = Math.round(numberValue(state.data?.success_rate) * 100);
  const totalCost = numberValue(state.data?.total_cost_usd);
  const budgetLimit = numberValue(agent?.budget_limit_usd);
  const budgetUsedPct = budgetLimit ? Math.min(100, Math.round((totalCost / budgetLimit) * 100)) : 0;

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Next.js parity route</p>
          <h1>Agent Detail</h1>
          <p className="subtle">
            Per-agent performance · {agent?.name || agentId} · {agent?.runtime_type || "runtime"} · {agent?.permission_level || "permission unknown"}
          </p>
        </div>
        <button className="iconButton" onClick={refresh} disabled={state.loading} aria-label="Refresh agent detail">
          <RefreshCw size={17} className={state.loading ? "spin" : ""} />
        </button>
      </header>

      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/agents/{agentId}/performance: {state.error}</div> : null}

      <section className="panel wide">
        <div className="panelHeader">
          <div>
            <h2><Bot size={14} /> {agent?.name || agentId}</h2>
            <span>{agent?.description || "Live agent detail loaded from MIS performance API."}</span>
          </div>
          <span className={statusClass(agent?.status)}>{agent?.status || "loading"}</span>
        </div>
        <div className="miniMetrics">
          <span>agent <strong>{agent?.agent_id || agentId}</strong></span>
          <span>role <strong>{agent?.role || "-"}</strong></span>
          <span>model <strong>{agent?.model_provider || "-"}/{agent?.model_name || "-"}</strong></span>
          <span>owner <strong>{agent?.owner_user_id || "-"}</strong></span>
        </div>
      </section>

      <section className="metricGrid">
        <article className="metric">
          <span><Activity size={15} />Total Runs</span>
          <strong>{totalRuns}</strong>
          <small>{completedRuns} completed</small>
        </article>
        <article className="metric">
          <span><Star size={15} />Success Rate</span>
          <strong>{successRate}%</strong>
          <small>{failures} failures or blocked runs</small>
        </article>
        <article className="metric">
          <span><ShieldCheck size={15} />Approvals Requested</span>
          <strong>{numberValue(state.data?.approval_required_count)}</strong>
          <small>high-risk or gated work</small>
        </article>
      </section>

      <div className="grid">
        <section className="panel">
          <div className="panelHeader">
            <div>
              <h2><DollarSign size={14} /> Budget</h2>
              <span>cost evidence from recent ledger runs</span>
            </div>
            <span className={statusClass(budgetUsedPct > 80 ? "waiting_approval" : "ready")}>{budgetUsedPct}% used</span>
          </div>
          <p className="subtle">${totalCost.toFixed(3)} of ${budgetLimit.toFixed(2)} limit</p>
          <div className="progressTrack">
            <span style={{ width: `${budgetUsedPct}%` }} />
          </div>
          <div className="miniMetrics">
            <span>avg duration <strong>{numberValue(state.data?.avg_duration_ms)} ms</strong></span>
            <span>runtime <strong>{agent?.runtime_type || "-"}</strong></span>
          </div>
        </section>

        <section className="panel">
          <div className="panelHeader">
            <div>
              <h2><Cpu size={14} /> Allowed Tools</h2>
              <span>high-risk tools are visibly marked</span>
            </div>
            <span className="status">{tools.length} tools</span>
          </div>
          <div className="miniMetrics">
            {tools.map((tool) => (
              <span className={HIGH_RISK_TOOLS.has(tool) ? "status statusBad" : "metaPill"} key={tool}>
                {tool}{HIGH_RISK_TOOLS.has(tool) ? " high-risk" : ""}
              </span>
            ))}
            {!tools.length ? <span className="metaPill">No tools loaded</span> : null}
          </div>
        </section>
      </div>

      <div className="tableWrap">
        <div className="panelHeader">
          <div>
            <h2>Recent Runs</h2>
            <span>run and task evidence for this agent</span>
          </div>
          <span className="status">{state.data?.recent_runs?.length || 0} runs</span>
        </div>
        <table className="dataTable">
          <thead>
            <tr>
              <th>Run</th>
              <th>Task</th>
              <th>Status</th>
              <th>Cost</th>
              <th>Tokens</th>
              <th>Duration</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {(state.data?.recent_runs || []).map((run) => (
              <tr key={run.run_id}>
                <td className="mono">
                  <Link className="tableLink" href={`/workspace/runs/${encodeURIComponent(run.run_id)}`}>
                    {run.run_id}
                  </Link>
                </td>
                <td className="mono">
                  {run.task_id ? (
                    <Link className="tableLink" href={`/workspace/tasks/${encodeURIComponent(run.task_id)}`}>
                      {run.task_id}
                    </Link>
                  ) : "-"}
                </td>
                <td><span className={statusClass(run.status)}>{run.status || "unknown"}</span></td>
                <td>${numberValue(run.cost_usd).toFixed(3)}</td>
                <td>{numberValue((run as { input_tokens?: number }).input_tokens) + numberValue((run as { output_tokens?: number }).output_tokens)}</td>
                <td>{numberValue(run.duration_ms) > 0 ? `${(numberValue(run.duration_ms) / 1000).toFixed(1)}s` : "-"}</td>
                <td>{formatDate(run.started_at || run.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {state.loading ? <p className="empty tableEmpty">Loading agent performance detail...</p> : null}
        {!state.loading && !(state.data?.recent_runs || []).length ? <p className="empty tableEmpty">No recent runs loaded for this agent.</p> : null}
      </div>

      <section className="panel wide">
        <div className="panelHeader">
          <div>
            <h2>Recent error types</h2>
            <span>failure evidence grouped by backend performance read model</span>
          </div>
          <span className="status">{state.data?.recent_error_types?.length || 0} groups</span>
        </div>
        <div className="list compact">
          {(state.data?.recent_error_types || []).map((item) => (
            <article className="row" key={item.error_type || "error"}>
              <div>
                <strong>{item.error_type || "unknown"}</strong>
                <span>recent failures for {agent?.agent_id || agentId}</span>
              </div>
              <span className="metaPill">{numberValue(item.count)} runs</span>
            </article>
          ))}
          {!(state.data?.recent_error_types || []).length ? <p className="empty">No recent error groups loaded.</p> : null}
        </div>
      </section>
    </AppFrame>
  );
}
