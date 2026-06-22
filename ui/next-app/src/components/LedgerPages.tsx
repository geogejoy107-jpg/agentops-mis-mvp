"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock, Filter, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import {
  decideApproval,
  loadApprovals,
  loadRuns,
  loadTasks,
  type ApprovalSummary,
  type RunSummary,
  type TaskSummary,
} from "@/lib/mis";
import { AppFrame } from "./AppFrame";

type LoadState<T> = {
  data: T;
  error: string | null;
  loading: boolean;
};

function statusClass(status: string) {
  if (["completed", "approved"].includes(status)) return "status statusGood";
  if (["failed", "blocked", "rejected"].includes(status)) return "status statusBad";
  if (["running", "waiting_approval", "pending"].includes(status)) return "status statusWarn";
  return "status";
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function PageHeader({
  title,
  summary,
  loading,
  onRefresh,
}: Readonly<{ title: string; summary: string; loading: boolean; onRefresh: () => void }>) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Next.js parity route</p>
        <h1>{title}</h1>
        <p className="subtle">{summary}</p>
      </div>
      <button className="iconButton" onClick={onRefresh} disabled={loading} aria-label={`Refresh ${title}`}>
        <RefreshCw size={17} className={loading ? "spin" : ""} />
      </button>
    </header>
  );
}

export function TasksParityPage() {
  const [filter, setFilter] = useState("all");
  const [state, setState] = useState<LoadState<TaskSummary[]>>({ data: [], error: null, loading: true });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      setState({ data: await loadTasks(), error: null, loading: false });
    } catch (err) {
      setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const counts = useMemo(() => {
    const byStatus = new Map<string, number>();
    for (const task of state.data) byStatus.set(task.status, (byStatus.get(task.status) || 0) + 1);
    return byStatus;
  }, [state.data]);
  const filtered = filter === "all" ? state.data : state.data.filter((task) => task.status === filter);
  const statuses = ["all", "running", "waiting_approval", "planned", "completed", "failed", "blocked"];

  return (
    <AppFrame>
      <PageHeader
        title="Tasks"
        summary={`${state.data.length} tasks · ${counts.get("running") || 0} running · ${counts.get("waiting_approval") || 0} waiting approval`}
        loading={state.loading}
        onRefresh={refresh}
      />
      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/tasks: {state.error}</div> : null}

      <div className="filterBar">
        {statuses.map((status) => (
          <button className={`filterChip ${filter === status ? "active" : ""}`} key={status} onClick={() => setFilter(status)}>
            {status}
            <span>{status === "all" ? state.data.length : counts.get(status) || 0}</span>
          </button>
        ))}
      </div>

      <div className="list">
        {filtered.length ? filtered.map((task) => (
          <Link className="row tall linkRow" href={`/workspace/tasks/${encodeURIComponent(task.task_id)}`} key={task.task_id}>
            <div>
              <strong>{task.title}</strong>
              <span>{task.task_id} · owner {task.owner_agent_id || "unassigned"}</span>
              <p>{task.description || task.acceptance_criteria || "No description loaded."}</p>
            </div>
            <div className="rowActions">
              <span className={statusClass(task.status)}>{task.status}</span>
              <span className="metaPill">{task.priority || "medium"}</span>
              <span className="metaPill">{task.risk_level || "risk unknown"}</span>
            </div>
          </Link>
        )) : (
          <div className="emptyState">
            <Filter size={24} />
            <p>No tasks match this status.</p>
          </div>
        )}
      </div>
    </AppFrame>
  );
}

