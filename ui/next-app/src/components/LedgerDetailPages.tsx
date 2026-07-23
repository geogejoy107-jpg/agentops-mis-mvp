"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ClipboardCheck, ClipboardList, GitBranch, Package, RefreshCw, ShieldCheck, Wrench } from "lucide-react";
import { AppFrame } from "./AppFrame";
import {
  isHumanSessionUnauthorized,
  loadRunDetail,
  loadRunGraph,
  loadTaskDetail,
  setActiveWorkspaceId,
  type RunDetailSnapshot,
  type TaskDetailPayload,
} from "@/lib/mis";

function count(value: unknown) {
  return Array.isArray(value) ? value.length : Number(value || 0);
}

function statusClass(status: string) {
  if (["completed", "approved", "verified", "ready", "pass"].includes(status)) return "status statusGood";
  if (["failed", "blocked", "rejected", "fail"].includes(status)) return "status statusBad";
  if (["running", "waiting_approval", "pending", "warning"].includes(status)) return "status statusWarn";
  return "status";
}

function formatMs(value?: number | null) {
  return value ? `${(value / 1000).toFixed(1)}s` : "-";
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function DetailState({
  loading,
  sessionRequired,
  error,
  notFound,
}: Readonly<{ loading: boolean; sessionRequired: boolean; error?: string | null; notFound: string }>) {
  if (loading) return <div className="emptyState"><RefreshCw className="spin" size={24} /><p>Loading ledger detail...</p></div>;
  if (sessionRequired) {
    return (
      <div className="banner error">
        Human Session required. <Link className="backLink" href="/workspace">Sign in</Link>
      </div>
    );
  }
  if (error) return <div className="banner error">{error}</div>;
  return <div className="banner error">{notFound}</div>;
}

export function TaskDetailClientPage({ taskId }: Readonly<{ taskId: string }>) {
  const [detail, setDetail] = useState<TaskDetailPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionRequired, setSessionRequired] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSessionRequired(false);
    try {
      setDetail(await loadTaskDetail(taskId));
    } catch (err) {
      setDetail(null);
      if (isHumanSessionUnauthorized(err)) {
        setActiveWorkspaceId("");
        setSessionRequired(true);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <TaskDetailPage
      taskId={taskId}
      detail={detail}
      error={error}
      loading={loading}
      sessionRequired={sessionRequired}
      onRefresh={refresh}
    />
  );
}

export function RunDetailClientPage({ runId }: Readonly<{ runId: string }>) {
  const [snapshot, setSnapshot] = useState<RunDetailSnapshot>({ detail: null, graph: null });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionRequired, setSessionRequired] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSessionRequired(false);
    try {
      const [detail, graph] = await Promise.all([loadRunDetail(runId), loadRunGraph(runId)]);
      setSnapshot({ detail, graph });
    } catch (err) {
      setSnapshot({ detail: null, graph: null });
      if (isHumanSessionUnauthorized(err)) {
        setActiveWorkspaceId("");
        setSessionRequired(true);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <RunDetailPage
      runId={runId}
      snapshot={snapshot}
      error={error}
      loading={loading}
      sessionRequired={sessionRequired}
      onRefresh={refresh}
    />
  );
}

export function TaskDetailPage({
  taskId,
  detail,
  error,
  loading = false,
  sessionRequired = false,
  onRefresh,
}: Readonly<{
  taskId: string;
  detail: TaskDetailPayload | null;
  error?: string | null;
  loading?: boolean;
  sessionRequired?: boolean;
  onRefresh?: () => void;
}>) {
  const task = detail?.task;
  const runs = detail?.runs || [];
  const approvals = detail?.approvals || [];
  const artifacts = detail?.artifacts || [];

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <Link className="backLink" href="/workspace/tasks"><ArrowLeft size={14} /> Tasks</Link>
          <p className="eyebrow">Read-only task detail</p>
          <h1>Task Detail</h1>
          <p className="subtle">{taskId}</p>
        </div>
        <div className="rowActions">
          <Link className="miniButton" href="/workspace/runs">Run ledger</Link>
          {onRefresh ? (
            <button className="iconButton" onClick={() => void onRefresh()} disabled={loading} aria-label="Refresh task detail">
              <RefreshCw size={17} className={loading ? "spin" : ""} />
            </button>
          ) : null}
        </div>
      </header>
      {loading || sessionRequired || error || detail?.error || !task ? (
        <DetailState
          loading={loading}
          sessionRequired={sessionRequired}
          error={error || detail?.error}
          notFound="Task not found"
        />
      ) : (
        <>
          <section className="metrics six">
            {[
              ["Runs", runs.length],
              ["Approvals", approvals.length],
              ["Evaluations", count(detail.evaluations)],
              ["Memories", count(detail.memories)],
              ["Artifacts", artifacts.length],
              ["Token omission", detail.token_omitted === true ? "verified" : "unverified"],
            ].map(([label, value]) => (
              <div className="metric compactMetric" key={String(label)}>
                <span>{label}</span>
                <strong>{String(value)}</strong>
              </div>
            ))}
          </section>

          <section className="panel wide">
            <div className="panelHeader">
              <h2><ClipboardList size={14} /> Task</h2>
              <span className={statusClass(task.status)}>{task.status}</span>
            </div>
            <div className="proofStrip">
              <span>owner {task.owner_agent_id || "unassigned"}</span>
              <span>risk {task.risk_level || "unknown"}</span>
              <span>priority {task.priority || "medium"}</span>
              <span>budget ${Number(task.budget_limit_usd || 0).toFixed(2)}</span>
            </div>
            <p className="subtle">{task.description || task.acceptance_criteria || "No task description loaded."}</p>
          </section>

          <section className="panel wide">
            <div className="panelHeader">
              <h2><GitBranch size={14} /> Runs</h2>
              <span>{runs.length} runs</span>
            </div>
            <div className="list compactList">
              {runs.length ? runs.map((run) => (
                <Link className="row linkRow" href={`/workspace/runs/${encodeURIComponent(run.run_id)}`} key={run.run_id}>
                  <div>
                    <strong>{run.run_id}</strong>
                    <span>{run.agent_id || "agent"} · {run.runtime_type || "runtime"} · {formatMs(run.duration_ms)}</span>
                  </div>
                  <span className={statusClass(run.status)}>{run.status}</span>
                </Link>
              )) : <p className="empty">No runs loaded for this task.</p>}
            </div>
          </section>

          <section className="grid">
            <div className="panel">
              <div className="panelHeader">
                <h2><ShieldCheck size={14} /> Approvals</h2>
                <span>{approvals.length}</span>
              </div>
              <div className="list compactList">
                {approvals.length ? approvals.slice(0, 6).map((approval) => (
                  <div className="row" key={approval.approval_id}>
                    <div>
                      <strong>{approval.approval_id}</strong>
                      <span>expires {formatDate(approval.expires_at)}</span>
                    </div>
                    <span className={statusClass(approval.decision)}>{approval.decision}</span>
                  </div>
                )) : <p className="empty">No approval evidence loaded.</p>}
              </div>
            </div>
            <div className="panel">
              <div className="panelHeader">
                <h2><Package size={14} /> Artifacts</h2>
                <span>{artifacts.length}</span>
              </div>
              <div className="list compactList">
                {artifacts.length ? artifacts.slice(0, 6).map((artifact) => (
                  <div className="row" key={artifact.artifact_id}>
                    <div>
                      <strong>{artifact.title || artifact.artifact_id}</strong>
                      <span>{artifact.artifact_type || "artifact"} · {formatDate(artifact.created_at)}</span>
                    </div>
                  </div>
                )) : <p className="empty">No artifact evidence loaded.</p>}
              </div>
            </div>
          </section>
        </>
      )}
    </AppFrame>
  );
}

