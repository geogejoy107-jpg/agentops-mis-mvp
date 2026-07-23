"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { CheckCircle2, Clock, Filter, LogIn, LogOut, RefreshCw, ShieldAlert, User, XCircle } from "lucide-react";
import {
  decideApproval,
  getActiveWorkspaceId,
  isHumanSessionUnauthorized,
  loadApprovals,
  loadHumanSession,
  loadRuns,
  loadTasks,
  loginHumanSession,
  logoutHumanSession,
  MisApiError,
  setActiveWorkspaceId,
  type ApprovalSummary,
  type HumanSessionPayload,
  type RunSummary,
  type TaskSummary,
} from "@/lib/mis";
import { AppFrame } from "./AppFrame";

type LoadState<T> = {
  data: T;
  error: string | null;
  loading: boolean;
};

type AuthMode = "loading" | "required" | "authenticated" | "proxy";

const APPROVAL_DECISION_KEY_PATTERN = /^[A-Za-z0-9._:-]{16,128}$/;

function selectedWorkspaceForSession(session: HumanSessionPayload) {
  const memberships = session.memberships || [];
  const persistedWorkspace = getActiveWorkspaceId();
  if (memberships.some((membership) => membership.workspace_id === persistedWorkspace)) {
    return persistedWorkspace;
  }
  return memberships.length === 1 ? memberships[0].workspace_id : "";
}

function approvalDecisionStorageKey(
  userId: string,
  workspaceId: string,
  approvalId: string,
  decision: "approve" | "reject",
) {
  return ["agentops_approval_decision", userId, workspaceId, approvalId, decision]
    .map((part) => encodeURIComponent(part))
    .join(":");
}

