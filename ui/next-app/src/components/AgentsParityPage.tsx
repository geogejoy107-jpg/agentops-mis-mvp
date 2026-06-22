"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Activity, Bot, FileSearch, KeyRound, Play, RefreshCw, Send, ShieldCheck, TerminalSquare, Undo2, UserPlus } from "lucide-react";
import { AppFrame } from "./AppFrame";
import {
  dispatchLocalWorkerOnce,
  loadAgentControlSnapshot,
  previewAgentGatewayEnrollmentPolicy,
  restartMockWorkerDaemon,
  releaseWorkerTask,
  requestAgentGatewayEnrollment,
  startMockWorkerDaemon,
  stopMockWorkerDaemon,
  type AgentControlSnapshot,
  type AgentGatewayEnrollmentPolicyPreview,
  type AgentGatewayEnrollmentRequestResult,
  type ReadinessGate,
} from "@/lib/mis";

type LoadState = {
  data: AgentControlSnapshot | null;
  error: string | null;
  loading: boolean;
};

const DEFAULT_ENROLLMENT_SCOPES = [
  "agents:heartbeat",
  "tasks:read",
  "tasks:claim",
  "runs:write",
  "toolcalls:write",
  "evaluations:submit",
  "audit:write",
];

const DEFAULT_ENROLLMENT_FORM = {
  agent_id: "agt_next_remote_worker",
  name: "Next Remote Worker",
  role: "Remote AI Digital Employee",
  runtime_type: "mock",
  workspace_id: "local-demo",
  scopes: DEFAULT_ENROLLMENT_SCOPES.join(", "),
  ttl_days: "30",
  heartbeat_timeout_sec: "300",
  reason: "Next worker console requested approval-gated remote agent enrollment.",
};

function statusClass(status?: string) {
  if (["ready", "running", "pass", "healthy"].includes(status || "")) return "status statusGood";
  if (["blocked", "failed", "fail", "unavailable"].includes(status || "")) return "status statusBad";
  if (["attention", "degraded", "review_required", "warn"].includes(status || "")) return "status statusWarn";
  return "status";
}

function boolStatus(value?: boolean) {
  return value ? "ready" : "attention";
}

function numberValue(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num.toLocaleString() : "0";
}

function parseScopeInput(value: string) {
  return value.split(/[\s,]+/).map((scope) => scope.trim()).filter(Boolean);
}

function GateList({ gates }: Readonly<{ gates?: ReadinessGate[] }>) {
  const rows = (gates || []).slice(0, 6);
  if (!rows.length) return <p className="empty">No readiness gates loaded.</p>;
  return (
    <div className="list compact">
      {rows.map((gate, index) => (
        <article className="row" key={`${gate.id || gate.label || "gate"}:${index}`}>
          <div>
            <strong>{gate.label || gate.id || "Readiness gate"}</strong>
            <span>{gate.detail || gate.summary || gate.next_action || gate.action || "No detail loaded."}</span>
          </div>
          <span className={statusClass(gate.status || (gate.ok ? "ready" : "attention"))}>{gate.status || (gate.ok ? "pass" : "attention")}</span>
        </article>
      ))}
    </div>
  );
}