export function RunDetailPage({
  runId,
  snapshot,
  error,
  loading = false,
  sessionRequired = false,
  onRefresh,
}: Readonly<{
  runId: string;
  snapshot: RunDetailSnapshot;
  error?: string | null;
  loading?: boolean;
  sessionRequired?: boolean;
  onRefresh?: () => void;
}>) {
  const detail = snapshot.detail;
  const graph = snapshot.graph;
  const run = detail?.run || graph?.run;
  const task = detail?.task || graph?.task;
  const taskIdForLink = task?.task_id || run?.task_id;
  const toolCalls = detail?.tool_calls || graph?.tool_calls || [];
  const evaluations = detail?.evaluations || graph?.evaluations || [];
  const artifacts = detail?.artifacts || graph?.artifacts || [];
  const auditLogs = detail?.audit_logs || graph?.audit_logs || [];

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <Link className="backLink" href="/workspace/runs"><ArrowLeft size={14} /> Runs</Link>
          <p className="eyebrow">Read-only run detail</p>
          <h1>Run Detail</h1>
          <p className="subtle">{runId}</p>
        </div>
        <div className="rowActions">
          {taskIdForLink ? <Link className="miniButton" href={`/workspace/tasks/${encodeURIComponent(taskIdForLink)}`}>Open task</Link> : null}
          {onRefresh ? (
            <button className="iconButton" onClick={() => void onRefresh()} disabled={loading} aria-label="Refresh run detail">
              <RefreshCw size={17} className={loading ? "spin" : ""} />
            </button>
          ) : null}
        </div>
      </header>
      {loading || sessionRequired || error || detail?.error || graph?.error || !run ? (
        <DetailState
          loading={loading}
          sessionRequired={sessionRequired}
          error={error || detail?.error || graph?.error}
          notFound="Run not found"
        />
      ) : (
        <>
          <section className="metrics nine">
            {[
              ["Tool calls", toolCalls.length],
              ["Evaluations", evaluations.length],
              ["Artifacts", artifacts.length],
              ["Approvals", count(detail?.approvals || graph?.approvals)],
              ["Audit logs", auditLogs.length],
              ["Runtime events", count(detail?.runtime_events || graph?.runtime_events)],
              ["Children", count(graph?.children)],
              ["Siblings", count(graph?.siblings_by_delegation)],
              ["Token omission", detail?.token_omitted === true && graph?.token_omitted === true ? "verified" : "unverified"],
            ].map(([label, value]) => (
              <div className="metric compactMetric" key={String(label)}>
                <span>{label}</span>
                <strong>{String(value)}</strong>
              </div>
            ))}
          </section>

          <section className="grid">
            <div className="panel">
              <div className="panelHeader">
                <h2><GitBranch size={14} /> Run</h2>
                <span className={statusClass(run.status)}>{run.status}</span>
              </div>
              <div className="proofStrip">
                <span>agent {run.agent_id || "none"}</span>
                <span>runtime {run.runtime_type || "unknown"}</span>
                <span>duration {formatMs(run.duration_ms)}</span>
                <span>cost ${Number(run.cost_usd || 0).toFixed(3)}</span>
              </div>
              <p className="subtle">started {formatDate(run.started_at || run.created_at)}</p>
            </div>
            <div className="panel">
              <div className="panelHeader">
                <h2><ClipboardList size={14} /> Task</h2>
                <span className={statusClass(task?.status || "unknown")}>{task?.status || "unknown"}</span>
              </div>
              <div className="proofStrip">
                <span>task {task?.task_id || run.task_id || "none"}</span>
                <span>owner {task?.owner_agent_id || "unknown"}</span>
                <span>risk {task?.risk_level || "unknown"}</span>
              </div>
              <p className="subtle">{task?.title || "Task readback not loaded."}</p>
            </div>
          </section>

          <section className="grid">
            <div className="panel">
              <div className="panelHeader">
                <h2><Wrench size={14} /> Tool calls</h2>
                <span>{toolCalls.length}</span>
              </div>
              <div className="list compactList">
                {toolCalls.length ? toolCalls.slice(0, 8).map((toolCall) => (
                  <div className="row" key={toolCall.tool_call_id}>
                    <div>
                      <strong>{toolCall.tool_name || toolCall.tool_call_id}</strong>
                      <span>{toolCall.tool_call_id} · agent {toolCall.agent_id || "unknown"}</span>
                    </div>
                    <span className={statusClass(toolCall.status || "unknown")}>{toolCall.status || "unknown"}</span>
                  </div>
                )) : <p className="empty">No tool-call evidence loaded.</p>}
              </div>
            </div>
            <div className="panel">
              <div className="panelHeader">
                <h2><ClipboardCheck size={14} /> Evaluations</h2>
                <span>{evaluations.length}</span>
              </div>
              <div className="list compactList">
                {evaluations.length ? evaluations.slice(0, 8).map((evaluation) => (
                  <div className="row" key={evaluation.evaluation_id}>
                    <div>
                      <strong>{evaluation.evaluation_id}</strong>
                      <span>{evaluation.evaluator_type || "evaluator"} · score {Number(evaluation.score || 0)}</span>
                    </div>
                    <span className={statusClass(evaluation.pass_fail || "unknown")}>{evaluation.pass_fail || "unknown"}</span>
                  </div>
                )) : <p className="empty">No evaluation evidence loaded.</p>}
              </div>
            </div>
          </section>

          <section className="grid">
            <div className="panel">
              <div className="panelHeader">
                <h2><Package size={14} /> Artifacts</h2>
                <span>{artifacts.length}</span>
              </div>
              <div className="list compactList">
                {artifacts.length ? artifacts.slice(0, 8).map((artifact) => (
                  <div className="row" key={artifact.artifact_id}>
                    <div>
                      <strong>{artifact.title || artifact.artifact_id}</strong>
                      <span>{artifact.artifact_type || "artifact"} · {formatDate(artifact.created_at)}</span>
                    </div>
                  </div>
                )) : <p className="empty">No artifact evidence loaded.</p>}
              </div>
            </div>
            <div className="panel">
              <div className="panelHeader">
                <h2><ShieldCheck size={14} /> Audit</h2>
                <span>{auditLogs.length}</span>
              </div>
              <div className="list compactList">
                {auditLogs.length ? auditLogs.slice(0, 8).map((audit) => (
                  <div className="row" key={audit.audit_id}>
                    <div>
                      <strong>{audit.action}</strong>
                      <span>{audit.entity_type} {audit.entity_id} · {formatDate(audit.created_at)}</span>
                    </div>
                  </div>
                )) : <p className="empty">No audit evidence loaded.</p>}
              </div>
            </div>
          </section>
        </>
      )}
    </AppFrame>
  );
}
