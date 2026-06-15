import type { PixelMetrics, PixelZoneDefinition } from "./pixelModel";
import { formatZoneMetric } from "./pixelModel";

interface PixelZoneProps {
  zone: PixelZoneDefinition;
  metrics: PixelMetrics;
  selected: boolean;
  hovered: boolean;
  onHover: (zone: PixelZoneDefinition | null) => void;
  onSelect: (zone: PixelZoneDefinition) => void;
  onOpen: (zone: PixelZoneDefinition) => void;
  showLabels: boolean;
}

const toneStyle: Record<PixelZoneDefinition["tone"], { border: string; bg: string; glow: string; light: string }> = {
  neutral: {
    border: "rgba(148, 163, 184, 0.42)",
    bg: "rgba(30, 41, 59, 0.72)",
    glow: "rgba(148, 163, 184, 0.16)",
    light: "#94A3B8",
  },
  ready: {
    border: "rgba(42, 157, 143, 0.56)",
    bg: "rgba(20, 83, 69, 0.48)",
    glow: "rgba(42, 157, 143, 0.18)",
    light: "var(--mis-success)",
  },
  active: {
    border: "rgba(46, 134, 171, 0.62)",
    bg: "rgba(15, 70, 112, 0.52)",
    glow: "rgba(46, 134, 171, 0.2)",
    light: "var(--mis-primary)",
  },
  warning: {
    border: "rgba(251, 191, 36, 0.7)",
    bg: "rgba(120, 70, 15, 0.48)",
    glow: "rgba(251, 191, 36, 0.2)",
    light: "#FBBF24",
  },
  danger: {
    border: "rgba(248, 113, 113, 0.7)",
    bg: "rgba(127, 29, 29, 0.52)",
    glow: "rgba(248, 113, 113, 0.22)",
    light: "#F87171",
  },
  purple: {
    border: "rgba(168, 85, 247, 0.62)",
    bg: "rgba(76, 29, 149, 0.45)",
    glow: "rgba(168, 85, 247, 0.22)",
    light: "var(--mis-purple)",
  },
  dock: {
    border: "rgba(34, 211, 238, 0.48)",
    bg: "rgba(8, 80, 100, 0.42)",
    glow: "rgba(34, 211, 238, 0.16)",
    light: "var(--mis-cyan)",
  },
};

export function PixelZone({ zone, metrics, selected, hovered, onHover, onSelect, onOpen, showLabels }: PixelZoneProps) {
  const tone = toneStyle[zone.tone];
  const active = selected || hovered;

  return (
    <button
      type="button"
      onMouseEnter={() => onHover(zone)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(zone)}
      onBlur={() => onHover(null)}
      onClick={(event) => {
        if (event.detail >= 2) {
          onOpen(zone);
          return;
        }
        onSelect(zone);
      }}
      onDoubleClick={() => onOpen(zone)}
      className="absolute overflow-hidden text-left transition-all duration-200"
      style={{
        left: `${zone.x}%`,
        top: `${zone.y}%`,
        width: `${zone.w}%`,
        height: `${zone.h}%`,
        color: "var(--mis-text)",
        background: tone.bg,
        border: `2px solid ${active ? tone.light : tone.border}`,
        boxShadow: active
          ? `0 0 0 2px rgba(255,255,255,0.05), 0 0 24px ${tone.glow}, inset 0 0 0 2px rgba(255,255,255,0.04)`
          : `0 0 12px ${tone.glow}, inset 0 0 0 1px rgba(255,255,255,0.03)`,
        imageRendering: "pixelated",
        clipPath: "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))",
      }}
      aria-label={`Open ${zone.label}`}
      title={`${zone.label}: ${zone.description}`}
    >
      <div
        className="absolute inset-0 opacity-25"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px)",
          backgroundSize: "12px 12px",
        }}
      />
      <div className="relative h-full p-2 flex flex-col justify-between">
        <div className="flex items-start justify-between gap-2">
          {showLabels && (
            <div className="min-w-0">
              <div className="text-[11px] font-semibold leading-tight truncate">{zone.label}</div>
              <div className="text-[9px] leading-tight mt-0.5 truncate" style={{ color: "var(--mis-muted)" }}>
                {zone.metricLabel}
              </div>
            </div>
          )}
          <span
            className="inline-block h-2.5 w-2.5 shrink-0"
            style={{ background: tone.light, boxShadow: `0 0 10px ${tone.light}` }}
          />
        </div>
        {showLabels && (
          <div
            className="self-start rounded px-1.5 py-0.5 text-[9px] font-mono"
            style={{ background: "rgba(2, 6, 23, 0.58)", color: tone.light }}
          >
            {formatZoneMetric(zone.id, metrics)}
          </div>
        )}
      </div>
    </button>
  );
}