export function AgentsParityPage() {
  const [state, setState] = useState<LoadState>({ data: null, error: null, loading: true });
  const [dispatching, setDispatching] = useState(false);
  const [releasingTaskId, setReleasingTaskId] = useState<string | null>(null);
  const [dispatchMessage, setDispatchMessage] = useState<string | null>(null);
  const [dispatchStatus, setDispatchStatus] = useState<"success" | "error" | null>(null);
  const [daemonBusy, setDaemonBusy] = useState<"start" | "stop" | "restart" | null>(null);
  const [enrollmentForm, setEnrollmentForm] = useState(DEFAULT_ENROLLMENT_FORM);
  const [enrollmentPolicy, setEnrollmentPolicy] = useState<AgentGatewayEnrollmentPolicyPreview | null>(null);
  const [enrollmentRequest, setEnrollmentRequest] = useState<AgentGatewayEnrollmentRequestResult | null>(null);
  const [enrollmentBusy, setEnrollmentBusy] = useState<"preview" | "request" | null>(null);

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      setState({ data: await loadAgentControlSnapshot(), error: null, loading: false });
    } catch (err) {
      setState({ data: null, error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("dispatch_status");
    if (status) {
      const taskId = params.get("task_id");
      const runId = params.get("run_id");
      const error = params.get("error");
      setDispatchStatus(status === "started" ? "success" : "error");
      setDispatchMessage(status === "started" ? `mock worker completed ${runId || taskId || "task"}` : `mock worker dispatch failed ${error || ""}`.trim());
    }
    const releaseStatus = params.get("release_status");
    if (releaseStatus) {
      const taskId = params.get("task_id");
      const runs = params.get("released_runs");
      const error = params.get("error");
      setDispatchStatus(releaseStatus === "released" ? "success" : "error");
      setDispatchMessage(releaseStatus === "released" ? `stuck task released ${taskId || "task"} · runs ${runs || "0"}` : `stuck task release failed ${error || ""}`.trim());
    }
    const enrollmentStatus = params.get("enrollment_status");
    if (enrollmentStatus) {
      const requestId = params.get("request_id");
      const approvalId = params.get("approval_id");
      const error = params.get("error");
      setDispatchStatus(enrollmentStatus === "requested" ? "success" : "error");
      setDispatchMessage(enrollmentStatus === "requested" ? `enrollment approval requested ${requestId || approvalId || ""}`.trim() : `enrollment request failed ${error || ""}`.trim());
    }
    const daemonStatus = params.get("daemon_status");
    if (daemonStatus) {
      const action = params.get("action");
      const pid = params.get("pid");
      const error = params.get("error");
      setDispatchStatus(["started", "stopped", "restarted"].includes(daemonStatus) ? "success" : "error");
      setDispatchMessage(["started", "stopped", "restarted"].includes(daemonStatus) ? `mock daemon ${daemonStatus} ${pid || ""}`.trim() : `mock daemon ${action || ""} failed ${error || ""}`.trim());
    }
    void refresh();
  }, []);

  const enrollmentInput = () => ({
    agent_id: enrollmentForm.agent_id.trim(),
    name: enrollmentForm.name.trim(),
    role: enrollmentForm.role.trim(),
    runtime_type: enrollmentForm.runtime_type.trim() || "mock",
    workspace_id: enrollmentForm.workspace_id.trim() || "local-demo",
    label: `${enrollmentForm.name.trim() || "Remote worker"} enrollment request`,
    scopes: parseScopeInput(enrollmentForm.scopes),
    ttl_days: Number(enrollmentForm.ttl_days) || 30,
    heartbeat_timeout_sec: Number(enrollmentForm.heartbeat_timeout_sec) || 300,
    reason: enrollmentForm.reason.trim() || DEFAULT_ENROLLMENT_FORM.reason,
  });

  const previewEnrollment = async () => {
    setEnrollmentBusy("preview");
    setDispatchStatus(null);
    setDispatchMessage(null);
    try {
      const input = enrollmentInput();
      const result = await previewAgentGatewayEnrollmentPolicy({
        workspace_id: input.workspace_id,
        runtime_type: input.runtime_type,
        scopes: input.scopes,
      });
      setEnrollmentPolicy(result);
      setDispatchStatus(result.status === "blocked" ? "error" : "success");
      setDispatchMessage(`enrollment policy ${result.recommended_path || result.status || "preview"}`);
    } catch (err) {
      setDispatchStatus("error");
      setDispatchMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setEnrollmentBusy(null);
    }
  };

  const requestEnrollment = async () => {
    setEnrollmentBusy("request");
    setDispatchStatus(null);
    setDispatchMessage(null);
    try {
      const result = await requestAgentGatewayEnrollment(enrollmentInput());
      setEnrollmentRequest(result);
      setDispatchStatus(result.token_issued ? "error" : "success");
      setDispatchMessage(`enrollment approval requested ${result.request?.request_id || result.approval?.approval_id || ""}`.trim());
      await refresh();
    } catch (err) {
      setDispatchStatus("error");
      setDispatchMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setEnrollmentBusy(null);
    }
  };

  const runMockWorkerOnce = async () => {
    setDispatching(true);
    setDispatchStatus(null);
    setDispatchMessage(null);
    try {
      const result = await dispatchLocalWorkerOnce({
        adapter: "mock",
        title: "Next mock worker dispatch task",
        description: "Triggered from the Next.js worker console parity route.",
        acceptance_criteria: "Mock worker must complete and write run/tool/evaluation/audit plus plan evidence.",
      });
      const workerResult = result.worker_result?.results?.[0];
      const runId = workerResult?.run_id || result.task_id;
      setDispatchStatus(result.ok ? "success" : "error");
      setDispatchMessage(`mock worker ${result.ok ? "completed" : "failed"} ${runId || "task"}`);
      await refresh();
    } catch (err) {
      setDispatchStatus("error");
      setDispatchMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(false);
    }
  };

  const controlMockDaemon = async (action: "start" | "stop" | "restart") => {
    setDaemonBusy(action);
    setDispatchStatus(null);
    setDispatchMessage(null);
    try {
      const result = action === "start"
        ? await startMockWorkerDaemon({ poll_interval: 2, max_tasks: 0 })
        : action === "restart"
          ? await restartMockWorkerDaemon({ poll_interval: 2, max_tasks: 0 })
          : await stopMockWorkerDaemon();
      const daemon = result.daemon || result.daemons?.[0];
      setDispatchStatus(result.ok ? "success" : "error");
      setDispatchMessage(`mock daemon ${action} ${result.ok ? "ok" : "failed"} ${daemon?.pid ? `pid ${daemon.pid}` : ""}`.trim());
      await refresh();
    } catch (err) {
      setDispatchStatus("error");
      setDispatchMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setDaemonBusy(null);
    }
  };

  const releaseStuckTask = async (taskId: string) => {
    setReleasingTaskId(taskId);
    setDispatchStatus(null);
    setDispatchMessage(null);
    try {
      const result = await releaseWorkerTask({
        task_id: taskId,
        reason: "Next worker console released stuck task",
      });
      setDispatchStatus(result.released ? "success" : "error");
      setDispatchMessage(`stuck task ${result.released ? "released" : "not released"} ${taskId} · runs ${(result.released_runs || []).length}`);
      await refresh();
    } catch (err) {
      setDispatchStatus("error");
      setDispatchMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setReleasingTaskId(null);
    }
  };

  const agents = state.data?.agents || [];
  const security = state.data?.security;
  const worker = state.data?.workerStatus;
  const stuckTasks = worker?.stuck_tasks || [];
  const adapter = state.data?.adapterReadiness;
  const enrollments = state.data?.enrollments?.enrollments || [];
  const runningDaemons = (worker?.daemons || []).filter((daemon) => daemon.running).length;
  const mockDaemon = (worker?.daemons || []).find((daemon) => daemon.adapter === "mock");
  const adapterRows = useMemo(() => Object.values(adapter?.adapters || {}), [adapter?.adapters]);

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Production safety parity route</p>
          <h1>Agents</h1>
          <p className="subtle">Read-only control plane for worker readiness, scoped execution, and production safety gates.</p>
        </div>
        <button className="iconButton" onClick={refresh} disabled={state.loading} aria-label="Refresh agents control plane">
          <RefreshCw size={17} className={state.loading ? "spin" : ""} />
        </button>
      </header>

      {state.error ? <div className="banner error">MIS API unavailable through /api/mis agent-control endpoints: {state.error}</div> : null}
      {dispatchMessage ? <div className={`banner ${dispatchStatus === "success" ? "success" : "error"}`}>{dispatchMessage}</div> : null}

      <section className="metrics">
        {[
          ["Agents", agents.length, <Bot key="agents" size={18} />, "ready"],
          ["Worker status", worker?.status || "unknown", <Activity key="workers" size={18} />, worker?.status],
          ["Production", security?.production_ready ? "ready" : "local", <ShieldCheck key="security" size={18} />, boolStatus(security?.production_ready)],
          ["Adapter", adapter?.summary?.recommended_adapter || worker?.adapter_readiness?.recommended_adapter || "mock", <TerminalSquare key="adapter" size={18} />, adapter?.status],
        ].map(([label, value, icon, status]) => (
          <div className="metric" key={String(label)}>
            <span className="metricIcon">{icon}</span>
            <span>{label}</span>
            <strong className="metricText">{state.loading && !state.data ? "..." : String(value)}</strong>
            <span className={statusClass(String(status || "unknown"))}>{String(status || "unknown")}</span>
          </div>
        ))}
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><ShieldCheck size={14} /> Production security</h2>
            <span>{security?.auth_mode || "auth unknown"}</span>
          </div>
          <p className="subtle">{security?.contract || "Production mode must fail closed before shared deployment."}</p>
          <div className="proofStrip">
            <span className={statusClass(security?.safety?.read_only ? "ready" : "attention")}>read only</span>
            <span className={statusClass(security?.safety?.token_omitted ? "ready" : "attention")}>token omitted</span>
            <span className={statusClass(security?.safety?.live_execution_performed === false ? "ready" : "attention")}>no live execution</span>
          </div>
          <GateList gates={security?.gates} />
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2><Activity size={14} /> Worker fleet</h2>
            <span>{worker?.fleet_health?.overall || worker?.status || "unknown"}</span>
          </div>
          <div className="miniMetrics">
            <span>workers <strong>{numberValue(worker?.worker_count)}</strong></span>
            <span>daemons <strong>{runningDaemons}/{numberValue(worker?.daemons?.length)}</strong></span>
            <span>pending <strong>{numberValue(worker?.pending_worker_tasks)}</strong></span>
            <span>stuck <strong>{numberValue(worker?.stuck_worker_tasks)}</strong></span>
            <span>remote <strong>{numberValue(worker?.remote_worker_count)}</strong></span>
            <span>sessions <strong>{numberValue(worker?.active_remote_sessions)}</strong></span>
          </div>
          <GateList gates={worker?.fleet_health?.gates} />
          <div className="proofStrip">
            <button className="miniButton good" type="button" onClick={runMockWorkerOnce} disabled={dispatching} data-smoke="run-mock-worker-once">
              <Play size={13} /> {dispatching ? "Running mock" : "Run mock once"}
            </button>
            <form className="inlineForm" method="post" action="/workspace/agents/dispatch-once" data-smoke="mock-worker-form-fallback">
              <input type="hidden" name="adapter" value="mock" />
              <button className="miniButton" type="submit" disabled={dispatching}>
                <Play size={13} /> Form fallback
              </button>
            </form>
          </div>
          <div className="proofStrip" data-smoke="mock-daemon-controls">
            <button className="miniButton good" type="button" onClick={() => controlMockDaemon("start")} disabled={Boolean(daemonBusy)} data-smoke="start-mock-daemon">
              <Play size={13} /> {daemonBusy === "start" ? "Starting" : "Start mock"}
            </button>
            <button className="miniButton" type="button" onClick={() => controlMockDaemon("restart")} disabled={Boolean(daemonBusy)} data-smoke="restart-mock-daemon">
              <RefreshCw size={13} /> {daemonBusy === "restart" ? "Restarting" : "Restart mock"}
            </button>
            <button className="miniButton bad" type="button" onClick={() => controlMockDaemon("stop")} disabled={Boolean(daemonBusy)} data-smoke="stop-mock-daemon">
              <Undo2 size={13} /> {daemonBusy === "stop" ? "Stopping" : "Stop mock"}
            </button>
            <form className="inlineForm" method="post" action="/workspace/agents/daemon-control" data-smoke="mock-daemon-form-fallback">
              <input type="hidden" name="action" value="start" />
              <input type="hidden" name="adapter" value="mock" />
              <input type="hidden" name="poll_interval" value="2" />
              <input type="hidden" name="max_tasks" value="0" />
              <button className="miniButton" type="submit" disabled={Boolean(daemonBusy)}>
                <Play size={13} /> Start form
              </button>
            </form>
            <form className="inlineForm" method="post" action="/workspace/agents/daemon-control" data-smoke="mock-daemon-restart-form">
              <input type="hidden" name="action" value="restart" />
              <input type="hidden" name="adapter" value="mock" />
              <input type="hidden" name="poll_interval" value="2" />
              <input type="hidden" name="max_tasks" value="0" />
              <button className="miniButton" type="submit" disabled={Boolean(daemonBusy)}>
                <RefreshCw size={13} /> Restart form
              </button>
            </form>
            <form className="inlineForm" method="post" action="/workspace/agents/daemon-control" data-smoke="mock-daemon-stop-form">
              <input type="hidden" name="action" value="stop" />
              <input type="hidden" name="adapter" value="mock" />
              <button className="miniButton bad" type="submit" disabled={Boolean(daemonBusy)}>
                <Undo2 size={13} /> Stop form
              </button>
            </form>
            <span className={statusClass("blocked")}>live daemon blocked</span>
          </div>
          {mockDaemon ? (
            <div className="list compact">
              <article className="row" data-smoke="mock-daemon-status">
                <div>
                  <strong>Mock daemon</strong>
                  <span>{mockDaemon.agent_id || "agt_worker_daemon_mock"} · pid {mockDaemon.pid || "none"} · processed {numberValue(mockDaemon.processed)} · iteration {numberValue(mockDaemon.iteration)}</span>
                </div>
                <span className={statusClass(mockDaemon.running ? "running" : mockDaemon.status)}>{mockDaemon.running ? "running" : mockDaemon.status || "stopped"}</span>
              </article>
            </div>
          ) : null}
          <div className="list compact">
            {stuckTasks.length === 0 ? (
              <article className="row">
                <div>
                  <strong>No stuck worker tasks</strong>
                  <span>Worker recovery is idle; release remains available through the guarded Next route.</span>
                </div>
                <span className="status statusGood">clear</span>
              </article>
            ) : null}
            {stuckTasks.slice(0, 4).map((task) => (
              <article className="row" key={task.task_id}>
                <div>
                  <strong>{task.title || task.task_id}</strong>
                  <span>{task.task_id} · {task.owner_agent_id || "unassigned"} · age {numberValue(task.age_sec)}s · run {task.running_run_id || "none"}</span>
                </div>
                <div className="proofStrip">
                  <button className="miniButton" type="button" onClick={() => releaseStuckTask(task.task_id)} disabled={Boolean(releasingTaskId)} data-smoke="release-stuck-worker-task">
                    <Undo2 size={13} /> {releasingTaskId === task.task_id ? "Releasing" : "Release"}
                  </button>
                  <form className="inlineForm" method="post" action="/workspace/agents/release-task" data-smoke="release-stuck-worker-form">
                    <input type="hidden" name="task_id" value={task.task_id} />
                    <button className="miniButton" type="submit" disabled={Boolean(releasingTaskId)}>
                      <Undo2 size={13} /> Form
                    </button>
                  </form>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><UserPlus size={14} /> Remote enrollment request</h2>
          <span>approval gated</span>
        </div>
        <div className="miniMetrics">
          <span>active <strong>{numberValue(worker?.active_remote_enrollments)}</strong></span>
          <span>fresh <strong>{numberValue(worker?.fresh_remote_enrollments)}</strong></span>
          <span>stale <strong>{numberValue(worker?.stale_remote_enrollments)}</strong></span>
          <span>visible tokens <strong>{numberValue(enrollments.length)}</strong></span>
        </div>
        <div className="formGrid" data-smoke="enrollment-request-panel">
          <label className="field">
            <span>Agent ID</span>
            <input value={enrollmentForm.agent_id} onChange={(event) => setEnrollmentForm((current) => ({ ...current, agent_id: event.target.value }))} />
          </label>
          <label className="field">
            <span>Name</span>
            <input value={enrollmentForm.name} onChange={(event) => setEnrollmentForm((current) => ({ ...current, name: event.target.value }))} />
          </label>
          <label className="field">
            <span>Runtime</span>
            <select value={enrollmentForm.runtime_type} onChange={(event) => setEnrollmentForm((current) => ({ ...current, runtime_type: event.target.value }))}>
              <option value="mock">mock</option>
              <option value="hermes">hermes</option>
              <option value="openclaw">openclaw</option>
            </select>
          </label>
          <label className="field">
            <span>Workspace</span>
            <input value={enrollmentForm.workspace_id} onChange={(event) => setEnrollmentForm((current) => ({ ...current, workspace_id: event.target.value }))} />
          </label>
          <label className="field">
            <span>TTL days</span>
            <input inputMode="numeric" value={enrollmentForm.ttl_days} onChange={(event) => setEnrollmentForm((current) => ({ ...current, ttl_days: event.target.value }))} />
          </label>
          <label className="field">
            <span>Heartbeat sec</span>
            <input inputMode="numeric" value={enrollmentForm.heartbeat_timeout_sec} onChange={(event) => setEnrollmentForm((current) => ({ ...current, heartbeat_timeout_sec: event.target.value }))} />
          </label>
          <label className="field wideField">
            <span>Scopes</span>
            <input value={enrollmentForm.scopes} onChange={(event) => setEnrollmentForm((current) => ({ ...current, scopes: event.target.value }))} />
          </label>
          <label className="field wideField">
            <span>Reason</span>
            <input value={enrollmentForm.reason} onChange={(event) => setEnrollmentForm((current) => ({ ...current, reason: event.target.value }))} />
          </label>
        </div>
        <div className="proofStrip">
          <button className="miniButton" type="button" onClick={previewEnrollment} disabled={Boolean(enrollmentBusy)} data-smoke="preview-enrollment-policy">
            <FileSearch size={13} /> {enrollmentBusy === "preview" ? "Previewing" : "Preview policy"}
          </button>
          <button className="miniButton good" type="button" onClick={requestEnrollment} disabled={Boolean(enrollmentBusy)} data-smoke="request-enrollment-approval">
            <Send size={13} /> {enrollmentBusy === "request" ? "Requesting" : "Request approval"}
          </button>
          <form className="inlineForm" method="post" action="/workspace/agents/enrollment-request" data-smoke="enrollment-request-form-fallback">
            {Object.entries(enrollmentForm).map(([name, value]) => (
              <input key={name} type="hidden" name={name} value={value} />
            ))}
            <button className="miniButton" type="submit" disabled={Boolean(enrollmentBusy)}>
              <Send size={13} /> Form fallback
            </button>
          </form>
          <span className={statusClass("ready")}>token omitted</span>
          <span className={statusClass("blocked")}>direct token issue blocked</span>
        </div>
        {enrollmentPolicy ? (
          <>
            <div className="adapterGrid" data-smoke="enrollment-policy-result">
              <article className="adapterCard">
                <div>
                  <strong>{enrollmentPolicy.policy || "policy"}</strong>
                  <span>{enrollmentPolicy.recommended_path || "recommended path pending"}</span>
                </div>
                <span className={statusClass(enrollmentPolicy.status)}>{enrollmentPolicy.status || "unknown"}</span>
                <div className="proofStrip">
                  <span className={statusClass(enrollmentPolicy.safety?.read_only ? "ready" : "attention")}>read only</span>
                  <span className={statusClass(enrollmentPolicy.safety?.ledger_mutated === false ? "ready" : "attention")}>ledger unchanged</span>
                  <span className={statusClass(enrollmentPolicy.token_omitted ? "ready" : "attention")}>token omitted</span>
                </div>
              </article>
              <article className="adapterCard">
                <div>
                  <strong>{enrollmentPolicy.risk_level || "risk"}</strong>
                  <span>{numberValue(enrollmentPolicy.scope_count)} scopes · {enrollmentPolicy.approval_recommended ? "approval recommended" : "direct local path"}</span>
                </div>
                <span className={statusClass(enrollmentPolicy.approval_recommended ? "attention" : "ready")}>{enrollmentPolicy.recommended_path || "policy"}</span>
                <div className="proofStrip">
                  <span>worker writes {numberValue(enrollmentPolicy.worker_write_scopes?.length)}</span>
                  <span>invalid {numberValue(enrollmentPolicy.invalid_scopes?.length)}</span>
                </div>
              </article>
            </div>
            <GateList gates={enrollmentPolicy.gates} />
          </>
        ) : null}
        {enrollmentRequest?.request ? (
          <div className="list compact" data-smoke="enrollment-request-result">
            <article className="row">
              <div>
                <strong>{enrollmentRequest.request.name || enrollmentRequest.request.agent_id}</strong>
                <span>{enrollmentRequest.request.request_id} · approval {enrollmentRequest.request.approval_id} · task {enrollmentRequest.request.task_id}</span>
              </div>
              <span className={statusClass(enrollmentRequest.token_issued ? "blocked" : "attention")}>{enrollmentRequest.request.status || "pending"}</span>
            </article>
          </div>
        ) : null}
        <div className="list compact">
          {enrollments.slice(0, 4).map((enrollment) => (
            <article className="row" key={enrollment.token_id || enrollment.token_ref || enrollment.agent_id}>
              <div>
                <strong>{enrollment.label || enrollment.agent_id || "remote enrollment"}</strong>
                <span>{enrollment.agent_id || "agent"} · {enrollment.workspace_id || "workspace"} · heartbeat {enrollment.heartbeat_state || "unknown"}</span>
              </div>
              <span className={statusClass(enrollment.status)}>{enrollment.status || "unknown"}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><TerminalSquare size={14} /> Adapter readiness</h2>
          <span>recommended {adapter?.summary?.recommended_adapter || "mock"}</span>
        </div>
        <div className="adapterGrid">
          {adapterRows.map((item) => (
            <article className="adapterCard" key={item.adapter || "adapter"}>
              <div>
                <strong>{item.adapter || "adapter"}</strong>
                <span>{item.recommended_action || "agentops worker readiness"}</span>
              </div>
              <span className={statusClass(item.readiness)}>{item.readiness || "unknown"}</span>
              <div className="proofStrip">
                <span className={statusClass(item.token_omitted ? "ready" : "attention")}>token omitted</span>
                <span className={statusClass(item.requires_confirm_run ? "attention" : "ready")}>{item.requires_confirm_run ? "confirm required" : "safe default"}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><KeyRound size={14} /> Agent registry</h2>
          <span>{agents.length} visible</span>
        </div>
        <div className="list compact">
          {agents.slice(0, 12).map((agent) => (
            <Link className="row linkRow" href={`/workspace/agents/${encodeURIComponent(agent.agent_id)}`} key={agent.agent_id}>
              <div>
                <strong>{agent.name || agent.agent_id}</strong>
                <span>{agent.agent_id} · {agent.role || "agent"} · {agent.runtime_type || "runtime"}</span>
              </div>
              <span className={statusClass(agent.status)}>{agent.status || "unknown"}</span>
            </Link>
          ))}
        </div>
      </section>
    </AppFrame>
  );
}
