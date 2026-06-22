import { History, KeyRound, ShieldCheck, UsersRound } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type {
  AgentGatewaySessionsPayload,
  AuditSummary,
  CommercialEntitlementStatus,
  ReadinessGate,
  SecurityReadinessSummary,
  WorkerStatusSummary,
} from "@/lib/mis";

function statusClass(status?: string) {
  if (["pass", "ready", "active", "healthy"].includes(status || "")) return "status statusGood";
  if (["fail", "blocked", "revoked", "expired", "unavailable"].includes(status || "")) return "status statusBad";
  if (["warn", "attention", "degraded", "waiting_for_heartbeat"].includes(status || "")) return "status statusWarn";
  return "status";
}

function boolText(value: unknown) {
  if (value === true) return "true";
  if (value === false) return "false";
  return "unknown";
}

function countBy<T>(items: T[], getKey: (item: T) => string | undefined) {
  return items.reduce<Record<string, number>>((acc, item) => {
    const key = getKey(item) || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function metricValue(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num.toLocaleString() : "0";
}

function GateRows({ gates }: Readonly<{ gates?: ReadinessGate[] }>) {
  const rows = (gates || []).slice(0, 8);
  if (!rows.length) return <p className="empty">No production readiness gates loaded.</p>;
  return (
    <div className="list compactList">
      {rows.map((gate, index) => (
        <div className="row" key={`${gate.id || gate.label || "gate"}:${index}`}>
          <div>
            <strong>{gate.label || gate.id || "Readiness gate"}</strong>
            <span>{gate.detail || gate.summary || gate.next_action || gate.action || "No detail loaded."}</span>
          </div>
          <span className={statusClass(gate.status || (gate.ok ? "pass" : "attention"))}>{gate.status || (gate.ok ? "pass" : "attention")}</span>
        </div>
      ))}
    </div>
  );
}

export function GovernanceParityPage({
  security,
  entitlements,
  worker,
  sessions,
  audit,
  errors,
}: Readonly<{
  security: SecurityReadinessSummary;
  entitlements: CommercialEntitlementStatus;
  worker: WorkerStatusSummary;
  sessions: AgentGatewaySessionsPayload;
  audit: AuditSummary[];
  errors?: string[];
}>) {
  const activeSessions = (sessions.sessions || []).filter((session) => (session.session_state || session.status) === "active");
  const sessionStates = countBy(sessions.sessions || [], (session) => session.session_state || session.status);
  const auditTypes = countBy(audit, (row) => row.action);
  const rbacGate = (entitlements.gates || []).find((gate) => gate.capability === "rbac");
  const sessionHygieneGate = (worker.fleet_health?.gates || []).find((gate) => gate.id === "session_hygiene");

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Team governance parity route</p>
          <h1>Governance</h1>
          <p className="subtle">Read-only production, workspace, RBAC, session, and audit evidence for the commercial track</p>
        </div>
        <span className="status statusGood">read-only</span>
      </header>

      {(errors || []).filter(Boolean).map((error) => (
        <div className="banner error" key={error}>Governance source unavailable: {error}</div>
      ))}

      <section className="metrics six">
        {[
          ["Production", security.status || "unknown"],
          ["Auth mode", security.auth_mode || "unknown"],
          ["RBAC gate", rbacGate?.enabled ? "enabled" : rbacGate?.required_edition || "team_governance"],
          ["Remote sessions", activeSessions.length],
          ["Audit events", audit.length],
          ["Token omitted", boolText(sessions.token_omitted !== false && security.safety?.token_omitted !== false)],
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
            <h2><ShieldCheck size={14} /> Production readiness</h2>
            <span className={statusClass(security.status)}>{security.status || "unknown"}</span>
          </div>
          <div className="proofStrip">
            <span>requested {boolText(security.production_requested)}</span>
            <span>ready {boolText(security.production_ready)}</span>
            <span>read only {boolText(security.safety?.read_only)}</span>
            <span>live execution {boolText(security.safety?.live_execution_performed)}</span>
          </div>
          <GateRows gates={security.gates} />
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2><UsersRound size={14} /> Workspace and RBAC</h2>
            <span className={statusClass(rbacGate?.enabled ? "ready" : "attention")}>{rbacGate?.enabled ? "enabled" : "gated"}</span>
          </div>
          <div className="proofStrip">
            <span>workspace {entitlements.workspace_id || "local_demo"}</span>
            <span>edition {entitlements.edition || "free_local"}</span>
            <span>rbac {boolText(entitlements.capabilities?.rbac)}</span>
            <span>multi project {boolText(entitlements.capabilities?.multi_project)}</span>
          </div>
          <p className="subtle">
            RBAC and multi-project controls stay fail-closed behind edition gates until Team/Enterprise governance is active.
          </p>
        </div>
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><KeyRound size={14} /> Session governance</h2>
            <span className={statusClass(sessionHygieneGate?.status || worker.fleet_health?.overall)}>{sessionHygieneGate?.status || worker.fleet_health?.overall || "unknown"}</span>
          </div>
          <div className="proofStrip">
            <span>active {metricValue(sessionStates.active)}</span>
            <span>expired {metricValue(sessionStates.expired)}</span>
            <span>revoked {metricValue(sessionStates.revoked)}</span>
            <span>raw ids omitted {boolText(sessions.token_omitted)}</span>
          </div>
          <div className="list compactList">
            {(sessions.sessions || []).slice(0, 8).map((session, index) => (
              <div className="row" key={`${session.agent_id || "agent"}:${session.created_at || index}`}>
                <div>
                  <strong>{session.agent_id || "agent"}</strong>
                  <span>{session.workspace_id || "workspace"} · scopes {session.scope_count ?? session.scopes?.length ?? 0} · session id omitted</span>
                </div>
                <span className={statusClass(session.session_state || session.status)}>{session.session_state || session.status || "unknown"}</span>
              </div>
            ))}
            {(sessions.sessions || []).length ? null : <p className="empty">No short-lived sessions loaded.</p>}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2><History size={14} /> Audit evidence</h2>
            <span>{audit.length} events</span>
          </div>
          <div className="proofStrip">
            {Object.entries(auditTypes).slice(0, 4).map(([action, count]) => <span key={action}>{action} {count}</span>)}
            {Object.keys(auditTypes).length ? null : <span>no audit rows loaded</span>}
          </div>
          <div className="list compactList">
            {audit.slice(0, 8).map((row) => (
              <div className="row" key={row.audit_id}>
                <div>
                  <strong>{row.action}</strong>
                  <span>{row.actor_type}:{row.actor_id} · {row.entity_type}:{row.entity_id}</span>
                </div>
                <span>{row.created_at || "time unknown"}</span>
              </div>
            ))}
            {audit.length ? null : <p className="empty">No audit evidence loaded.</p>}
          </div>
        </div>
      </section>
    </AppFrame>
  );
}