function newApprovalDecisionKey() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `approval-decision-${globalThis.crypto.randomUUID()}`;
  }
  return `approval-decision-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

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
  const [authMode, setAuthMode] = useState<AuthMode>("loading");
  const [humanSession, setHumanSession] = useState<HumanSessionPayload | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const fallbackDecisionIdempotencyKeys = useRef(new Map<string, string>());
  const [state, setState] = useState<LoadState<ApprovalSummary[]>>({
    data: initialApprovals,
    error: initialError,
    loading: !initialLoaded,
  });

  const requireLogin = () => {
    setHumanSession(null);
    setWorkspaceId("");
    setActiveWorkspaceId("");
    setAuthMode("required");
    setState({ data: [], error: null, loading: false });
  };

  const refresh = async (
    selectedWorkspace = workspaceId,
    mode = authMode,
  ): Promise<ApprovalSummary[] | null> => {
    if (mode === "loading" || mode === "required" || (mode === "authenticated" && !selectedWorkspace)) {
      setState({ data: [], error: null, loading: false });
      return null;
    }
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      const directWorkspace = mode === "authenticated" ? selectedWorkspace : undefined;
      const approvals = await loadApprovals(directWorkspace);
      setState({ data: approvals, error: null, loading: false });
      return approvals;
    } catch (err) {
      if (isHumanSessionUnauthorized(err)) {
        requireLogin();
        return null;
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
        const selectedWorkspace = selectedWorkspaceForSession(session);
        setHumanSession(session);
        setWorkspaceId(selectedWorkspace);
        setActiveWorkspaceId(selectedWorkspace);
        setAuthMode("authenticated");
        if (selectedWorkspace) {
          await refresh(selectedWorkspace, "authenticated");
        } else {
          setState({ data: [], error: null, loading: false });
        }
      } catch (err) {
        if (!active) return;
        if (isHumanSessionUnauthorized(err)) {
          requireLogin();
          return;
        }
        if (err instanceof MisApiError && err.code === "human_session_postgres_required") {
          setAuthMode("proxy");
          if (!initialLoaded) {
            await refresh("", "proxy");
          } else {
            setState((current) => ({ ...current, loading: false }));
          }
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
      const selectedWorkspace = selectedWorkspaceForSession(session);
      setPassword("");
      setHumanSession(session);
      setWorkspaceId(selectedWorkspace);
      setActiveWorkspaceId(selectedWorkspace);
      setAuthMode("authenticated");
      if (selectedWorkspace) {
        await refresh(selectedWorkspace, "authenticated");
      } else {
        setState({ data: [], error: null, loading: false });
      }
    } catch (err) {
      setPassword("");
      setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  const submitLogout = async () => {
    try {
      await logoutHumanSession(humanSession?.csrf_token || "", workspaceId);
      requireLogin();
    } catch (err) {
      if (isHumanSessionUnauthorized(err)) {
        requireLogin();
        return;
      }
      setState((current) => ({ ...current, error: err instanceof Error ? err.message : String(err) }));
    }
  };

  const decisionIdempotencyKey = (approvalId: string, decision: "approve" | "reject") => {
    const userId = humanSession?.user?.user_id || "free-local";
    const selectedWorkspace = workspaceId || "free-local";
    const storageKey = approvalDecisionStorageKey(userId, selectedWorkspace, approvalId, decision);
    const fallbackKey = fallbackDecisionIdempotencyKeys.current.get(storageKey);
    try {
      const storedKey = window.sessionStorage.getItem(storageKey);
      if (storedKey && APPROVAL_DECISION_KEY_PATTERN.test(storedKey)) {
        fallbackDecisionIdempotencyKeys.current.set(storageKey, storedKey);
        return storedKey;
      }
      const nextKey = fallbackKey || newApprovalDecisionKey();
      window.sessionStorage.setItem(storageKey, nextKey);
      fallbackDecisionIdempotencyKeys.current.set(storageKey, nextKey);
      return nextKey;
    } catch {
      const nextKey = fallbackKey || newApprovalDecisionKey();
      fallbackDecisionIdempotencyKeys.current.set(storageKey, nextKey);
      return nextKey;
    }
  };

  const pending = state.data.filter((approval) => approval.decision === "pending");
  const decided = state.data.filter((approval) => approval.decision !== "pending");
  const selectedMembership = humanSession?.memberships?.find((membership) => membership.workspace_id === workspaceId);
  const canReview = authMode === "proxy" || ["approver", "owner"].includes(selectedMembership?.role || "");

  const submitDecision = async (approvalId: string, decision: "approve" | "reject") => {
    setBusyId(approvalId);
    try {
      let human: { workspaceId: string; csrfToken: string; idempotencyKey: string } | undefined;
      if (authMode === "authenticated") {
        const userId = humanSession?.user?.user_id || "";
        const csrfToken = humanSession?.csrf_token || "";
        if (!userId || !workspaceId || !csrfToken || !canReview) {
          throw new Error("Human Session approval context is unavailable");
        }
        human = {
          workspaceId,
          csrfToken,
          idempotencyKey: decisionIdempotencyKey(approvalId, decision),
        };
      }
      await decideApproval(approvalId, decision, human);
      await refresh(workspaceId, authMode);
    } catch (err) {
      if (isHumanSessionUnauthorized(err)) {
        requireLogin();
        return;
      }
      setState((current) => ({ ...current, error: err instanceof Error ? err.message : String(err) }));
    } finally {
      setBusyId(null);
    }
  };

  const renderApproval = (approval: ApprovalSummary) => {
    const isPending = approval.decision === "pending";
    const approveIdempotencyKey = isPending && canReview
      ? decisionIdempotencyKey(approval.approval_id, "approve")
      : "";
    const rejectIdempotencyKey = isPending && canReview
      ? decisionIdempotencyKey(approval.approval_id, "reject")
      : "";
    return (
      <article className={`approval ${isPending ? "pending" : ""}`} key={approval.approval_id}>
        <div>
          <strong>{approval.approval_id}</strong>
          <span>{approval.approval_kind || approval.reason || approval.task_id || approval.run_id || "approval required"}</span>
          <p>{approval.requested_by_agent_id || "agent"} · task {approval.task_id || "-"} · run {approval.run_id || "-"}</p>
        </div>
        <div className="approvalActions">
          <span className={statusClass(approval.decision)}>{approval.decision}</span>
          {isPending && canReview ? (
            <>
              <form className="inlineForm" method="post" action="/workspace/approvals/review">
                <input type="hidden" name="approval_id" value={approval.approval_id} />
                <input type="hidden" name="decision" value="approve" />
                <input type="hidden" name="workspace_id" value={workspaceId} />
                <input type="hidden" name="csrf_token" value={humanSession?.csrf_token || ""} />
                <input type="hidden" name="idempotency_key" value={approveIdempotencyKey} />
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
                <input type="hidden" name="workspace_id" value={workspaceId} />
                <input type="hidden" name="csrf_token" value={humanSession?.csrf_token || ""} />
                <input type="hidden" name="idempotency_key" value={rejectIdempotencyKey} />
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
        loading={state.loading
          || Boolean(busyId)
          || authMode === "loading"
          || authMode === "required"
          || (authMode === "authenticated" && !workspaceId)}
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
              {(humanSession.memberships || []).length !== 1 ? <option value="">Select workspace</option> : null}
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
