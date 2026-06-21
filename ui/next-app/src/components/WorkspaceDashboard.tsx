"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, Bot, CheckCircle2, Database, RefreshCw, ShieldCheck, Workflow } from "lucide-react";
import { loadWorkspaceSnapshot, type WorkspaceSnapshot } from "@/lib/mis";

function formatNumber(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num.toLocaleString() : "0";
}

function statusClass(status: string) {
  if (["completed", "approved", "healthy", "ready"].includes(status)) return "status statusGood";
  if (["failed", "blocked", "rejected"].includes(status)) return "status statusBad";
  if (["running", "waiting_approval", "pending"].includes(status)) return "status statusWarn";
  return "status";
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
  const recentRuns = snapshot?.runs || snapshot?.metrics.recent_runs || [];

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark">A</span>
          <div>
            <strong>AgentOps MIS</strong>
            <span>Next.js parity track</span>
          </div>
        </div>
        <nav className="nav">
          <a className="navItem active" href="/workspace"><Activity size={16} />Workspace</a>
          <a className="navItem" href="/workspace"><Workflow size={16} />Runs</a>
          <a className="navItem" href="/workspace"><Bot size={16} />Workers</a>
          <a className="navItem" href="/workspace"><Database size={16} />Ledger</a>
          <a className="navItem" href="/workspace"><ShieldCheck size={16} />Governance</a>
        </nav>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Commercial migration</p>
            <h1>Workspace control plane</h1>
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

        <section className="metrics">
          {[
            ["Agents", snapshot?.metrics.agents_total, <Bot key="agents" size={18} />],
            ["Running", snapshot?.metrics.agents_running, <Activity key="running" size={18} />],
            ["Completed Tasks", snapshot?.metrics.tasks_completed_total, <CheckCircle2 key="tasks" size={18} />],
            ["Pending Approvals", snapshot?.metrics.pending_approvals, <ShieldCheck key="approvals" size={18} />],
          ].map(([label, value, icon]) => (
            <div className="metric" key={String(label)}>
              <span className="metricIcon">{icon}</span>
              <span>{label}</span>
              <strong>{loading && !snapshot ? "..." : formatNumber(value)}</strong>
            </div>
          ))}
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
      </section>
    </main>
  );
}
