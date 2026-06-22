import { AgentAvatar } from "./AgentAvatar";
import type { PixelAgent, PixelLocale, PixelZoneDefinition } from "./pixelModel";
import { PIXEL_ZONE_BY_ID, zoneCenter } from "./pixelModel";
import type { PixelOfficeTheme } from "./pixelOfficeTheme";

interface AgentSpriteProps {
  agent: PixelAgent;
  index: number;
  active: boolean;
  onSelect: (agent: PixelAgent) => void;
  theme: PixelOfficeTheme;
  dimmed?: boolean;
  locale?: PixelLocale;
}

const signalTone: Record<PixelAgent["risk"], "ready" | "warning" | "danger"> = {
  low: "ready",
  medium: "warning",
  high: "warning",
  critical: "danger",
};

function agentPosition(zone: PixelZoneDefinition, index: number) {
  const center = zoneCenter(zone, index);
  return {
    left: `${center.x}%`,
    top: `${center.y}%`,
  };
}

export function AgentSprite({ agent, index, active, onSelect, theme, dimmed = false, locale = "en" }: AgentSpriteProps) {
  const targetZone = PIXEL_ZONE_BY_ID[agent.targetZone] || PIXEL_ZONE_BY_ID.agent_lobby;
  const position = agentPosition(targetZone, index);
  const signal = theme.tones[signalTone[agent.risk] || "ready"].light;

  return (
    <button
      type="button"
      className="group absolute z-20 -translate-x-1/2 -translate-y-1/2 transition-all duration-[900ms] ease-in-out"
      style={{ ...position, opacity: dimmed ? 0.18 : 1, pointerEvents: dimmed ? "none" : "auto" }}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(agent);
      }}
      aria-label={locale === "zh" ? `查看 ${agent.name}` : `Inspect ${agent.name}`}
      title={`${agent.name} · ${agent.status}`}
    >
      <span className="sr-only">{agent.name}</span>
      <div className="relative">
        <AgentAvatar agent={agent} active={active} signal={signal} theme={theme} />
        <div
          className="absolute -bottom-4 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded px-1.5 py-0.5 text-[9px] font-mono group-hover:block group-focus:block"
          style={{ background: theme.frame.controlBar, color: "var(--mis-text)", border: `1px solid ${theme.frame.controlBorder}` }}
        >
          {agent.name}
        </div>
        {agent.isDemo && (
          <div
            className="absolute -left-3 top-0 rounded px-1 text-[8px] uppercase tracking-wide"
            style={{ background: theme.tones.purple.background, color: theme.tones.purple.light, border: `1px solid ${theme.tones.purple.border}` }}
          >
            {locale === "zh" ? "演示" : "demo"}
          </div>
        )}
      </div>
    </button>
  );
}