import { Plug, Radio } from "lucide-react";
import { ConnectorCard } from "../shared/ConnectorCard";
import { StatusBadge } from "../shared/StatusBadge";
import { loadAudit, loadRuntimeConnectors, useLiveData } from "../../data/liveApi";
import { pick, usePreferences } from "../../context/PreferencesContext";

export function RuntimeConnectors() {
  const { locale } = usePreferences();
  const { data, loading, error, refresh } = useLiveData(async () => {
    const [runtimeConnectors, auditLogs] = await Promise.all([loadRuntimeConnectors(), loadAudit()]);
    const connectorAuditLogs = auditLogs.filter(a =>
      a.entity_type === "runtime_connectors" || a.entity_type === "runtime_connector" || a.entity_type === "connector"
    );
    return { runtimeConnectors, connectorAuditLogs };
  }, []);
  const runtimeConnectors = data?.runtimeConnectors || [];
  const connectorAuditLogs = data?.connectorAuditLogs || [];
  const copy = pick(locale, {
    en: {
      title: "Runtime Connectors",
      subtitle: "Vendor-neutral control plane · live AgentOps MIS backend",
      loading: "Loading live connectors...",
      backendUnavailable: "Live backend unavailable",
      refresh: "Refresh live",
      ready: "Ready",
      live: "Live",
      dryRun: "Dry-run",
      unavailable: "Unavailable",
      plannedConnectors: "Planned Connectors",
      recentRuntimeEvents: "Recent Runtime Events",
    },
    zh: {
      title: "运行时连接器",
      subtitle: "供应商中立的控制平面 · 连接本地 AgentOps MIS 后端",
      loading: "正在加载实时连接器...",
      backendUnavailable: "本地后端不可用",
      refresh: "刷新实时状态",
      ready: "就绪",
      live: "实时",
      dryRun: "安全预演",
      unavailable: "不可用",
      plannedConnectors: "计划接入的连接器",
      recentRuntimeEvents: "最近运行时事件",
    },
  });

  return (
    <div className="space-y-6 w-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>
            {copy.title}
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
            {copy.subtitle}
          </p>
          {loading && <p className="text-xs mt-2" style={{ color: "var(--mis-muted)" }}>{copy.loading}</p>}
          {error && <p className="text-xs mt-2" style={{ color: "#F87171" }}>{copy.backendUnavailable}: {error}</p>}
        </div>
        <button onClick={refresh} className="flex items-center gap-2 text-xs px-3 py-1.5 rounded" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)", color: "var(--mis-dim)" }}>
          <Radio size={12} style={{ color: "var(--mis-success)" }} />
          {copy.refresh}
        </button>
      </div>

      {/* Status summary */}
      <div className="flex gap-4 flex-wrap">
        {[
          { label: copy.ready, count: runtimeConnectors.filter(c => c.status === "ready").length, status: "ready" },
          { label: copy.live, count: runtimeConnectors.filter(c => c.status === "live").length, status: "live" },
          { label: copy.dryRun, count: runtimeConnectors.filter(c => c.status === "dry_run").length, status: "dry_run" },
          { label: copy.unavailable, count: runtimeConnectors.filter(c => c.status === "unavailable").length, status: "unavailable" },
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
          {copy.plannedConnectors}
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
          <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-text)" }}>{copy.recentRuntimeEvents}</div>
          <div className="space-y-2">
            {connectorAuditLogs.map(log => (
              <div key={log.audit_id} className="flex items-center justify-between py-2" style={{ borderBottom: "1px solid var(--mis-border)" }}>
                <div>
                  <span className="text-xs font-medium" style={{ color: "var(--mis-text)" }}>{log.action}</span>
                  <span className="text-[11px] ml-2" style={{ color: "var(--mis-muted)" }}>{log.entity_id}</span>
                </div>
                <span className="text-[11px]" style={{ color: "var(--mis-muted)" }}>
                  {new Date(log.created_at).toLocaleString(locale === "zh" ? "zh-CN" : "en-US")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
