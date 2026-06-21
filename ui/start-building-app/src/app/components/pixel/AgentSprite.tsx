import type { CSSProperties } from "react";
import type { PixelAgent, PixelZoneDefinition } from "./pixelModel";
import { PIXEL_ZONE_BY_ID, zoneCenter } from "./pixelModel";

interface AgentSpriteProps {
  agent: PixelAgent;
  index: number;
  active: boolean;
  onSelect: (agent: PixelAgent) => void;
}

interface CharacterPalette {
  skin: string;
  skinShade: string;
  hair: string;
  jacket: string;
  jacketShade: string;
  accent: string;
  trousers: string;
}

const riskColor: Record<PixelAgent["risk"], string> = {
  low: "var(--mis-success)",
  medium: "#FBBF24",
  high: "var(--mis-warning)",
  critical: "#F87171",
};

const CHARACTER_PALETTES: CharacterPalette[] = [
  { skin: "#f1c6a8", skinShade: "#c98e70", hair: "#30231f", jacket: "#2563eb", jacketShade: "#1e3a8a", accent: "#67e8f9", trousers: "#172554" },
  { skin: "#dca77e", skinShade: "#9a6647", hair: "#171717", jacket: "#7c3aed", jacketShade: "#4c1d95", accent: "#c4b5fd", trousers: "#2e1065" },
  { skin: "#f0bd8e", skinShade: "#bd7b50", hair: "#7c2d12", jacket: "#0f766e", jacketShade: "#134e4a", accent: "#5eead4", trousers: "#042f2e" },
  { skin: "#9f6849", skinShade: "#6b3f2b", hair: "#111827", jacket: "#b45309", jacketShade: "#78350f", accent: "#fde68a", trousers: "#451a03" },
  { skin: "#e9b98f", skinShade: "#b77954", hair: "#4a2840", jacket: "#be185d", jacketShade: "#831843", accent: "#f9a8d4", trousers: "#500724" },
  { skin: "#c98b63", skinShade: "#89583d", hair: "#253047", jacket: "#475569", jacketShade: "#1e293b", accent: "#94a3b8", trousers: "#0f172a" },
];

function agentPosition(zone: PixelZoneDefinition, index: number) {
  const center = zoneCenter(zone, index);
  return {
    left: `${center.x}%`,
    top: `${center.y}%`,
  };
}

function stablePalette(agent: PixelAgent) {
  const seed = `${agent.id}:${agent.role}:${agent.runtime}`;
  const value = Array.from(seed).reduce((sum, character) => sum + character.charCodeAt(0), 0);
  return CHARACTER_PALETTES[value % CHARACTER_PALETTES.length];
}

function animationForStatus(status: string) {
  const normalized = status.toLowerCase();
  if (["running", "executing", "syncing", "auditing"].some((value) => normalized.includes(value))) {
    return "pixelAgentWork .85s steps(2, end) infinite";
  }
  if (["waiting", "pending", "approval", "review"].some((value) => normalized.includes(value))) {
    return "pixelAgentWait 1.4s steps(2, end) infinite";
  }
  if (["failed", "blocked", "error"].some((value) => normalized.includes(value))) {
    return "pixelAgentAlert .45s steps(2, end) infinite";
  }
  return "pixelAgentIdle 1.8s steps(2, end) infinite";
}

function Accessory({ agent, palette }: { agent: PixelAgent; palette: CharacterPalette }) {
  const role = `${agent.role} ${agent.name}`.toLowerCase();

  if (role.includes("research") || role.includes("memory") || role.includes("archiv")) {
    return (
      <span className="absolute -right-[5px] top-[22px] h-[12px] w-[9px] border border-slate-950" style={{ background: palette.accent }}>
        <span className="absolute left-[3px] top-0 h-full w-[1px] bg-slate-900/60" />
      </span>
    );
  }

  if (role.includes("review") || role.includes("quality") || role.includes("audit")) {
    return (
      <span className="absolute -right-[5px] top-[20px] h-[14px] w-[10px] border border-slate-950 bg-amber-100">
        <span className="absolute left-[2px] top-[3px] h-[1px] w-[6px] bg-slate-600" />
        <span className="absolute left-[2px] top-[6px] h-[1px] w-[5px] bg-slate-600" />
        <span className="absolute left-[2px] top-[9px] h-[1px] w-[6px] bg-slate-600" />
      </span>
    );
  }

  if (role.includes("coding") || role.includes("builder") || role.includes("connector") || role.includes("sync")) {
    return (
      <span className="absolute -right-[7px] top-[21px] h-[11px] w-[12px] border border-slate-950 bg-slate-800">
        <span className="absolute left-[2px] top-[2px] h-[5px] w-[8px]" style={{ background: palette.accent, boxShadow: `0 0 6px ${palette.accent}` }} />
        <span className="absolute -top-[5px] right-[1px] h-[5px] w-[1px] bg-slate-300" />
      </span>
    );
  }

  return <span className="absolute -right-[3px] top-[24px] h-[7px] w-[7px] border border-slate-950" style={{ background: palette.accent }} />;
}

