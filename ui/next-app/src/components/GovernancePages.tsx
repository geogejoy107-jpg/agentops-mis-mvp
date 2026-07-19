"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Bot, Brain, CheckCircle2, Filter, History, LogIn, LogOut, Monitor, RefreshCw, User, XCircle } from "lucide-react";
import { AppFrame } from "./AppFrame";
import {
  decideMemory,
  isHumanSessionUnauthorized,
  loadHumanSession,
  loadAudit,
  loadMemories,
  loginHumanSession,
  logoutHumanSession,
  MisApiError,
  setActiveWorkspaceId,
  type AuditSummary,
  type HumanSessionPayload,
  type MemorySummary,
} from "@/lib/mis";
import {
  acquireMemoryReviewIdempotencyKey,
  getMemoryReviewSessionStorage,
  memoryReviewIdempotencyStorageKey,
  reconcileMemoryReviewIdempotencyKeys,
  type MemoryReviewIdempotencyScope,
} from "@/lib/memoryReviewIdempotency";

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
  const [authMode, setAuthMode] = useState<"loading" | "required" | "authenticated" | "proxy">("loading");
  const [humanSession, setHumanSession] = useState<HumanSessionPayload | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const fallbackDecisionIdempotencyKeys = useRef(new Map<string, string>());
  const [state, setState] = useState<LoadState<MemorySummary[]>>({
    data: initialMemories,
    error: initialError,
    loading: !initialLoaded,
  });

  const refresh = async (
    selectedWorkspace = workspaceId,
    mode = authMode,
    selectedUserId = humanSession?.user?.user_id || "",
  ): Promise<MemorySummary[] | null> => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      const directWorkspace = mode === "authenticated" ? selectedWorkspace : undefined;
      const memories = await loadMemories(directWorkspace);
      if (mode === "authenticated" && selectedUserId && selectedWorkspace) {
        const storage = getMemoryReviewSessionStorage();
        if (storage) {
          reconcileMemoryReviewIdempotencyKeys(storage, selectedUserId, selectedWorkspace, memories);
        }
      }
      setState({ data: memories, error: null, loading: false });
      return memories;
    } catch (err) {
      if (isHumanSessionUnauthorized(err)) {
        setHumanSession(null);
        setWorkspaceId("");
        setActiveWorkspaceId("");
        setAuthMode("required");
      }
      setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
      return null;
    }
  };

  useEffect(() => {
    let active = true;
    const initialize = async () => {
      try {
        const session = await loadHumanSession();
        if (!active) return;
        const memberships = session.memberships || [];
        const selectedWorkspace = memberships.length === 1 ? memberships[0].workspace_id : "";
        setHumanSession(session);
        setWorkspaceId(selectedWorkspace);
        setActiveWorkspaceId(selectedWorkspace);
        setAuthMode("authenticated");
        if (selectedWorkspace) {
          await refresh(selectedWorkspace, "authenticated", session.user?.user_id || "");
        } else {
          setState({ data: [], error: null, loading: false });
        }
      } catch (err) {
        if (!active) return;
        if (isHumanSessionUnauthorized(err)) {
          setHumanSession(null);
          setWorkspaceId("");
          setActiveWorkspaceId("");
          setAuthMode("required");
          setState({ data: [], error: null, loading: false });
          return;
        }
        if (err instanceof MisApiError && err.code === "human_session_postgres_required") {
          setAuthMode("proxy");
          if (!initialLoaded) await refresh("", "proxy");
          return;
        }
        setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
      }
    };
    void initialize();
    return () => {
      active = false;
    };
  }, [initialLoaded]);

  const submitLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      const session = await loginHumanSession(username, password);
      const memberships = session.memberships || [];
      const selectedWorkspace = memberships.length === 1 ? memberships[0].workspace_id : "";
      setPassword("");
      setHumanSession(session);
      setWorkspaceId(selectedWorkspace);
      setActiveWorkspaceId(selectedWorkspace);
      setAuthMode("authenticated");
      if (selectedWorkspace) {
        await refresh(selectedWorkspace, "authenticated", session.user?.user_id || "");
      } else {
        setState({ data: [], error: null, loading: false });
      }
    } catch (err) {
      setPassword("");
      setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  const submitLogout = async () => {
    const csrfToken = humanSession?.csrf_token || "";
    try {
      await logoutHumanSession(csrfToken, workspaceId);
      setHumanSession(null);
      setWorkspaceId("");
      setActiveWorkspaceId("");
      setAuthMode("required");
      setState({ data: [], error: null, loading: false });
    } catch (err) {
      if (isHumanSessionUnauthorized(err)) {
        setHumanSession(null);
        setWorkspaceId("");
        setActiveWorkspaceId("");
        setAuthMode("required");
        setState({ data: [], error: null, loading: false });
        return;
      }
      setState((current) => ({ ...current, error: err instanceof Error ? err.message : String(err) }));
    }
  };

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
  const selectedMembership = humanSession?.memberships?.find((membership) => membership.workspace_id === workspaceId);
  const canReview = authMode === "proxy" || ["approver", "owner"].includes(selectedMembership?.role || "");
  const statusFilters = authMode === "authenticated"
    ? ["all", "candidate"]
    : ["all", "candidate", "approved", "rejected", "stale"];

  const submitDecision = async (memoryId: string, decision: "approve" | "reject") => {
    setBusyId(memoryId);
    try {
      const userId = humanSession?.user?.user_id || "";
      let human: { workspaceId: string; csrfToken: string; idempotencyKey: string } | undefined;
      if (authMode === "authenticated") {
        if (!userId || !workspaceId) throw new Error("Human Session workspace context is unavailable");
        const scope: MemoryReviewIdempotencyScope = { userId, workspaceId, memoryId, decision };
        const storageKey = memoryReviewIdempotencyStorageKey(scope);
        const storage = getMemoryReviewSessionStorage();
        let idempotencyKey = fallbackDecisionIdempotencyKeys.current.get(storageKey);
        if (storage) {
          const acquired = acquireMemoryReviewIdempotencyKey(storage, scope);
          idempotencyKey = acquired.persisted
            ? acquired.key
            : idempotencyKey || acquired.key;
        }
        if (!idempotencyKey) {
          idempotencyKey = `memory-review-${crypto.randomUUID()}`;
        }
        fallbackDecisionIdempotencyKeys.current.set(storageKey, idempotencyKey);
        human = { workspaceId, csrfToken: humanSession?.csrf_token || "", idempotencyKey };
      }
      await decideMemory(memoryId, decision, human);
      await refresh(workspaceId, authMode, userId);
    } catch (err) {
      if (isHumanSessionUnauthorized(err)) {
        setHumanSession(null);
        setWorkspaceId("");
        setActiveWorkspaceId("");
        setAuthMode("required");
      }
      setState((current) => ({ ...current, error: err instanceof Error ? err.message : String(err) }));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <AppFrame>
      <PageHeader
        title={authMode === "authenticated" ? "Memory Review Queue" : "Memory"}
        summary={`${state.data.length} memories · ${counts.statuses.get("candidate") || 0} candidates pending review`}
        loading={state.loading || Boolean(busyId)}
        onRefresh={() => void refresh()}
      />
      {authMode === "required" ? (
        <form className="humanSessionBar" onSubmit={submitLogin}>
          <label className="field">
            <span>Username</span>
            <input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
          </label>
          <label className="field">
            <span>Password</span>
            <input autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </label>
          <button className="miniButton good" disabled={state.loading} type="submit"><LogIn size={13} />Sign in</button>
        </form>
      ) : null}
      {authMode === "authenticated" && humanSession ? (
        <div className="humanSessionBar">
          <div className="sessionIdentity">
            <User size={15} />
            <span>{humanSession.user?.name || humanSession.user?.user_id}</span>
          </div>
          <label className="field workspaceSelect">
            <span>Workspace</span>
            <select
              value={workspaceId}
              required
              onChange={(event) => {
                const selected = event.target.value;
                setWorkspaceId(selected);
                setActiveWorkspaceId(selected);
                void refresh(selected, "authenticated");
              }}
            >
              <option value="" disabled>Select workspace</option>
              {(humanSession.memberships || []).map((membership) => (
                <option key={membership.workspace_id} value={membership.workspace_id}>
                  {membership.workspace_id} ({membership.role})
                </option>
              ))}
            </select>
          </label>
          <button className="iconButton" onClick={() => void submitLogout()} type="button" aria-label="Sign out" title="Sign out">
            <LogOut size={16} />
          </button>
        </div>
      ) : null}
      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/memories: {state.error}</div> : null}

      <div className="filterBar">
        {["all", "task", "project", "org"].map((scope) => (
          <button className={`filterChip ${scopeFilter === scope ? "active" : ""}`} key={scope} onClick={() => setScopeFilter(scope)}>
            {scope}
            <span>{scope === "all" ? state.data.length : counts.scopes.get(scope) || 0}</span>
          </button>
        ))}
        {statusFilters.map((status) => (
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
              {memory.review_status === "candidate" && canReview ? (
                <>
                  <button
                    className="miniButton good"
                    disabled={busyId === memory.memory_id}
                    onClick={() => void submitDecision(memory.memory_id, "approve")}
                    type="button"
                  >
                    <CheckCircle2 size={13} />Approve
                  </button>
                  <button
                    className="miniButton bad"
                    disabled={busyId === memory.memory_id}
                    onClick={() => void submitDecision(memory.memory_id, "reject")}
                    type="button"
                  >
                    <XCircle size={13} />Reject
                  </button>
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
