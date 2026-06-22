import Link from "next/link";
import { ArrowLeft, ClipboardList, GitBranch, ShieldCheck } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type { RunDetailSnapshot, TaskDetailPayload } from "@/lib/mis";

function count(value: unknown) {
  return Array.isArray(value) ? value.length : Number(value || 0);
}

function statusClass(status: string) {
  if (["completed", "approved", "verified", "ready"].includes(status)) return "status statusGood";
  if (["failed", "blocked", "rejected"].includes(status)) return "status statusBad";
  if (["running", "waiting_approval", "pending", "warning"].includes(status)) return "status statusWarn";
  return "status";
}

function formatMs(value?: number | null) {
  return value ? `${(value / 1000).toFixed(1)}s` : "-";
}

function JsonPreview({ value }: Readonly<{ value: unknown }>) {
  return <pre className="jsonPreview">{JSON.stringify(value || {}, null, 2).slice(0, 2200)}</pre>;
}

export function TaskDetailPage({
  taskId,
  detail,
  error,
}: Readonly<{ taskId: string; detail: TaskDetailPayload | null; error?: string | null }>) {
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
        <Link className="miniButton" href="/workspace/runs">Run ledger</Link>
      </header>
      {error || detail?.error || !task ? <div className="banner error">{error || detail?.error || "Task not found"}</div> : (
        <>
          <section className="metrics six">
            {[
              ["Runs", runs.length],
              ["Approvals", approvals.length],
              ["Evaluations", count(detail?.evaluations)],
              ["Memories", count(detail?.memories)],
              ["Artifacts", artifacts.length],
              ["Token omitted", detail?.token_omitted === false ? "false" : "true"],
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
              <JsonPreview value={approvals.slice(0, 6)} />
            </div>
            <div className="panel">
              <div className="panelHeader">
                <h2><ShieldCheck size={14} /> Artifacts</h2>
                <span>{artifacts.length}</span>
              </div>
              <JsonPreview value={artifacts.slice(0, 6)} />
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
}: Readonly<{ runId: string; snapshot: RunDetailSnapshot; error?: string | null }>) {
  const detail = snapshot.detail;
  const graph = snapshot.graph;
  const run = detail?.run || graph?.run;
  const task = detail?.task || graph?.task;

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <Link className="backLink" href="/workspace/runs"><ArrowLeft size={14} /> Runs</Link>
          <p className="eyebrow">Read-only run detail</p>
          <h1>Run Detail</h1>
          <p className="subtle">{runId}</p>
        </div>
        {task?.task_id ? <Link className="miniButton" href={`/workspace/tasks/${encodeURIComponent(task.task_id)}`}>Open task</Link> : null}
      </header>
      {error || detail?.error || graph?.error || !run ? <div className="banner error">{error || detail?.error || graph?.error || "Run not found"}</div> : (
        <>
          <section className="metrics nine">
            {[
              ["Tool calls", count(detail?.tool_calls)],
              ["Evaluations", count(detail?.evaluations)],
              ["Artifacts", count(detail?.artifacts)],
              ["Approvals", count(detail?.approvals)],
              ["Audit logs", count(detail?.audit_logs)],
              ["Runtime events", count(detail?.runtime_events)],
              ["Children", count(graph?.children)],
              ["Siblings", count(graph?.siblings_by_delegation)],
              ["Token omitted", detail?.token_omitted === false || graph?.token_omitted === false ? "false" : "true"],
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
              <p className="subtle">{run.output_summary || run.input_summary || "No run summary loaded."}</p>
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
              <p className="subtle">{task?.title || task?.description || "Task readback not loaded."}</p>
            </div>
          </section>

          <section className="grid">
            <div className="panel">
              <div className="panelHeader">
                <h2><ShieldCheck size={14} /> Tool and evaluation evidence</h2>
              </div>
              <JsonPreview value={{ tool_calls: detail?.tool_calls || [], evaluations: detail?.evaluations || [] }} />
            </div>
            <div className="panel">
              <div className="panelHeader">
                <h2><ShieldCheck size={14} /> Audit and artifact evidence</h2>
              </div>
              <JsonPreview value={{ artifacts: detail?.artifacts || [], audit_logs: detail?.audit_logs || [] }} />
            </div>
          </section>
        </>
      )}
    </AppFrame>
  );
}
