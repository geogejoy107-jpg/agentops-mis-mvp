"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, Bot, Brain, CheckCircle2, Database, DollarSign, Download, RefreshCw, ServerCog, ShieldCheck } from "lucide-react";
import { loadWorkspaceSnapshot, type WorkspaceSnapshot } from "@/lib/mis";
import { AppFrame } from "./AppFrame";

function formatNumber(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num.toLocaleString() : "0";
}

function statusClass(status?: string) {
  if (["completed", "approved", "healthy", "ready", "configured", "pass"].includes(status || "")) return "status statusGood";
  if (["failed", "blocked", "rejected", "unavailable"].includes(status || "")) return "status statusBad";
  if (["running", "waiting_approval", "pending", "attention", "warn"].includes(status || "")) return "status statusWarn";
  return "status";
}

function percent(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? `${Math.round(num * 100)}%` : "0%";
}

function money(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? `$${num.toFixed(2)}` : "$0.00";
}

function metricDisplay(value: unknown) {
  return typeof value === "string" ? value : formatNumber(value);
}

export function WorkspaceDashboard() {
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await loadWorkspaceSnapshot());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const activeTasks = useMemo(
    () => (snapshot?.tasks || []).filter((task) => task.status !== "completed").slice(0, 5),
    [snapshot?.tasks],
  );
  const metrics = snapshot?.metrics || {};
  const recentRuns = snapshot?.runs || metrics.recent_runs || [];
  const runtimeHealth = metrics.runtime_health || [];
  const readyRuntimes = runtimeHealth.filter((row) => ["ready", "configured", "healthy"].includes(String(row.status || ""))).length;
  const taskStatus = metrics.task_status_distribution || [];
  const topCostAgents = metrics.top_cost_agents || [];
  const openclaw = metrics.openclaw_import || {};

  return (
    <AppFrame>
        <header className="topbar" data-smoke="control-tower-route">
          <div>
            <p className="eyebrow">Commercial migration</p>
            <h1>Workspace control plane</h1>
            <p className="subtle">Next control tower split across cockpit, governance, and BYOC deployment evidence.</p>
          </div>
          <div className="rowActions">
            <Link className="miniButton" href="/workspace/agents">Agents</Link>
            <Link className="miniButton" href="/workspace/governance">Governance</Link>
            <Link className="miniButton" href="/workspace/deployment">Deployment</Link>
            <Link className="miniButton" href="/workspace/workers">Workers</Link>
          </div>
          <button className="iconButton" onClick={refresh} disabled={loading} aria-label="Refresh workspace snapshot">
            <RefreshCw size={17} className={loading ? "spin" : ""} />
          </button>
        </header>

        {error ? (
          <div className="banner error">
            Next.js can load, but MIS API is unavailable through <code>/api/mis/*</code>: {error}
          </div>
        ) : null}

        <section className="metrics six" data-smoke="control-tower-live-metrics">
          {[
            ["Agents", metrics.agents_total, <Bot key="agents" size={18} />, "ready"],
            ["Running", metrics.agents_running, <Activity key="running" size={18} />, "running"],
            ["Completed Tasks", metrics.tasks_completed_total, <CheckCircle2 key="tasks" size={18} />, "completed"],
            ["Pending Approvals", metrics.pending_approvals, <ShieldCheck key="approvals" size={18} />, "pending"],
            ["Memory Due", metrics.stale_or_due_memories, <Brain key="memory" size={18} />, "attention"],
            ["Failure Rate", percent(metrics.failure_rate), <AlertTriangle key="failure" size={18} />, Number(metrics.failure_rate || 0) ? "attention" : "ready"],
            ["Total Cost", money(metrics.total_cost_usd), <DollarSign key="cost" size={18} />, "ready"],
            ["Runtime Health", `${readyRuntimes}/${runtimeHealth.length || 0}`, <ServerCog key="runtime" size={18} />, readyRuntimes ? "ready" : "attention"],
          ].map(([label, value, icon, status]) => (
            <div className="metric" key={String(label)}>
              <span className="metricIcon">{icon}</span>
              <span>{label}</span>
              <strong>{loading && !snapshot ? "..." : metricDisplay(value)}</strong>
              <span className={statusClass(String(status))}>{String(status)}</span>
            </div>
          ))}
        </section>

        <section className="panel wide" data-smoke="control-tower-split-proof">
          <div className="panelHeader">
            <h2>Control Tower split proof</h2>
            <span>Vite /admin remains canonical until explicit retirement</span>
          </div>
          <div className="proofStrip">
            <span>/dashboard/metrics cockpit readback</span>
            <span>/workspace/agents agent performance drilldown</span>
            <span>/workspace/governance production and session governance</span>
            <span>/workspace/deployment BYOC storage and recovery gates</span>
            <span>Agent Gateway CLI/API/MCP unchanged</span>
            <span>route retirement blocked</span>
          </div>
        </section>

        <section className="grid">
          <div className="panel">
            <div className="panelHeader">
              <h2>Active tasks</h2>
              <span>{activeTasks.length} visible</span>
            </div>
            <div className="list">
              {activeTasks.length ? activeTasks.map((task) => (
                <article className="row" key={task.task_id}>
                  <div>
                    <strong>{task.title}</strong>
                    <span>{task.task_id} · {task.owner_agent_id || "unassigned"}</span>
                  </div>
                  <span className={statusClass(task.status)}>{task.status}</span>
                </article>
              )) : <p className="empty">No active task data loaded yet.</p>}
            </div>
          </div>

          <div className="panel">
            <div className="panelHeader">
              <h2>Recent runs</h2>
              <span>{recentRuns.length} visible</span>
            </div>
            <div className="list">
              {recentRuns.length ? recentRuns.slice(0, 6).map((run) => (
                <article className="row" key={run.run_id}>
                  <div>
                    <strong>{run.run_id}</strong>
                    <span>{run.runtime_type || "runtime"} · {run.agent_id || "agent"}</span>
                  </div>
                  <span className={statusClass(run.status)}>{run.status}</span>
                </article>
              )) : <p className="empty">No run data loaded yet.</p>}
            </div>
          </div>
        </section>

        <section className="panel wide">
          <div className="panelHeader">
            <h2>Pending approval queue</h2>
            <span>{snapshot?.approvals.length || 0} pending</span>
          </div>
          <div className="approvalGrid">
            {(snapshot?.approvals || []).length ? snapshot?.approvals.map((approval) => (
              <article className="approval" key={approval.approval_id}>
                <strong>{approval.approval_id}</strong>
                <span>{approval.reason || approval.task_id || approval.run_id || "approval required"}</span>
              </article>
            )) : <p className="empty">Approval queue is empty or not loaded.</p>}
          </div>
        </section>

        <section className="grid">
          <div className="panel" data-smoke="control-tower-runtime-health">
            <div className="panelHeader">
              <h2><ServerCog size={14} /> Runtime health</h2>
              <span>{readyRuntimes}/{runtimeHealth.length || 0} ready</span>
            </div>
            <div className="list compactList">
              {runtimeHealth.length ? runtimeHealth.map((runtime) => (
                <article className="row" key={runtime.provider || "runtime"}>
                  <div>
                    <strong>{runtime.provider || "runtime"}</strong>
                    <span>{runtime.detail || runtime.last_error || "status read from /dashboard/metrics"}</span>
                  </div>
                  <span className={statusClass(runtime.status)}>{runtime.status || "unknown"}</span>
                </article>
              )) : <p className="empty">No runtime health rows loaded.</p>}
            </div>
          </div>

          <div className="panel" data-smoke="control-tower-openclaw-imports">
            <div className="panelHeader">
              <h2><Download size={14} /> OpenClaw import readback</h2>
              <span>/dashboard/metrics</span>
            </div>
            <div className="miniMetrics">
              <span>agents <strong>{formatNumber(openclaw.agents)}</strong></span>
              <span>cron jobs <strong>{formatNumber(openclaw.cron_jobs)}</strong></span>
              <span>enabled <strong>{formatNumber(openclaw.enabled_cron_jobs)}</strong></span>
              <span>runs <strong>{formatNumber(openclaw.cron_runs)}</strong></span>
              <span>tasks <strong>{formatNumber(openclaw.cron_tasks)}</strong></span>
            </div>
          </div>
        </section>

        <section className="grid">
          <div className="panel" data-smoke="control-tower-task-status">
            <div className="panelHeader">
              <h2><Database size={14} /> Task status distribution</h2>
              <span>{taskStatus.length} statuses</span>
            </div>
            <div className="list compactList">
              {taskStatus.length ? taskStatus.map((row) => (
                <article className="row" key={row.status || "unknown"}>
                  <div>
                    <strong>{row.status || "unknown"}</strong>
                    <span>live count from dashboard metrics</span>
                  </div>
                  <span className={statusClass(row.status)}>{formatNumber(row.count)}</span>
                </article>
              )) : <p className="empty">No task status rows loaded.</p>}
            </div>
          </div>

          <div className="panel" data-smoke="control-tower-cost-leaders">
            <div className="panelHeader">
              <h2><DollarSign size={14} /> Cost leaders</h2>
              <span>{topCostAgents.length} agents</span>
            </div>
            <div className="list compactList">
              {topCostAgents.length ? topCostAgents.map((agent) => (
                <article className="row" key={agent.agent_id || agent.name || "agent"}>
                  <div>
                    <strong>{agent.name || agent.agent_id || "agent"}</strong>
                    <span>{agent.agent_id || "agent id unavailable"}</span>
                  </div>
                  <span>{money(agent.cost_usd)}</span>
                </article>
              )) : <p className="empty">No cost leader rows loaded.</p>}
            </div>
          </div>
        </section>
    </AppFrame>
  );
}
