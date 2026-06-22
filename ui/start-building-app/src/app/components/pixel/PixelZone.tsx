import { PixelRoomSceneRenderer } from "./PixelRoomSceneRenderer";
import type { PixelLocale, PixelMetrics, PixelZoneDefinition } from "./pixelModel";
import { formatZoneMetric, zoneDisplay } from "./pixelModel";
import type { PixelOfficeTheme } from "./pixelOfficeTheme";

interface PixelZoneProps {
  zone: PixelZoneDefinition;
  metrics: PixelMetrics;
  selected: boolean;
  hovered: boolean;
  onHover: (zone: PixelZoneDefinition | null) => void;
  onSelect: (zone: PixelZoneDefinition) => void;
  onOpen: (zone: PixelZoneDefinition) => void;
  showLabels: boolean;
  theme: PixelOfficeTheme;
  dimmed?: boolean;
  locale?: PixelLocale;
}

export function PixelZone({
  zone,
  metrics,
  selected,
  hovered,
  onHover,
  onSelect,
  onOpen,
  showLabels,
  theme,
  dimmed = false,
  locale = "en",
}: PixelZoneProps) {
  const tone = theme.tones[zone.tone];
  const active = selected || hovered;
  const copy = zoneDisplay(zone, locale);

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
      className="absolute overflow-hidden text-left transition-all duration-300"
      style={{
        left: `${zone.x}%`,
        top: `${zone.y}%`,
        width: `${zone.w}%`,
        height: `${zone.h}%`,
        color: "var(--mis-text)",
        background: tone.background,
        border: `2px solid ${active ? tone.light : tone.border}`,
        boxShadow: active ? `${theme.effects.selectedShadow}, 0 0 24px ${tone.glow}` : `${theme.effects.roomShadow}, 0 0 12px ${tone.glow}`,
        imageRendering: "pixelated",
        clipPath: theme.shape.roomClipPath,
        borderRadius: theme.shape.roomRadius,
        opacity: dimmed ? 0.2 : 1,
        pointerEvents: dimmed ? "none" : "auto",
        transform: active && !dimmed ? "translateY(-1px)" : "none",
      }}
      aria-label={locale === "zh" ? `查看${copy.label}` : `Inspect ${copy.label}`}
      title={`${copy.label}: ${copy.description}`}
    >
      <PixelRoomSceneRenderer zone={zone} theme={theme} />
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: `linear-gradient(180deg, ${tone.background} 0%, transparent 34%, transparent 72%, rgba(2,6,23,.3) 100%)` }}
      />
      <div className="relative z-10 flex h-full flex-col justify-between p-2">
        <div className="flex items-start justify-between gap-2">
          {showLabels && (
            <div className="min-w-0 rounded px-1.5 py-1" style={{ background: theme.frame.controlBar, border: `1px solid ${theme.frame.controlBorder}` }}>
              <div className="truncate text-[11px] font-semibold leading-tight">{copy.label}</div>
              <div className="mt-0.5 truncate text-[9px] leading-tight" style={{ color: "var(--mis-muted)" }}>
                {copy.metricLabel}
              </div>
            </div>
          )}
          <span className="inline-block h-2.5 w-2.5 shrink-0" style={{ background: tone.light, boxShadow: `0 0 10px ${tone.light}` }} />
        </div>
        {showLabels && (
          <div
            className="self-start rounded px-1.5 py-0.5 text-[9px] font-mono"
            style={{ background: theme.frame.controlBar, color: tone.light, border: `1px solid ${theme.frame.controlBorder}` }}
          >
            {formatZoneMetric(zone.id, metrics, locale)}
          </div>
        )}
      </div>
    </button>
  );
}