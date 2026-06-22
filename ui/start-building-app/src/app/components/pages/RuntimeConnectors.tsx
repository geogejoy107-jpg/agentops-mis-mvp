import { Plug, Radio } from "lucide-react";
import { useState } from "react";
import { ConnectorCard } from "../shared/ConnectorCard";
import { StatusBadge } from "../shared/StatusBadge";
import { loadAudit, loadRuntimeConnectors, updateRuntimeConnectorTrust, useLiveData } from "../../data/liveApi";
import { pick, usePreferences } from "../../context/PreferencesContext";

export function RuntimeConnectors() {
  const { locale } = usePreferences();
  const [trustAction, setTrustAction] = useState<string | null>(null);
  const [trustMessage, setTrustMessage] = useState<string | null>(null);
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
      trusted: "Trusted",
      reviewRequired: "Review",
      blocked: "Blocked",
      trustRegistry: "Runtime Trust Registry",
      trustSummary: "Controls whether live adapters are trusted, require review, or are blocked before customer worker execution.",
      updatingTrust: "Updating...",
      trustUpdated: "Trust policy updated",
      capabilityManifest: "Capability Manifest",
      policyHash: "Policy hash",
      observation: "Observation",
      riskFloor: "Risk",
      externalWrite: "External write",
      confirm: "Confirm",
      trustPolicy: "Trust policy",
      commercial: "Commercial",
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
      trusted: "已信任",
      reviewRequired: "需复核",
      blocked: "已阻止",
      trustRegistry: "运行时信任登记",
      trustSummary: "控制 live adapter 在客户 worker 执行前是可信、需复核，还是被阻止。",
      updatingTrust: "正在更新...",
      trustUpdated: "信任策略已更新",
      capabilityManifest: "能力清单",
      policyHash: "策略哈希",
      observation: "观测级别",
      riskFloor: "风险下限",
      externalWrite: "外部写入",
      confirm: "确认要求",
      trustPolicy: "信任策略",
      commercial: "商业状态",
      plannedConnectors: "计划接入的连接器",
      recentRuntimeEvents: "最近运行时事件",
    },
  });

  const capabilitySummary = (connector: (typeof runtimeConnectors)[number]) => {
    const manifest = connector.capability_manifest || {};
    const capabilities = typeof manifest.capabilities === "object" && manifest.capabilities !== null
      ? manifest.capabilities as Record<string, unknown>
      : {};
    return [
      { label: copy.observation, value: connector.observation_level || String(manifest.observation_level || "—") },
      { label: copy.riskFloor, value: connector.risk_floor || String(manifest.risk_floor || "—") },
      { label: copy.externalWrite, value: String(capabilities.external_write || "—") },
      { label: copy.confirm, value: String(capabilities.confirmation || "—") },
      { label: copy.trustPolicy, value: String(capabilities.trust_policy || connector.trust_status || "—") },
      { label: copy.commercial, value: connector.commercial_readiness || String(manifest.commercial_readiness || "—") },
    ];
  };

  const changeTrust = async (connectorId: string, trustStatus: "trusted" | "review_required" | "blocked") => {
    setTrustAction(`${connectorId}:${trustStatus}`);
    setTrustMessage(null);
    try {
      await updateRuntimeConnectorTrust(connectorId, {
        trust_status: trustStatus,
        trust_note: locale === "zh"
          ? `管理员将 ${connectorId} 标记为 ${trustStatus}。`
          : `Operator marked ${connectorId} as ${trustStatus}.`,
      });
      setTrustMessage(`${copy.trustUpdated}: ${connectorId} -> ${trustStatus}`);
      await refresh();
    } catch (err) {
      setTrustMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setTrustAction(null);
    }
  };

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
          <div key={connector.connector_id} className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--mis-border)" }}>
            <ConnectorCard connector={connector} />
            <div className="px-5 pb-5 -mt-1" style={{ background: "var(--mis-surface)" }}>
              <div className="rounded-lg p-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.trustRegistry}</div>
                    <div className="text-[10px] mt-0.5" style={{ color: "var(--mis-muted)" }}>{copy.trustSummary}</div>
                    {connector.trust_note && (
                      <div className="text-[10px] mt-1 truncate" style={{ color: "var(--mis-dim)" }}>{connector.trust_note}</div>
                    )}
                  </div>
                  <StatusBadge status={connector.trust_status || "trusted"} />
                </div>
                <div className="flex flex-wrap gap-2 mt-3">
                  {[
                    { status: "trusted" as const, label: copy.trusted },
                    { status: "review_required" as const, label: copy.reviewRequired },
                    { status: "blocked" as const, label: copy.blocked },
                  ].map(item => (
                    <button
                      key={item.status}
                      onClick={() => changeTrust(connector.connector_id, item.status)}
                      disabled={Boolean(trustAction)}
                      className="text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
                      style={{
                        background: connector.trust_status === item.status ? "rgba(34,211,238,0.14)" : "var(--mis-bg)",
                        color: item.status === "blocked" ? "#F87171" : connector.trust_status === item.status ? "var(--mis-cyan)" : "var(--mis-dim)",
                        border: "1px solid var(--mis-border)",
                      }}
                    >
                      {trustAction === `${connector.connector_id}:${item.status}` ? copy.updatingTrust : item.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="rounded-lg p-3 mt-3" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{copy.capabilityManifest}</div>
                  {connector.capability_policy_hash && (
                    <div className="text-[10px] truncate max-w-[180px]" style={{ color: "var(--mis-muted)" }}>
                      {copy.policyHash}: {connector.capability_policy_hash.slice(0, 12)}
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2 mt-3">
                  {capabilitySummary(connector).map(item => (
                    <div key={item.label} className="min-w-0 rounded px-2 py-1.5" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
                      <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                      <div className="text-[10px] font-semibold truncate" title={item.value} style={{ color: "var(--mis-text)" }}>{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {trustMessage && (
        <div className="text-xs rounded px-3 py-2" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)", color: trustMessage.includes("Error") || trustMessage.includes("error") ? "#F87171" : "var(--mis-success)" }}>
          {trustMessage}
        </div>
      )}

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
