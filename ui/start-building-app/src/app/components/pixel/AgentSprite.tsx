import type { PixelAgent, PixelLocale, PixelZoneDefinition } from "./pixelModel";
import { PIXEL_ZONE_BY_ID, zoneCenter } from "./pixelModel";
import { AgentAvatarV3 } from "./AgentAvatarV3";

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
  const point = zoneCenter(zone, index);
  return { left: `${point.x}%`, top: `${point.y}%` };
}

export function AgentSprite({ agent, index, active, onSelect, locale = "en" }: AgentSpriteProps) {
  const targetZone = PIXEL_ZONE_BY_ID[agent.targetZone] || PIXEL_ZONE_BY_ID.agent_lobby;
  const risk = riskColor[agent.risk] || riskColor.low;
  return (
    <button
      type="button"
      className="group absolute z-20 -translate-x-1/2 -translate-y-1/2 transition-[left,top] duration-[1400ms] ease-in-out"
      style={agentPosition(targetZone, index)}
      onClick={(event) => { event.stopPropagation(); onSelect(agent); }}
      aria-label={locale === "zh" ? `查看 ${agent.name}` : `Inspect ${agent.name}`}
      title={`${agent.name} · ${agent.status}`}
    >
      <span className="sr-only">{agent.name}</span>
      <AgentAvatarV3 agent={agent} active={active} risk={risk} />
      <span className="absolute -bottom-[22px] left-1/2 hidden min-w-max -translate-x-1/2 border border-slate-500/30 px-1.5 py-1 text-[8px] font-mono group-hover:block group-focus:block" style={{ background: "rgba(2,6,23,.94)", color: "var(--mis-text)" }}>
        <strong className="block">{agent.name}</strong>
        <span style={{ color: "var(--mis-muted)" }}>{agent.runtime} · {agent.status}</span>
      </span>
      {agent.isDemo && <span className="absolute -left-[10px] top-0 px-1 text-[7px] uppercase" style={{ background: "rgba(168,85,247,.3)", color: "#ddd6fe", border: "1px solid rgba(196,181,253,.42)" }}>{locale === "zh" ? "演示" : "demo"}</span>}
    </button>
  );
}
