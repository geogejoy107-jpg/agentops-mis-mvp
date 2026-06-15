import { Activity, AlertTriangle, Brain, CheckCircle2, RefreshCw, ShieldAlert, Wifi } from "lucide-react";
import type { PixelMetrics } from "./pixelModel";

interface OperationsBarProps {
  metrics: PixelMetrics;
  loading?: boolean;
  error?: string | null;
  onRefresh?: () => void;
}

interface OperationTile {
  label: string;
  value: string | number;
  hint: string;
  tone: "cyan" | "green" | "amber" | "red" | "purple";
  icon: JSX.Element;
}

const toneStyle: Record<OperationTile["tone"], { color: string; bg: string; border: string }> = {
  cyan: { color: "var(--mis-cyan)", bg: "rgba(34,211,238,0.10)", border: "rgba(34,211,238,0.24)" },
  green: { color: "var(--mis-success)", bg: "rgba(42,157,143,0.12)", border: "rgba(42,157,143,0.25)" },
  amber: { color: "#FBBF24", bg: "rgba(251,191,36,0.12)", border: "rgba(251,191,36,0.28)" },
  red: { color: "#F87171", bg: "rgba(248,113,113,0.12)", border: "rgba(248,113,113,0.28)" },
  purple: { color: "var(--mis-purple)", bg: "rgba(168,85,247,0.12)", border: "rgba(168,85,247,0.26)" },
};

export function OperationsBar({ metrics, loading, error, onRefresh }: OperationsBarProps) {
  const tiles: OperationTile[] = [
    {
      label: "Active runs",
      value: metrics.activeRuns,
      hint: `${metrics.totalRuns} total`,
      tone: "cyan",
      icon: <Activity size={14} />,
    },
    {
      label: "Pending approvals",
      value: metrics.pendingApprovals,
      hint: "human gate",
      tone: metrics.pendingApprovals > 0 ? "amber" : "green",
      icon: <ShieldAlert size={14} />,
    },
    {
      label: "Failed gates",
      value: metrics.failedQualityGates,
      hint: "quality",
      tone: metrics.failedQualityGates > 0 ? "red" : "green",
      icon: <CheckCircle2 size={14} />,
    },
    {
      label: "Memory candidates",
      value: metrics.memoryCandidates,
      hint: "review queue",
      tone: "purple",
      icon: <Brain size={14} />,
    },
    {
      label: "Runtime health",
      value: metrics.runtimeHealth,
      hint: "connectors",
      tone: metrics.runtimeHealth.includes("fail") || metrics.runtimeHealth.includes("unavailable") ? "red" : "cyan",
      icon: <Wifi size={14} />,
    },
    {
      label: "Incidents",
      value: metrics.failedRuns + metrics.blockedTasks,
      hint: "failed / blocked",
      tone: metrics.failedRuns + metrics.blockedTasks > 0 ? "red" : "green",
      icon: <AlertTriangle size={14} />,
    },
  ];

  return (
    <section className="rounded-lg p-3" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div>
          <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>Operations Bar</h2>
          <p className="text-[11px]" style={{ color: "var(--mis-dim)" }}>
            Live control-plane signals that drive the floor map.
          </p>
        </div>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-[11px] disabled:opacity-50"
            style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        )}
      </div>
      {error && (
        <div className="mb-3 rounded px-2.5 py-2 text-[11px]" style={{ background: "rgba(248,113,113,0.10)", color: "#FCA5A5", border: "1px solid rgba(248,113,113,0.24)" }}>
          Live backend unavailable, showing demo-safe state: {error}
        </div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-2">
        {tiles.map((tile) => {
          const tone = toneStyle[tile.tone];
          return (
            <div key={tile.label} className="rounded p-2" style={{ background: tone.bg, border: `1px solid ${tone.border}` }}>
              <div className="flex items-center gap-1.5 text-[10px]" style={{ color: tone.color }}>
                {tile.icon}
                <span style={{ color: "var(--mis-muted)" }}>{tile.label}</span>
              </div>
              <div className="mt-1 truncate text-base font-semibold" style={{ color: "var(--mis-text)" }}>{tile.value}</div>
              <div className="truncate text-[9px]" style={{ color: "var(--mis-muted)" }}>{tile.hint}</div>
            </div>
          );
        })}
      </div>
      <div className="mt-2 text-[10px]" style={{ color: "var(--mis-muted)" }}>
        Latest audit signal: <span style={{ color: "var(--mis-cyan)" }}>{metrics.latestAudit}</span> · External base: <span style={{ color: "var(--mis-cyan)" }}>{metrics.externalSyncState}</span>
      </div>
    </section>
  );
}
