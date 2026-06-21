import type { PixelLocale, PixelMetrics, PixelZoneDefinition } from "./pixelModel";
import { formatZoneMetric, zoneDisplay } from "./pixelModel";
import { PixelRoomSceneRenderer } from "./PixelRoomSceneRenderer";

interface PixelZoneProps {
  zone: PixelZoneDefinition;
  metrics: PixelMetrics;
  selected: boolean;
  hovered: boolean;
  onHover: (zone: PixelZoneDefinition | null) => void;
  onSelect: (zone: PixelZoneDefinition) => void;
  onOpen: (zone: PixelZoneDefinition) => void;
  showLabels: boolean;
  locale?: PixelLocale;
}

const toneStyle: Record<PixelZoneDefinition["tone"], { border: string; glow: string; light: string }> = {
  neutral: { border: "rgba(148,163,184,.42)", glow: "rgba(148,163,184,.16)", light: "#94A3B8" },
  ready: { border: "rgba(42,157,143,.56)", glow: "rgba(42,157,143,.18)", light: "var(--mis-success)" },
  active: { border: "rgba(46,134,171,.62)", glow: "rgba(46,134,171,.2)", light: "var(--mis-primary)" },
  warning: { border: "rgba(251,191,36,.7)", glow: "rgba(251,191,36,.2)", light: "#FBBF24" },
  danger: { border: "rgba(248,113,113,.7)", glow: "rgba(248,113,113,.22)", light: "#F87171" },
  purple: { border: "rgba(168,85,247,.62)", glow: "rgba(168,85,247,.22)", light: "var(--mis-purple)" },
  dock: { border: "rgba(34,211,238,.48)", glow: "rgba(34,211,238,.16)", light: "var(--mis-cyan)" },
};

export function PixelZone({ zone, metrics, selected, hovered, onHover, onSelect, onOpen, showLabels, locale = "en" }: PixelZoneProps) {
  const tone = toneStyle[zone.tone];
  const active = selected || hovered;
  const copy = zoneDisplay(zone, locale);

  return (
    <button
      type="button"
      onMouseEnter={() => onHover(zone)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(zone)}
      onBlur={() => onHover(null)}
      onClick={(event) => event.detail >= 2 ? onOpen(zone) : onSelect(zone)}
      onDoubleClick={() => onOpen(zone)}
      className="absolute overflow-hidden text-left transition-all duration-200"
      style={{
        left: `${zone.x}%`, top: `${zone.y}%`, width: `${zone.w}%`, height: `${zone.h}%`,
        color: "var(--mis-text)", border: `2px solid ${active ? tone.light : tone.border}`,
        boxShadow: active
          ? `0 0 0 2px rgba(255,255,255,.05),0 0 24px ${tone.glow},4px 5px 0 rgba(2,6,23,.38)`
          : `0 0 12px ${tone.glow},3px 4px 0 rgba(2,6,23,.3)`,
        imageRendering: "pixelated",
        clipPath: "polygon(0 0,calc(100% - 8px) 0,100% 8px,100% 100%,8px 100%,0 calc(100% - 8px))",
        transform: active ? "translateY(-2px)" : "translateY(0)",
      }}
      aria-label={locale === "zh" ? `打开${copy.label}` : `Open ${copy.label}`}
      title={`${copy.label}: ${copy.description}`}
    >
      <PixelRoomSceneRenderer zone={zone} />
      <div className="pointer-events-none absolute inset-0 z-[1]" style={{ background: active ? `linear-gradient(135deg,${tone.glow},transparent 42%)` : "linear-gradient(180deg,rgba(255,255,255,.025),transparent 45%)" }} />
      <div className="relative z-10 flex h-full flex-col justify-between p-2">
        <div className="flex items-start justify-between gap-2">
          {showLabels && (
            <div className="min-w-0 px-1.5 py-1" style={{ background: "rgba(2,6,23,.74)", border: "1px solid rgba(148,163,184,.18)", boxShadow: "2px 2px 0 rgba(2,6,23,.38)" }}>
              <div className="truncate text-[10px] font-semibold leading-tight tracking-wide">{copy.label}</div>
              <div className="mt-0.5 truncate text-[8px] leading-tight" style={{ color: "var(--mis-muted)" }}>{copy.metricLabel}</div>
            </div>
          )}
          <span className="inline-block h-2.5 w-2.5 shrink-0" style={{ background: tone.light, boxShadow: `0 0 10px ${tone.light}`, border: "1px solid #020617" }} />
        </div>
        {showLabels && (
          <div className="self-start px-1.5 py-0.5 text-[9px] font-mono" style={{ background: "rgba(2,6,23,.74)", color: tone.light, border: "1px solid rgba(148,163,184,.16)" }}>
            {formatZoneMetric(zone.id, metrics, locale)}
          </div>
        )}
      </div>
    </button>
  );
}
