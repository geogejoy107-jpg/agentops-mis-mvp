import { deriveSpatialAgentIdentity } from "../../spatial/agentIdentity";
import { agentGlyphPalette, SimpleAgentGlyph } from "./SimpleAgentGlyph";
import type { PixelAgent, PixelLocale, PixelZoneDefinition } from "./pixelModel";
import { PIXEL_ZONE_BY_ID, zoneCenter } from "./pixelModel";

interface AgentSpriteProps {
  agent: PixelAgent;
  index: number;
  active: boolean;
  onSelect: (agent: PixelAgent) => void;
  locale?: PixelLocale;
}

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
  const identity = deriveSpatialAgentIdentity({ id: agent.id, name: agent.name, role: agent.role, runtime: agent.runtime });
  const palette = agentGlyphPalette(identity);

  return (
    <button
      type="button"
      className="group absolute z-20 -translate-x-1/2 -translate-y-1/2 transition-all duration-[1400ms] ease-in-out"
      style={position}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(agent);
      }}
      aria-label={locale === "zh" ? `查看 ${agent.name}` : `Inspect ${agent.name}`}
      title={`${agent.name} · ${agent.status}`}
      data-agent-archetype={identity.archetype}
      data-agent-palette={identity.palette}
    >
      <span className="sr-only">{agent.name}</span>
      <span className="relative block h-11 w-10">
        <span className="absolute bottom-0 left-1/2 h-2 w-7 -translate-x-1/2 rounded-[50%]" style={{ background: "rgba(2,6,23,.62)" }} />
        <span className="absolute left-1/2 top-0 -translate-x-1/2">
          <SimpleAgentGlyph
            identity={identity}
            id={agent.id}
            name={agent.name}
            role={agent.role}
            runtime={agent.runtime}
            size={34}
            status={agent.status}
            risk={agent.risk}
            selected={active}
            label={`${agent.name} · ${agent.role} · ${agent.status}`}
          />
        </span>
        <span
          className="absolute -bottom-4 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded px-1.5 py-0.5 text-[9px] font-mono group-hover:block group-focus-visible:block"
          style={{ background: "rgba(2,6,23,.9)", color: "var(--mis-text)", border: `1px solid ${palette.primary}` }}
        >
          {agent.name}
        </span>
        {agent.isDemo && (
          <span
            className="absolute -left-3 top-0 rounded px-1 text-[8px] uppercase tracking-wide"
            style={{ background: "rgba(168,85,247,.2)", color: "var(--mis-purple)", border: "1px solid rgba(168,85,247,.35)" }}
          >
            {locale === "zh" ? "演示" : "demo"}
          </span>
        )}
      </span>
    </button>
  );
}
