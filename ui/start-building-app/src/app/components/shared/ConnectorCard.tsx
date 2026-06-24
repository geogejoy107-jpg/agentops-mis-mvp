import { ExternalLink, RefreshCw, AlertTriangle, CheckCircle, XCircle, Clock } from "lucide-react";
import { StatusBadge } from "./StatusBadge";
import type { RuntimeConnector } from "../../data/mockData";
import { pick, usePreferences } from "../../context/PreferencesContext";

interface ConnectorCardProps {
  connector: RuntimeConnector;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "ready" || status === "live") return <CheckCircle size={14} style={{ color: "var(--mis-success)" }} />;
  if (status === "unavailable") return <XCircle size={14} style={{ color: "#F87171" }} />;
  if (status === "dry_run") return <Clock size={14} style={{ color: "var(--mis-primary)" }} />;
  return <AlertTriangle size={14} style={{ color: "#FBBF24" }} />;
}

export function ConnectorCard({ connector }: ConnectorCardProps) {
  const { locale } = usePreferences();
  const copy = pick(locale, {
    en: {
      mode: "Mode",
      endpoint: "Endpoint",
      lastChecked: "Last checked",
      realRun: "Real run",
      enabled: "Enabled",
      disabled: "Disabled",
      confirmRequired: "Explicit confirmation required before real run",
      lastEvent: "Last event",
      probe: "Probe",
      viewLedger: "View Ledger",
    },
    zh: {
      mode: "模式",
      endpoint: "端点",
      lastChecked: "上次检查",
      realRun: "真实运行",
      enabled: "已开启",
      disabled: "已关闭",
      confirmRequired: "真实运行前必须显式确认",
      lastEvent: "最近事件",
      probe: "探测",
      viewLedger: "查看账本",
    },
  });

  return (
    <div
      className="rounded-xl p-5 flex flex-col gap-4"
      style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <StatusIcon status={connector.status} />
          <div>
            <div className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>
              {connector.provider}
            </div>
            <div className="text-[11px]" style={{ color: "var(--mis-dim)" }}>
              {connector.connector_id}
            </div>
          </div>
        </div>
        <StatusBadge status={connector.status} />
      </div>

      {/* Details grid */}
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: copy.mode, value: connector.mode },
          { label: copy.endpoint, value: connector.endpoint.length > 24 ? connector.endpoint.slice(0, 24) + "…" : connector.endpoint },
          { label: copy.lastChecked, value: new Date(connector.last_checked).toLocaleTimeString(locale === "zh" ? "zh-CN" : "en-US") },
          { label: copy.realRun, value: connector.real_run_enabled ? copy.enabled : copy.disabled },
        ].map(({ label, value }) => (
          <div key={label}>
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{label}</div>
            <div className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Confirm required warning */}
      {connector.confirm_required && (
        <div
          className="flex items-center gap-2 text-[11px] rounded px-3 py-2"
          style={{ background: "rgba(251,191,36,0.08)", color: "#FBBF24", border: "1px solid rgba(251,191,36,0.2)" }}
        >
          <AlertTriangle size={12} />
          {copy.confirmRequired}
        </div>
      )}

      {/* Last event */}
      {connector.last_event && (
        <div className="text-[11px] rounded px-3 py-2" style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)" }}>
          <span style={{ color: "var(--mis-muted)" }}>{copy.lastEvent}: </span>
          {connector.last_event}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 mt-1">
        <button
          className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded transition-opacity hover:opacity-80"
          style={{ background: "rgba(46,134,171,0.15)", color: "var(--mis-primary)", border: "1px solid rgba(46,134,171,0.2)" }}
        >
          <RefreshCw size={11} />
          {copy.probe}
        </button>
        <button
          className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded transition-opacity hover:opacity-80"
          style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)" }}
        >
          <ExternalLink size={11} />
          {copy.viewLedger}
        </button>
      </div>
    </div>
  );
}
