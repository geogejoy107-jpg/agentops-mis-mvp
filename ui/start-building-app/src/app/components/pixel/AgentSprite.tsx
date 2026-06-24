import type { PixelAgent, PixelLocale, PixelZoneDefinition } from "./pixelModel";
import { PIXEL_ZONE_BY_ID, zoneCenter } from "./pixelModel";

interface AgentSpriteProps {
  agent: PixelAgent;
  index: number;
  active: boolean;
  onSelect: (agent: PixelAgent) => void;
  locale?: PixelLocale;
}

const riskColor: Record<PixelAgent["risk"], string> = {
  low: "var(--mis-success)",
  medium: "#FBBF24",
  high: "var(--mis-warning)",
  critical: "#F87171",
};

function agentPosition(zone: PixelZoneDefinition, index: number) {
  const center = zoneCenter(zone, index);
  return {
    left: `${center.x}%`,
    top: `${center.y}%`,
  };
}

export function AgentSprite({ agent, index, active, onSelect, locale = "en" }: AgentSpriteProps) {
  const targetZone = PIXEL_ZONE_BY_ID[agent.targetZone] || PIXEL_ZONE_BY_ID.agent_lobby;
  const position = agentPosition(targetZone, index);
  const color = riskColor[agent.risk] || riskColor.low;

  return (
    <button
      type="button"
      className="absolute z-20 -translate-x-1/2 -translate-y-1/2 transition-all duration-[1400ms] ease-in-out group"
      style={position}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(agent);
      }}
      aria-label={locale === "zh" ? `查看 ${agent.name}` : `Inspect ${agent.name}`}
      title={`${agent.name} · ${agent.status}`}
    >
      <span className="sr-only">{agent.name}</span>
      <div
        className="relative h-10 w-8"
        style={{
          filter: active ? "drop-shadow(0 0 12px rgba(34,211,238,0.55))" : "drop-shadow(0 3px 8px rgba(0,0,0,0.45))",
        }}
      >
        <div
          className="absolute left-1/2 top-0 h-3 w-5 -translate-x-1/2"
          style={{
            background: active ? "var(--mis-cyan)" : "#CBD5E1",
            border: "2px solid #0B1020",
            boxShadow: "0 0 0 1px rgba(255,255,255,0.08)",
          }}
        />
        <div
          className="absolute left-1/2 top-3 h-5 w-7 -translate-x-1/2"
          style={{
            background: active ? "rgba(34,211,238,0.95)" : "rgba(46,134,171,0.92)",
            border: "2px solid #0B1020",
            boxShadow: "inset 0 0 0 2px rgba(255,255,255,0.1)",
          }}
        />
        <div className="absolute bottom-1 left-1 h-2 w-2" style={{ background: "#0B1020" }} />
        <div className="absolute bottom-1 right-1 h-2 w-2" style={{ background: "#0B1020" }} />
        <div
          className="absolute -right-1 top-2 h-2.5 w-2.5"
          style={{ background: color, boxShadow: `0 0 10px ${color}`, border: "1px solid #0B1020" }}
        />
        <div
          className="absolute -bottom-4 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded px-1.5 py-0.5 text-[9px] font-mono group-hover:block"
          style={{ background: "rgba(2,6,23,0.88)", color: "var(--mis-text)", border: "1px solid rgba(148,163,184,0.25)" }}
        >
          {agent.name}
        </div>
        {agent.isDemo && (
          <div
            className="absolute -left-3 top-0 rounded px-1 text-[8px] uppercase tracking-wide"
            style={{ background: "rgba(168,85,247,0.2)", color: "var(--mis-purple)", border: "1px solid rgba(168,85,247,0.35)" }}
          >
            {locale === "zh" ? "演示" : "demo"}
          </div>
        )}
      </div>
    </button>
  );
}
