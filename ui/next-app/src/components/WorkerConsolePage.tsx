import { Activity, KeyRound, ServerCog, ShieldCheck, TerminalSquare, Workflow, Wrench } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type {
  AgentGatewaySessionsPayload,
  LocalReadinessPayload,
  OperatorExecutionModePayload,
  WorkerAdapterReadinessSummary,
  WorkerFleetHygienePayload,
  WorkerFleetPayload,
  WorkerStatusSummary,
} from "@/lib/mis";
import type { ServerLoadResult } from "@/lib/misServer";

type WorkerConsoleProps = {
  workerStatus: ServerLoadResult<WorkerStatusSummary>;
  workerFleet: ServerLoadResult<WorkerFleetPayload>;
  workerHygiene: ServerLoadResult<WorkerFleetHygienePayload>;
  adapterReadiness: ServerLoadResult<WorkerAdapterReadinessSummary>;
  executionMode: ServerLoadResult<OperatorExecutionModePayload>;
  sessions: ServerLoadResult<AgentGatewaySessionsPayload>;
  localReadiness: ServerLoadResult<LocalReadinessPayload>;
};

function statusClass(status?: string | boolean) {
  const value = String(status ?? "").toLowerCase();
  if (["true", "ok", "ready", "running", "pass", "healthy", "clear"].includes(value)) return "status statusGood";
  if (["false", "blocked", "failed", "fail", "unavailable", "error"].includes(value)) return "status statusBad";
  if (["attention", "degraded", "review_required", "warn", "pending"].includes(value)) return "status statusWarn";
  return "status";
}

function numberValue(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num.toLocaleString() : "0";
}

function boolLabel(value: unknown) {
  if (value === true) return "true";
  if (value === false) return "false";
  return "unknown";
}

function titleize(value: string) {
  return value.replace(/[_-]/g, " ");
}

function errorsFrom(results: WorkerConsoleProps) {
  return [
    ["worker status", results.workerStatus.error],
    ["worker fleet", results.workerFleet.error],
    ["fleet hygiene", results.workerHygiene.error],
    ["adapter readiness", results.adapterReadiness.error],
    ["execution mode", results.executionMode.error],
    ["gateway sessions", results.sessions.error],
    ["local readiness", results.localReadiness.error],
  ].filter(([, error]) => Boolean(error));
}

