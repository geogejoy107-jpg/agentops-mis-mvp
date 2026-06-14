import { Plug, Radio } from "lucide-react";
import { ConnectorCard } from "../shared/ConnectorCard";
import { StatusBadge } from "../shared/StatusBadge";
import { loadAudit, loadRuntimeConnectors, useLiveData } from "../../data/liveApi";

export function RuntimeConnectors() {
  const { data, loading, error, refresh } = useLiveData(async () => {
    const [runtimeConnectors, auditLogs] = await Promise.all([loadRuntimeConnectors(), loadAudit()]);
    const connectorAuditLogs = auditLogs.filter(a =>
      a.entity_type === "runtime_connectors" || a.entity_type === "runtime_connector" || a.entity_type === "connector"
    );
    return { runtimeConnectors, connectorAuditLogs };
  }, []);
  const runtimeConnectors = data?.runtimeConnectors || [];
  const connectorAuditLogs = data?.connectorAuditLogs || [];

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>
            Runtime Connectors
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
            Vendor-neutral control plane · live AgentOps MIS backend
          </p>
          {loading && <p className="text-xs mt-2" style={{ color: "var(--mis-muted)" }}>Loading live connectors...</p>}
          {error && <p className="text-xs mt-2" style={{ color: "#F87171" }}>Live backend unavailable: {error}</p>}
        </div>
        <button onClick={refresh} className="flex items-center gap-2 text-xs px-3 py-1.5 rounded" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)", color: "var(--mis-dim)" }}>
          <Radio size={12} style={{ color: "var(--mis-success)" }} />
          Refresh live
        </button>
      </div>

      {/* Status summary */}
      <div className="flex gap-4 flex-wrap">
        {[
          { label: "Ready", count: runtimeConnectors.filter(c => c.status === "ready").length, status: "ready" },
          { label: "Live", count: runtimeConnectors.filter(c => c.status === "live").length, status: "live" },
          { label: "Dry-run", count: runtimeConnectors.filter(c => c.status === "dry_run").length, status: "dry_run" },
          { label: "Unavailable", count: runtimeConnectors.filter(c => c.status === "unavailable").length, status: "unavailable" },
        ].map(({ label, count, status }) => (
          <div
            key={label}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs"
            style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
          >
            <span style={{ color: "var(--mis-dim)" }}>{label}:</span>
            <span className="font-semibold" style={{ color: "var(--mis-text)" }}>{count}</span>
            <StatusBadge status={status} />
          </div>
        ))}
      </div>

      {/* Connector cards grid */}
      <div className="grid grid-cols-2 gap-4">
        {runtimeConnectors.map(connector => (
          <ConnectorCard key={connector.connector_id} connector={connector} />
        ))}
      </div>

      {/* Integration architecture note */}
      <div
        className="rounded-xl p-4 text-xs"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="font-semibold mb-2" style={{ color: "var(--mis-text)" }}>
          <Plug size={13} className="inline mr-1.5" style={{ color: "var(--mis-primary)" }} />
          Planned Connectors
        </div>
        <div className="flex gap-3 flex-wrap">
          {["OpenAI-compatible APIs", "Claude Direct", "Codex", "OpenHands", "CrewAI", "LangGraph"].map(name => (
            <span
              key={name}
              className="px-2 py-1 rounded"
              style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}
            >
              {name}
            </span>
          ))}
        </div>
      </div>

      {/* Recent runtime events */}
      {connectorAuditLogs.length > 0 && (
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-text)" }}>Recent Runtime Events</div>
          <div className="space-y-2">
            {connectorAuditLogs.map(log => (
              <div key={log.audit_id} className="flex items-center justify-between py-2" style={{ borderBottom: "1px solid var(--mis-border)" }}>
                <div>
                  <span className="text-xs font-medium" style={{ color: "var(--mis-text)" }}>{log.action}</span>
                  <span className="text-[11px] ml-2" style={{ color: "var(--mis-muted)" }}>{log.entity_id}</span>
                </div>
                <span className="text-[11px]" style={{ color: "var(--mis-muted)" }}>
                  {new Date(log.created_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
