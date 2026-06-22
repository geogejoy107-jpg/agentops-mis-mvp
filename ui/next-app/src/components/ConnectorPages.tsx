"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Filter, Plug, Radio, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { AppFrame } from "./AppFrame";
import {
  loadAudit,
  loadRuntimeConnectors,
  updateRuntimeConnectorTrust,
  type AuditSummary,
  type RuntimeConnectorSummary,
} from "@/lib/mis";

type LoadState = {
  audit: AuditSummary[];
  connectors: RuntimeConnectorSummary[];
  error: string | null;
  loading: boolean;
};

type TrustStatus = "trusted" | "review_required" | "blocked";

function connectorId(connector: RuntimeConnectorSummary) {
  return connector.runtime_connector_id || connector.connector_id || "unknown";
}

function booleanValue(value: unknown) {
  return value === true || value === 1 || value === "1" || value === "true";
}

function statusClass(status?: string) {
  const normalized = status || "unknown";
  if (["ready", "live", "trusted"].includes(normalized)) return "status statusGood";
  if (["blocked", "unavailable", "failed"].includes(normalized)) return "status statusBad";
  if (["review_required", "dry_run", "unknown"].includes(normalized)) return "status statusWarn";
  return "status";
}

function statusIcon(status?: string) {
  if (["ready", "live", "trusted"].includes(status || "")) return <CheckCircle2 size={15} />;
  if (["blocked", "unavailable", "failed"].includes(status || "")) return <XCircle size={15} />;
  return <AlertTriangle size={15} />;
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function RuntimeConnectorsParityPage() {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [trustMessage, setTrustMessage] = useState<string | null>(null);
  const [state, setState] = useState<LoadState>({ audit: [], connectors: [], error: null, loading: true });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      const [connectors, audit] = await Promise.all([loadRuntimeConnectors(), loadAudit()]);
      setState({
        audit: audit.filter((item) => ["runtime_connectors", "runtime_connector", "connector"].includes(item.entity_type)),
        connectors,
        error: null,
        loading: false,
      });
    } catch (err) {
      setState({ audit: [], connectors: [], error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const counts = useMemo(() => {
    const byStatus = new Map<string, number>();
    const byTrust = new Map<string, number>();
    for (const connector of state.connectors) {
      byStatus.set(connector.status || "unknown", (byStatus.get(connector.status || "unknown") || 0) + 1);
      byTrust.set(connector.trust_status || "trusted", (byTrust.get(connector.trust_status || "trusted") || 0) + 1);
    }
    return { byStatus, byTrust };
  }, [state.connectors]);

  const filtered = state.connectors.filter((connector) => {
    if (statusFilter === "all") return true;
    return (connector.trust_status || "trusted") === statusFilter || (connector.status || "unknown") === statusFilter;
  });

  const submitTrust = async (id: string, trustStatus: TrustStatus) => {
    setBusyId(id);
    setTrustMessage(null);
    try {
      await updateRuntimeConnectorTrust(id, trustStatus, `Next operator marked ${id} as ${trustStatus}.`);
      setTrustMessage(`Runtime connector trust updated: ${id} -> ${trustStatus}`);
      await refresh();
    } catch (err) {
      setTrustMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Next.js parity route</p>
          <h1>Runtime Connectors</h1>
          <p className="subtle">
            {state.connectors.length} connectors · {counts.byTrust.get("blocked") || 0} blocked · {counts.byTrust.get("review_required") || 0} require review
          </p>
        </div>
        <button className="iconButton" onClick={refresh} disabled={state.loading || Boolean(busyId)} aria-label="Refresh runtime connectors">
          <RefreshCw size={17} className={state.loading ? "spin" : ""} />
        </button>
      </header>

      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/runtime-connectors: {state.error}</div> : null}
      {trustMessage ? <div className={`banner ${trustMessage.includes("updated") ? "success" : "error"}`}>{trustMessage}</div> : null}

      <section className="metricGrid">
        <article className="metric">
          <span><Plug size={15} />Runtime Trust Registry</span>
          <strong>{counts.byTrust.get("trusted") || 0}</strong>
          <small>trusted connectors</small>
        </article>
        <article className="metric">
          <span><ShieldAlert size={15} />Review required</span>
          <strong>{counts.byTrust.get("review_required") || 0}</strong>
          <small>must be reviewed before live execution</small>
        </article>
        <article className="metric">
          <span><XCircle size={15} />Blocked</span>
          <strong>{counts.byTrust.get("blocked") || 0}</strong>
          <small>customer worker live execution blocked</small>
        </article>
      </section>

      <div className="filterBar">
        {["all", "trusted", "review_required", "blocked", "ready", "live", "dry_run", "unavailable"].map((status) => (
          <button className={`filterChip ${statusFilter === status ? "active" : ""}`} key={status} onClick={() => setStatusFilter(status)}>
            {status}
            <span>{status === "all" ? state.connectors.length : (counts.byTrust.get(status) || counts.byStatus.get(status) || 0)}</span>
          </button>
        ))}
      </div>

      <div className="grid">
        {filtered.map((connector) => {
          const id = connectorId(connector);
          return (
            <article className="panel" key={id}>
              <div className="panelHeader">
                <div>
                  <strong>{connector.provider || "unknown provider"}</strong>
                  <span>{id} · {connector.connector_type || "runtime"} · {connector.profile_name || "default"}</span>
                </div>
                <span className={statusClass(connector.status)}>{statusIcon(connector.status)} {connector.status || "unknown"}</span>
              </div>

              <div className="miniMetrics">
                <span className="metaPill">allow real run {String(booleanValue(connector.allow_real_run))}</span>
                <span className="metaPill">require confirm {String(booleanValue(connector.require_confirm_run))}</span>
                <span className="metaPill">last health {formatDate(connector.last_health_at || connector.updated_at)}</span>
              </div>

              <p className="subtle">{connector.base_url || connector.binary_path || "local runtime endpoint omitted"}</p>
              {connector.last_error ? <p className="subtle">last error: {connector.last_error}</p> : null}

              <div className="approvalActions">
                <span className={statusClass(connector.trust_status || "trusted")}>{connector.trust_status || "trusted"}</span>
                {(["trusted", "review_required", "blocked"] as TrustStatus[]).map((trustStatus) => (
                  <form className="inlineForm" method="post" action="/workspace/connectors/trust" key={trustStatus}>
                    <input type="hidden" name="connector_id" value={id} />
                    <input type="hidden" name="trust_status" value={trustStatus} />
                    <button
                      aria-label={`${trustStatus === "trusted" ? "Trust" : trustStatus === "blocked" ? "Block" : "Review"} ${id}`}
                      className={`miniButton ${trustStatus === "trusted" ? "good" : trustStatus === "blocked" ? "bad" : ""}`}
                      disabled={busyId === id}
                      onClick={(event) => {
                        event.preventDefault();
                        void submitTrust(id, trustStatus);
                      }}
                      type="submit"
                    >
                      {trustStatus === "trusted" ? <CheckCircle2 size={13} /> : trustStatus === "blocked" ? <XCircle size={13} /> : <ShieldAlert size={13} />}
                      {trustStatus === "trusted" ? "Trust" : trustStatus === "blocked" ? "Block" : "Review"}
                    </button>
                  </form>
                ))}
              </div>

              {connector.trust_note ? <p className="subtle">{connector.trust_note}</p> : null}
              <p className="subtle">trust updated {formatDate(connector.trust_updated_at)}</p>
            </article>
          );
        })}
      </div>

      {!filtered.length && !state.loading ? (
        <div className="emptyState">
          <Filter size={24} />
          <p>No runtime connectors match this filter.</p>
        </div>
      ) : null}
      {state.loading ? (
        <div className="emptyState">
          <Radio size={24} />
          <p>Loading runtime connectors...</p>
        </div>
      ) : null}

      <section className="panel wide">
        <div className="panelHeader">
          <div>
            <strong>Recent connector audit</strong>
            <span>runtime connector trust and connector evidence</span>
          </div>
          <span className="status">append-only</span>
        </div>
        <div className="tableWrap">
          <table className="dataTable">
            <thead>
              <tr>
                <th>Action</th>
                <th>Entity</th>
                <th>Actor</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {state.audit.slice(0, 80).map((audit) => (
                <tr key={audit.audit_id}>
                  <td>{audit.action}</td>
                  <td className="mono">{audit.entity_type}:{audit.entity_id}</td>
                  <td>{audit.actor_type}:{audit.actor_id}</td>
                  <td>{formatDate(audit.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!state.audit.length ? <p className="empty tableEmpty">No connector audit events loaded.</p> : null}
        </div>
      </section>
    </AppFrame>
  );
}