export function AgentSprite({ agent, index, active, onSelect }: AgentSpriteProps) {
  const targetZone = PIXEL_ZONE_BY_ID[agent.targetZone] || PIXEL_ZONE_BY_ID.agent_lobby;
  const position = agentPosition(targetZone, index);
  const risk = riskColor[agent.risk] || riskColor.low;
  const palette = stablePalette(agent);
  const characterStyle: CSSProperties = {
    animation: animationForStatus(agent.status),
    imageRendering: "pixelated",
    filter: active ? "drop-shadow(0 0 11px rgba(34,211,238,.72))" : "drop-shadow(0 4px 3px rgba(2,6,23,.7))",
  };

  return (
    <button
      type="button"
      className="group absolute z-20 -translate-x-1/2 -translate-y-1/2 transition-[left,top,filter] duration-[1400ms] ease-in-out"
      style={position}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(agent);
      }}
      aria-label={`Inspect ${agent.name}`}
      title={`${agent.name} · ${agent.status}`}
    >
      <span className="sr-only">{agent.name}</span>
      <span className="relative block h-[48px] w-[36px]" style={characterStyle}>
        <span className="absolute bottom-[1px] left-[7px] h-[5px] w-[24px] bg-slate-950/55" style={{ borderRadius: "50%" }} />

        <span className="absolute bottom-[5px] left-[9px] h-[11px] w-[7px] border-x-2 border-slate-950" style={{ background: palette.trousers }} />
        <span className="absolute bottom-[5px] right-[8px] h-[11px] w-[7px] border-x-2 border-slate-950" style={{ background: palette.trousers }} />
        <span className="absolute bottom-[3px] left-[7px] h-[4px] w-[10px] bg-slate-950" />
        <span className="absolute bottom-[3px] right-[6px] h-[4px] w-[10px] bg-slate-950" />

        <span className="absolute left-[7px] top-[22px] h-[17px] w-[23px] border-2 border-slate-950" style={{ background: palette.jacket }}>
          <span className="absolute bottom-0 left-1/2 h-full w-[2px] -translate-x-1/2" style={{ background: palette.jacketShade }} />
          <span className="absolute left-[4px] top-[2px] h-[3px] w-[11px]" style={{ background: palette.accent }} />
          <span className="absolute left-[4px] top-[7px] h-[3px] w-[3px] bg-slate-100/80" />
        </span>
        <span className="absolute left-[3px] top-[24px] h-[13px] w-[6px] border-2 border-slate-950" style={{ background: palette.jacketShade }} />
        <span className="absolute right-[1px] top-[24px] h-[13px] w-[6px] border-2 border-slate-950" style={{ background: palette.jacketShade }} />
        <span className="absolute left-[2px] top-[34px] h-[5px] w-[6px] border border-slate-950" style={{ background: palette.skin }} />
        <span className="absolute right-0 top-[34px] h-[5px] w-[6px] border border-slate-950" style={{ background: palette.skin }} />

        <span className="absolute left-[9px] top-[6px] h-[17px] w-[19px] border-2 border-slate-950" style={{ background: palette.skin }}>
          <span className="absolute left-[3px] top-[7px] h-[2px] w-[2px] bg-slate-950" />
          <span className="absolute right-[3px] top-[7px] h-[2px] w-[2px] bg-slate-950" />
          <span className="absolute left-[7px] top-[12px] h-[2px] w-[5px]" style={{ background: palette.skinShade }} />
        </span>
        <span className="absolute left-[7px] top-[4px] h-[7px] w-[23px] border-2 border-slate-950" style={{ background: palette.hair }} />
        <span className="absolute left-[7px] top-[9px] h-[9px] w-[5px] border-l-2 border-slate-950" style={{ background: palette.hair }} />
        <span className="absolute right-[6px] top-[9px] h-[7px] w-[5px] border-r-2 border-slate-950" style={{ background: palette.hair }} />
        <span className="absolute left-[4px] top-[13px] h-[6px] w-[4px] border border-slate-950" style={{ background: palette.skinShade }} />
        <span className="absolute right-[3px] top-[13px] h-[6px] w-[4px] border border-slate-950" style={{ background: palette.skinShade }} />

        <Accessory agent={agent} palette={palette} />

        <span
          className="absolute right-[-5px] top-[4px] h-[7px] w-[7px] border border-slate-950"
          style={{ background: risk, boxShadow: `0 0 8px ${risk}` }}
        />

        <span
          className="absolute -bottom-[19px] left-1/2 hidden min-w-max -translate-x-1/2 border border-slate-500/30 px-1.5 py-1 text-[8px] font-mono group-hover:block group-focus:block"
          style={{ background: "rgba(2,6,23,.94)", color: "var(--mis-text)", boxShadow: "2px 2px 0 rgba(2,6,23,.45)" }}
        >
          <strong className="block font-semibold">{agent.name}</strong>
          <span style={{ color: "var(--mis-muted)" }}>{agent.runtime} · {agent.status}</span>
        </span>

        {agent.isDemo && (
          <span
            className="absolute -left-[10px] top-0 px-1 text-[7px] uppercase tracking-wide"
            style={{ background: "rgba(168,85,247,.3)", color: "#ddd6fe", border: "1px solid rgba(196,181,253,.42)" }}
          >
            demo
          </span>
        )}
      </span>
    </button>
  );
}
