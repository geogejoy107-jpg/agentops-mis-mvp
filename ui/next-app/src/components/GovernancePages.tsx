"use client";

import { useEffect, useMemo, useState } from "react";
import { Bot, Brain, CheckCircle2, Filter, History, Monitor, RefreshCw, User, XCircle } from "lucide-react";
import { AppFrame } from "./AppFrame";
import {
  decideMemory,
  loadAudit,
  loadMemories,
  type AuditSummary,
  type MemorySummary,
} from "@/lib/mis";

type LoadState<T> = {
  data: T;
  error: string | null;
  loading: boolean;
};

function statusClass(status: string) {
  if (["approved", "completed"].includes(status)) return "status statusGood";
  if (["rejected", "failed"].includes(status)) return "status statusBad";
  if (["candidate", "pending", "stale"].includes(status)) return "status statusWarn";
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
        <p className="eyebrow">Governance parity route</p>
        <h1>{title}</h1>
        <p className="subtle">{summary}</p>
      </div>
      <button className="iconButton" onClick={onRefresh} disabled={loading} aria-label={`Refresh ${title}`}>
        <RefreshCw size={17} className={loading ? "spin" : ""} />
      </button>
    </header>
  );
}

export function MemoryParityPage({
  initialMemories = [],
  initialError = null,
  initialLoaded = false,
}: Readonly<{ initialMemories?: MemorySummary[]; initialError?: string | null; initialLoaded?: boolean }> = {}) {
  const [scopeFilter, setScopeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [state, setState] = useState<LoadState<MemorySummary[]>>({
    data: initialMemories,
    error: initialError,
    loading: !initialLoaded,
  });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      setState({ data: await loadMemories(), error: null, loading: false });
    } catch (err) {
      setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    if (!initialLoaded) void refresh();
  }, [initialLoaded]);

  const counts = useMemo(() => {
    const scopes = new Map<string, number>();
    const statuses = new Map<string, number>();
    for (const memory of state.data) {
      scopes.set(memory.scope, (scopes.get(memory.scope) || 0) + 1);
      statuses.set(memory.review_status, (statuses.get(memory.review_status) || 0) + 1);
    }
    return { scopes, statuses };
  }, [state.data]);

  const filtered = state.data.filter((memory) => {
    if (scopeFilter !== "all" && memory.scope !== scopeFilter) return false;
    if (statusFilter !== "all" && memory.review_status !== statusFilter) return false;
    return true;
  });

  const submitDecision = async (memoryId: string, decision: "approve" | "reject") => {
    setBusyId(memoryId);
    try {
      await decideMemory(memoryId, decision);
      await refresh();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <AppFrame>
      <PageHeader
        title="Memory"
        summary={`${state.data.length} memories · ${counts.statuses.get("candidate") || 0} candidates pending review`}
        loading={state.loading || Boolean(busyId)}
        onRefresh={refresh}
      />
      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/memories: {state.error}</div> : null}

      <div className="filterBar">
        {["all", "task", "project", "org"].map((scope) => (
          <button className={`filterChip ${scopeFilter === scope ? "active" : ""}`} key={scope} onClick={() => setScopeFilter(scope)}>
            {scope}
            <span>{scope === "all" ? state.data.length : counts.scopes.get(scope) || 0}</span>
          </button>
        ))}
        {["all", "candidate", "approved", "rejected", "stale"].map((status) => (
          <button className={`filterChip ${statusFilter === status ? "active" : ""}`} key={status} onClick={() => setStatusFilter(status)}>
            {status}
            <span>{status === "all" ? state.data.length : counts.statuses.get(status) || 0}</span>
          </button>
        ))}
      </div>

      <div className="list">
        {filtered.length ? filtered.map((memory) => (
          <article className="row tall memoryRow" key={memory.memory_id}>
            <span className="memoryIcon"><Brain size={15} /></span>
            <div>
              <strong>{memory.memory_type}</strong>
              <span>{memory.memory_id} · {memory.scope} · confidence {Math.round(Number(memory.confidence || 0) * 100)}%</span>
              <p>{memory.canonical_text}</p>
              <span>{memory.source_type || "source unknown"} · {formatDate(memory.created_at)}</span>
            </div>
            <div className="rowActions">
              <span className={statusClass(memory.review_status)}>{memory.review_status}</span>
              {memory.review_status === "candidate" ? (
                <>
                  <form className="inlineForm" method="post" action="/workspace/memory/review">
                    <input type="hidden" name="memory_id" value={memory.memory_id} />
                    <input type="hidden" name="decision" value="approve" />
                    <button
                      className="miniButton good"
                      disabled={busyId === memory.memory_id}
                      onClick={(event) => {
                        event.preventDefault();
                        void submitDecision(memory.memory_id, "approve");
                      }}
                      type="submit"
                    >
                      <CheckCircle2 size={13} />Approve
                    </button>
                  </form>
                  <form className="inlineForm" method="post" action="/workspace/memory/review">
                    <input type="hidden" name="memory_id" value={memory.memory_id} />
                    <input type="hidden" name="decision" value="reject" />
                    <button
                      className="miniButton bad"
                      disabled={busyId === memory.memory_id}
                      onClick={(event) => {
                        event.preventDefault();
                        void submitDecision(memory.memory_id, "reject");
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
        )) : (
          <div className="emptyState">
            <Filter size={24} />
            <p>No memories match these filters.</p>
          </div>
        )}
      </div>
    </AppFrame>
  );
}

function actorIcon(type: string) {
  if (type === "user") return <User size={13} />;
  if (type === "agent") return <Bot size={13} />;
  return <Monitor size={13} />;
}

export function AuditParityPage() {
  const [actorFilter, setActorFilter] = useState("all");
  const [state, setState] = useState<LoadState<AuditSummary[]>>({ data: [], error: null, loading: true });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      setState({ data: await loadAudit(), error: null, loading: false });
    } catch (err) {
      setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const counts = useMemo(() => {
    const actors = new Map<string, number>();
    for (const audit of state.data) actors.set(audit.actor_type, (actors.get(audit.actor_type) || 0) + 1);
    return actors;
  }, [state.data]);
  const filtered = actorFilter === "all" ? state.data : state.data.filter((audit) => audit.actor_type === actorFilter);

  return (
    <AppFrame>
      <PageHeader
        title="Audit"
        summary={`${state.data.length} audit events · append-only evidence readback`}
        loading={state.loading}
        onRefresh={refresh}
      />
      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/audit: {state.error}</div> : null}

      <div className="filterBar">
        {["all", "user", "agent", "system"].map((actor) => (
          <button className={`filterChip ${actorFilter === actor ? "active" : ""}`} key={actor} onClick={() => setActorFilter(actor)}>
            {actor}
            <span>{actor === "all" ? state.data.length : counts.get(actor) || 0}</span>
          </button>
        ))}
      </div>

      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th>Actor</th>
              <th>Action</th>
              <th>Entity</th>
              <th>Entity ID</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 140).map((audit) => (
              <tr key={audit.audit_id}>
                <td>
                  <span className="actorCell">{actorIcon(audit.actor_type)} {audit.actor_id} <em>{audit.actor_type}</em></span>
                </td>
                <td>{audit.action}</td>
                <td>{audit.entity_type}</td>
                <td className="mono">{audit.entity_id}</td>
                <td>{formatDate(audit.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length ? <p className="empty tableEmpty">No audit events loaded.</p> : null}
      </div>
    </AppFrame>
  );
}