export function WorkerConsolePage(props: Readonly<WorkerConsoleProps>) {
  const workerStatus = props.workerStatus.data;
  const workerFleet = props.workerFleet.data;
  const workerHygiene = props.workerHygiene.data;
  const adapterReadiness = props.adapterReadiness.data;
  const executionMode = props.executionMode.data;
  const sessions = props.sessions.data.sessions || [];
  const localReadiness = props.localReadiness.data;
  const errors = errorsFrom(props);

  const daemons = workerStatus.daemons || [];
  const runningDaemons = daemons.filter((daemon) => daemon.running || daemon.status === "running").length;
  const fleetSummary = workerFleet.summary || {};
  const hygieneSummary = workerHygiene.summary || {};
  const lanes = workerFleet.lanes || [];
  const adapterEntries = Object.entries(adapterReadiness.adapters || {}).sort(([left], [right]) => left.localeCompare(right));
  const executionRoute = executionMode.adapter_route || {};
  const executionSummary = executionMode.summary || {};
  const stuckTasks = workerHygiene.stuck_tasks || workerStatus.stuck_tasks || [];
  const staleEnrollments = workerHygiene.stale_never_seen_enrollments || [];
  const sessionStateCounts = sessions.reduce<Record<string, number>>((acc, session) => {
    const state = session.session_state || session.status || "unknown";
    acc[state] = (acc[state] || 0) + 1;
    return acc;
  }, {});

  return (
    <AppFrame>
      <header className="topbar" data-smoke="worker-console-route">
        <div>
          <p className="eyebrow">Gate 4 worker console parity</p>
          <h1>Worker Console</h1>
          <p className="subtle">Next.js read model for worker fleet, adapter readiness, session hygiene, and fail-closed lifecycle controls.</p>
        </div>
        <span className={statusClass(workerFleet.status || workerStatus.status)}>{workerFleet.status || workerStatus.status || "unknown"}</span>
      </header>

      {errors.length ? (
        <div className="banner warn">
          {errors.map(([label, error]) => `${label}: ${error}`).join(" · ")}
        </div>
      ) : null}

      <section className="metrics six" data-smoke="worker-fleet-summary">
        {[
          ["Worker status", workerStatus.status || "unknown", <Activity key="worker-status" size={18} />, workerStatus.status],
          ["Fleet lanes", numberValue(fleetSummary.lane_count ?? lanes.length), <Workflow key="fleet-lanes" size={18} />, workerFleet.status],
          ["Running daemons", `${runningDaemons}/${numberValue(daemons.length)}`, <ServerCog key="daemons" size={18} />, runningDaemons ? "running" : "attention"],
          ["Remote sessions", numberValue(fleetSummary.active_remote_sessions ?? sessions.length), <KeyRound key="sessions" size={18} />, sessions.length ? "ready" : "attention"],
          ["Hygiene actions", numberValue(hygieneSummary.actions_available), <Wrench key="hygiene" size={18} />, hygieneSummary.actions_available ? "attention" : "clear"],
          ["Execution mode", executionMode.selected_adapter || adapterReadiness.summary?.recommended_adapter || "mock", <TerminalSquare key="adapter" size={18} />, executionMode.status],
        ].map(([label, value, icon, status]) => (
          <div className="metric compactMetric" key={String(label)}>
            <span className="metricIcon">{icon}</span>
            <span>{label}</span>
            <strong className="metricText">{String(value)}</strong>
            <span className={statusClass(String(status || "unknown"))}>{String(status || "unknown")}</span>
          </div>
        ))}
      </section>

      <section className="grid">
        <div className="panel" data-smoke="worker-console-read-model">
          <div className="panelHeader">
            <h2><ShieldCheck size={14} /> Worker read model</h2>
            <span>worker_console_read_model_parity</span>
          </div>
          <p className="subtle">Next reads the worker API contracts without issuing tokens, creating sessions, or executing live controls.</p>
          <div className="proofStrip">
            <span className={statusClass(workerFleet.safety?.read_only)}>read only</span>
            <span className={statusClass(workerFleet.token_omitted || workerFleet.safety?.token_omitted)}>token omitted</span>
            <span className={statusClass(workerFleet.live_execution_performed === false || workerFleet.safety?.live_execution_performed === false)}>no live execution</span>
            <span className={statusClass(workerFleet.safety?.session_id_omitted)}>session id hidden</span>
            <span>{workerFleet.contract || "fleet contract pending"}</span>
          </div>
          <div className="miniMetrics">
            <span>local daemons <strong>{numberValue(fleetSummary.local_daemon_count)}</strong></span>
            <span>remote workers <strong>{numberValue(fleetSummary.remote_worker_count)}</strong></span>
            <span>fresh enrollments <strong>{numberValue(fleetSummary.fresh_remote_enrollments)}</strong></span>
            <span>stale enrollments <strong>{numberValue(fleetSummary.stale_remote_enrollments)}</strong></span>
          </div>
        </div>

        <div className="panel" data-smoke="worker-local-readiness-proof">
          <div className="panelHeader">
            <h2><ShieldCheck size={14} /> Local readiness</h2>
            <span>{localReadiness.contract || "local readiness contract"}</span>
          </div>
          <p className="subtle">This is a readback proof only; real Hermes/OpenClaw acceptance remains an explicit runtime lane.</p>
          <div className="proofStrip">
            <span className={statusClass(localReadiness.ok || localReadiness.status)}>{localReadiness.status || (localReadiness.ok ? "ok" : "unknown")}</span>
            <span className={statusClass(localReadiness.token_omitted)}>token omitted</span>
            <span className={statusClass(localReadiness.live_execution_performed === false)}>no live execution</span>
            <span>recommended {localReadiness.adapter_readiness?.recommended_adapter || adapterReadiness.summary?.recommended_adapter || "mock"}</span>
          </div>
          <div className="list compact">
            {(localReadiness.gates || workerStatus.fleet_health?.gates || []).slice(0, 4).map((gate, index) => (
              <article className="row" key={`${gate.id || gate.label || "gate"}:${index}`}>
                <div>
                  <strong>{gate.label || gate.id || "Readiness gate"}</strong>
                  <span>{gate.detail || gate.summary || gate.next_action || gate.action || "No detail loaded."}</span>
                </div>
                <span className={statusClass(gate.status || gate.ok)}>{gate.status || (gate.ok ? "pass" : "attention")}</span>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="panel wide" data-smoke="worker-console-live-boundary">
        <div className="panelHeader">
          <h2><Wrench size={14} /> Lifecycle boundary</h2>
          <span>fail closed</span>
        </div>
        <div className="proofStrip">
          <span className={statusClass("blocked")}>live daemon blocked</span>
          <span className={statusClass("blocked")}>direct token issue blocked</span>
          <span className={statusClass("blocked")}>session create blocked</span>
          <span className={statusClass("blocked")}>session revoke blocked</span>
          <span className={statusClass("blocked")}>enrollment revoke blocked</span>
          <span className={statusClass("attention")}>fleet cleanup preview only</span>
          <span className={statusClass(executionMode.safety?.read_only)}>operator execution-mode readback</span>
        </div>
        <p className="subtle">
          mock_daemon_only_next_parity · live_worker_daemon_not_allowed_next_parity · gateway_lifecycle_write_not_allowed_next_parity · Vite/CLI remain canonical for live lifecycle mutation.
        </p>
      </section>

      <section className="panel wide" data-smoke="worker-console-coverage-boundary">
        <div className="panelHeader">
          <h2><TerminalSquare size={14} /> Worker Console coverage boundary</h2>
          <span>covered, retirement blocked</span>
        </div>
        <p className="subtle">
          Next covers the commercial worker console through split routes and guarded actions while preserving Agent Gateway CLI/API/MCP as the durable execution contract for live lifecycle mutation.
        </p>
        <div className="proofStrip">
          <span>/workspace/agents remote enrollment approval request</span>
          <span>/workspace/agents mock worker dispatch and daemon controls</span>
          <span>/workspace/workers fleet/readiness/hygiene cockpit</span>
          <span>Agent Gateway CLI/API/MCP canonical for token issue/rotate/revoke</span>
          <span>Agent Gateway CLI/API/MCP canonical for session lifecycle</span>
          <span>live daemon lifecycle requires CLI/API operator lane</span>
          <span>Vite route retirement blocked</span>
        </div>
        <div className="miniMetrics">
          <span>safe readbacks <strong>/workers/fleet</strong></span>
          <span>hygiene <strong>preview only</strong></span>
          <span>tokens <strong>approval gated</strong></span>
          <span>sessions <strong>safe refs only</strong></span>
          <span>live adapters <strong>prepared-action wall</strong></span>
          <span>route state <strong>covered</strong></span>
        </div>
      </section>

      <section className="panel wide" data-smoke="operator-execution-mode-readback">
        <div className="panelHeader">
          <h2><TerminalSquare size={14} /> Operator execution mode</h2>
          <span>{executionMode.operation || "/operator/execution-mode"}</span>
        </div>
        <div className="miniMetrics">
          <span>adapter <strong>{executionMode.selected_adapter || executionRoute.adapter || "mock"}</strong></span>
          <span>readiness <strong>{executionRoute.readiness || "unknown"}</strong></span>
          <span>trust <strong>{titleize(executionRoute.trust_status || "unknown")}</strong></span>
          <span>pending approvals <strong>{numberValue(executionSummary.pending_approvals)}</strong></span>
          <span>active jobs <strong>{numberValue(executionSummary.active_async_jobs)}</strong></span>
          <span>approved actions <strong>{numberValue(executionSummary.approved_prepared_actions)}</strong></span>
        </div>
        <div className="proofStrip">
          <span>/operator/execution-mode</span>
          <span className={statusClass(executionMode.safety?.read_only)}>read only</span>
          <span className={statusClass(executionMode.safety?.ledger_mutated === false)}>ledger not mutated</span>
          <span className={statusClass(executionMode.safety?.daemon_started === false)}>daemon not started</span>
          <span className={statusClass(executionMode.safety?.adapter_executed === false)}>adapter not executed</span>
          <span className={statusClass(executionMode.safety?.live_execution_performed === false)}>no live execution</span>
          <span className={statusClass(executionMode.token_omitted)}>token omitted</span>
        </div>
        <div className="grid tightGrid">
          <article className="row tall">
            <div>
              <strong>Confirm-run wall</strong>
              <span>{executionRoute.confirm_run_wall?.reason || "Live adapters require explicit confirmation before execution."}</span>
              <p>{executionRoute.recommended_command || "agentops operator execution-mode"}</p>
            </div>
            <span className={statusClass(executionRoute.confirm_run_wall?.required ? "attention" : "ready")}>{executionRoute.confirm_run_wall?.required ? "confirm required" : "ready"}</span>
          </article>
          <article className="row tall">
            <div>
              <strong>Prepared-action wall</strong>
              <span>{numberValue(executionRoute.prepared_action_wall?.pending_actions)} waiting · {numberValue(executionRoute.prepared_action_wall?.approved_actions)} approved</span>
              <p>{executionRoute.prepared_action_wall?.resume_command || "agentops workflow customer-worker-task --help"}</p>
            </div>
            <span className={statusClass(executionRoute.prepared_action_wall?.required_for_live_customer_worker ? "attention" : "ready")}>{executionRoute.prepared_action_wall?.required_for_live_customer_worker ? "approval wall" : "not required"}</span>
          </article>
        </div>
        <div className="list compact">
          {(executionMode.gates || []).slice(0, 5).map((gate, index) => (
            <article className="row" key={`${gate.id || gate.label || "execution-mode"}:${index}`}>
              <div>
                <strong>{gate.label || gate.id || "Execution-mode gate"}</strong>
                <span>{gate.detail || gate.summary || gate.next_action || gate.action || "No detail loaded."}</span>
              </div>
              <span className={statusClass(gate.status || gate.ok)}>{gate.status || (gate.ok ? "pass" : "attention")}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="grid">
        <div className="panel" data-smoke="worker-console-fleet-lanes">
          <div className="panelHeader">
            <h2><Workflow size={14} /> Worker fleet lanes</h2>
            <span>{workerFleet.operation || "/workers/fleet"}</span>
          </div>
          <div className="list compact">
            {lanes.length ? lanes.slice(0, 8).map((lane) => (
              <article className="row" key={lane.lane_id || lane.safe_ref || `${lane.adapter}:${lane.agent_id}`}>
                <div>
                  <strong>{lane.agent_name || lane.agent_id || lane.lane_id || "Worker lane"}</strong>
                  <span>{lane.safe_ref || "safe_ref pending"} · {lane.adapter || "adapter unknown"} · {lane.workspace_id || "workspace unknown"} · sessions {numberValue(lane.active_session_count)}</span>
                </div>
                <span className={statusClass(lane.health || lane.status)}>{lane.health || lane.status || "unknown"}</span>
              </article>
            )) : (
              <article className="row">
                <div>
                  <strong>No worker fleet lanes yet</strong>
                  <span>Fleet readback is empty; the Next route still proves the safe read-only contract.</span>
                </div>
                <span className="status statusWarn">empty</span>
              </article>
            )}
          </div>
          <div className="proofStrip">
            <span>/workers/fleet</span>
            <span className={statusClass(workerFleet.token_omitted)}>token omitted</span>
            <span className={statusClass(workerFleet.live_execution_performed === false)}>no live execution</span>
          </div>
        </div>

        <div className="panel" data-smoke="worker-console-hygiene-plan">
          <div className="panelHeader">
            <h2><Wrench size={14} /> Fleet hygiene plan</h2>
            <span>{workerHygiene.operation || "/workers/fleet/hygiene"}</span>
          </div>
          <div className="miniMetrics">
            <span>stuck tasks <strong>{numberValue(hygieneSummary.stuck_tasks)}</strong></span>
            <span>stale enrollments <strong>{numberValue(hygieneSummary.stale_never_seen_enrollments)}</strong></span>
            <span>actions <strong>{numberValue(hygieneSummary.actions_available)}</strong></span>
            <span>threshold <strong>{numberValue(workerHygiene.threshold_sec)}s</strong></span>
          </div>
          <div className="proofStrip">
            <span>/workers/fleet/hygiene</span>
            <span className={statusClass(workerHygiene.safety?.read_only)}>fleet hygiene read-only</span>
            <span className={statusClass(workerHygiene.safety?.requires_confirm_cleanup)}>confirm cleanup required</span>
            <span className={statusClass(workerHygiene.live_execution_performed === false || workerHygiene.safety?.live_execution_performed === false)}>cleanup not executed</span>
            <span className={statusClass(workerHygiene.token_omitted || workerHygiene.safety?.token_omitted)}>token omitted</span>
          </div>
          <div className="list compact">
            {stuckTasks.slice(0, 4).map((task) => (
              <article className="row" key={task.task_id}>
                <div>
                  <strong>{task.title || task.task_id}</strong>
                  <span>{task.task_id} · age {numberValue(task.age_sec)}s · run {task.running_run_id || "none"}</span>
                </div>
                <span className={statusClass("attention")}>{task.stuck_reason || "stuck"}</span>
              </article>
            ))}
            {staleEnrollments.slice(0, 3).map((enrollment) => (
              <article className="row" key={enrollment.token_ref || enrollment.agent_id}>
                <div>
                  <strong>{enrollment.agent_id || "Remote enrollment"}</strong>
                  <span>{enrollment.token_ref || "token_ref hidden"} · {enrollment.runtime_type || "runtime"} · {enrollment.heartbeat_state || "heartbeat unknown"}</span>
                </div>
                <span className={statusClass("attention")}>stale</span>
              </article>
            ))}
            {!stuckTasks.length && !staleEnrollments.length ? (
              <article className="row">
                <div>
                  <strong>No cleanup actions</strong>
                  <span>fleet cleanup preview only; mutation remains CLI/Vite canonical until route retirement evidence.</span>
                </div>
                <span className="status statusGood">clear</span>
              </article>
            ) : null}
          </div>
        </div>
      </section>

      <section className="grid">
        <div className="panel" data-smoke="worker-console-session-hygiene">
          <div className="panelHeader">
            <h2><KeyRound size={14} /> Remote heartbeat sessions</h2>
            <span>{sessions.length} safe refs</span>
          </div>
          <div className="proofStrip">
            <span className={statusClass(props.sessions.data.token_omitted)}>session token omitted</span>
            <span className={statusClass("ready")}>session id hidden</span>
            <span>active {numberValue(sessionStateCounts.active)}</span>
            <span>revoked {numberValue(sessionStateCounts.revoked)}</span>
            <span>expired {numberValue(sessionStateCounts.expired)}</span>
          </div>
          <div className="list compact">
            {sessions.length ? sessions.slice(0, 6).map((session) => (
              <article className="row" key={session.session_ref || `${session.agent_id}:${session.created_at}`}>
                <div>
                  <strong>{session.agent_id || "Remote worker session"}</strong>
                  <span>{session.session_ref || "session_ref hidden"} · {session.parent_token_ref || "token_ref hidden"} · scopes {numberValue(session.scope_count ?? session.scopes?.length)}</span>
                </div>
                <span className={statusClass(session.session_state || session.status)}>{session.session_state || session.status || "unknown"}</span>
              </article>
            )) : (
              <article className="row">
                <div>
                  <strong>No active remote sessions</strong>
                  <span>Session list is safe-projected; raw session ids and tokens are omitted.</span>
                </div>
                <span className="status statusWarn">empty</span>
              </article>
            )}
          </div>
        </div>

        <div className="panel" data-smoke="worker-adapter-readiness-proof">
          <div className="panelHeader">
            <h2><TerminalSquare size={14} /> Adapter readiness</h2>
            <span>{adapterReadiness.contract || "adapter readiness contract"}</span>
          </div>
          <div className="adapterGrid">
            {adapterEntries.length ? adapterEntries.map(([adapter, readiness]) => (
              <article className="adapterCard" key={adapter}>
                <div>
                  <strong>{readiness.adapter || adapter}</strong>
                  <span>{readiness.recommended_action || readiness.readiness || "readiness pending"}</span>
                </div>
                <span className={statusClass(readiness.readiness || readiness.ok)}>{readiness.readiness || (readiness.ok ? "ready" : "attention")}</span>
                <div className="proofStrip">
                  <span>trust {titleize(readiness.trust_status || "unknown")}</span>
                  <span>confirm {boolLabel(readiness.requires_confirm_run)}</span>
                  <span className={statusClass(readiness.token_omitted)}>token omitted</span>
                </div>
              </article>
            )) : <p className="empty">No adapter readiness rows loaded.</p>}
          </div>
          <div className="proofStrip">
            <span className={statusClass(adapterReadiness.token_omitted)}>token omitted</span>
            <span className={statusClass(adapterReadiness.live_execution_performed === false)}>no live execution</span>
          </div>
        </div>
      </section>

      <section className="panel wide" data-smoke="worker-daemon-status-readback">
        <div className="panelHeader">
          <h2><ServerCog size={14} /> Local daemon status</h2>
          <span>{daemons.length} daemons</span>
        </div>
        <div className="list compact">
          {daemons.length ? daemons.map((daemon) => (
            <article className="row" key={`${daemon.adapter || "adapter"}:${daemon.agent_id || daemon.pid || daemon.status}`}>
              <div>
                <strong>{daemon.adapter || "worker"} daemon</strong>
                <span>{daemon.agent_id || "agent id pending"} · pid {daemon.pid || "none"} · processed {numberValue(daemon.processed)} · errors {numberValue(daemon.error_count)}</span>
              </div>
              <span className={statusClass(daemon.running ? "running" : daemon.status)}>{daemon.running ? "running" : daemon.status || "stopped"}</span>
            </article>
          )) : (
            <article className="row">
              <div>
                <strong>No local daemons running</strong>
                <span>Next shows status only; live daemon start/restart/stop remains fail-closed outside mock controls.</span>
              </div>
              <span className="status statusWarn">idle</span>
            </article>
          )}
        </div>
      </section>
    </AppFrame>
  );
}