export function RunsParityPage() {
  const [state, setState] = useState<LoadState<RunSummary[]>>({ data: [], error: null, loading: true });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      setState({ data: await loadRuns(), error: null, loading: false });
    } catch (err) {
      setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <AppFrame>
      <PageHeader
        title="Run Ledger"
        summary={`${state.data.length} runs from the MIS ledger`}
        loading={state.loading}
        onRefresh={refresh}
      />
      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/runs: {state.error}</div> : null}

      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th>Run</th>
              <th>Status</th>
              <th>Agent</th>
              <th>Runtime</th>
              <th>Duration</th>
              <th>Cost</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {state.data.slice(0, 120).map((run) => (
              <tr key={run.run_id}>
                <td className="mono">
                  <Link className="tableLink" href={`/workspace/runs/${encodeURIComponent(run.run_id)}`}>
                    {run.run_id}
                  </Link>
                </td>
                <td><span className={statusClass(run.status)}>{run.status}</span></td>
                <td className="mono">{run.agent_id || "-"}</td>
                <td>{run.runtime_type || "-"}</td>
                <td>{run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : "-"}</td>
                <td>${Number(run.cost_usd || 0).toFixed(3)}</td>
                <td>{formatDate(run.started_at || run.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!state.data.length ? <p className="empty tableEmpty">No runs loaded.</p> : null}
      </div>
    </AppFrame>
  );
}

export function ApprovalsParityPage({
  initialApprovals = [],
  initialError = null,
  initialLoaded = false,
}: Readonly<{ initialApprovals?: ApprovalSummary[]; initialError?: string | null; initialLoaded?: boolean }> = {}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [state, setState] = useState<LoadState<ApprovalSummary[]>>({
    data: initialApprovals,
    error: initialError,
    loading: !initialLoaded,
  });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      setState({ data: await loadApprovals(), error: null, loading: false });
    } catch (err) {
      setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    if (!initialLoaded) void refresh();
  }, [initialLoaded]);

  const pending = state.data.filter((approval) => approval.decision === "pending");
  const decided = state.data.filter((approval) => approval.decision !== "pending");

  const submitDecision = async (approvalId: string, decision: "approve" | "reject") => {
    setBusyId(approvalId);
    try {
      await decideApproval(approvalId, decision);
      await refresh();
    } finally {
      setBusyId(null);
    }
  };

  const renderApproval = (approval: ApprovalSummary) => {
    const isPending = approval.decision === "pending";
    return (
      <article className={`approval ${isPending ? "pending" : ""}`} key={approval.approval_id}>
        <div>
          <strong>{approval.approval_id}</strong>
          <span>{approval.reason || approval.task_id || approval.run_id || "approval required"}</span>
          <p>{approval.requested_by_agent_id || "agent"} · task {approval.task_id || "-"} · run {approval.run_id || "-"}</p>
        </div>
        <div className="approvalActions">
          <span className={statusClass(approval.decision)}>{approval.decision}</span>
          {isPending ? (
            <>
              <form className="inlineForm" method="post" action="/workspace/approvals/review">
                <input type="hidden" name="approval_id" value={approval.approval_id} />
                <input type="hidden" name="decision" value="approve" />
                <button
                  className="miniButton good"
                  disabled={busyId === approval.approval_id}
                  onClick={(event) => {
                    event.preventDefault();
                    void submitDecision(approval.approval_id, "approve");
                  }}
                  type="submit"
                >
                  <CheckCircle2 size={13} />Approve
                </button>
              </form>
              <form className="inlineForm" method="post" action="/workspace/approvals/review">
                <input type="hidden" name="approval_id" value={approval.approval_id} />
                <input type="hidden" name="decision" value="reject" />
                <button
                  className="miniButton bad"
                  disabled={busyId === approval.approval_id}
                  onClick={(event) => {
                    event.preventDefault();
                    void submitDecision(approval.approval_id, "reject");
                  }}
                  type="submit"
                >
                  <XCircle size={13} />Reject
                </button>
              </form>
            </>
          ) : null}
        </div>
      </article>
    );
  };

  return (
    <AppFrame>
      <PageHeader
        title="Approvals"
        summary={`${pending.length} pending · ${decided.length} decided`}
        loading={state.loading || Boolean(busyId)}
        onRefresh={refresh}
      />
      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/approvals: {state.error}</div> : null}

      <section className="panel wide">
        <div className="panelHeader">
          <h2><Clock size={14} /> Pending approval</h2>
          <span>{pending.length} open</span>
        </div>
        <div className="approvalGrid single">
          {pending.length ? pending.map(renderApproval) : <p className="empty">No pending approvals.</p>}
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><ShieldAlert size={14} /> Decision history</h2>
          <span>{decided.length} decisions</span>
        </div>
        <div className="approvalGrid single">
          {decided.length ? decided.slice(0, 80).map(renderApproval) : <p className="empty">No approval history loaded.</p>}
        </div>
      </section>
    </AppFrame>
  );
}
