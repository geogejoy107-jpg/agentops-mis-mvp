import type { CSSProperties } from "react";
import type { PixelAgent } from "./pixelModel";

const palettes = [
  ["#f1c6a8", "#30231f", "#2563eb", "#1e3a8a", "#67e8f9"],
  ["#dca77e", "#171717", "#7c3aed", "#4c1d95", "#c4b5fd"],
  ["#f0bd8e", "#7c2d12", "#0f766e", "#134e4a", "#5eead4"],
  ["#9f6849", "#111827", "#b45309", "#78350f", "#fde68a"],
  ["#e9b98f", "#4a2840", "#be185d", "#831843", "#f9a8d4"],
];

function paletteFor(agent: PixelAgent) {
  const key = `${agent.id}:${agent.role}:${agent.runtime}`;
  const sum = Array.from(key).reduce((total, char) => total + char.charCodeAt(0), 0);
  return palettes[sum % palettes.length];
}

function motion(status: string) {
  if (/failed|blocked|error/i.test(status)) return "pixelAgentAlert .45s steps(2,end) infinite";
  if (/waiting|pending|approval|review/i.test(status)) return "pixelAgentWait 1.4s steps(2,end) infinite";
  if (/running|executing|syncing|auditing/i.test(status)) return "pixelAgentWork .85s steps(2,end) infinite";
  return "pixelAgentIdle 1.8s steps(2,end) infinite";
}

export function AgentAvatarV3({ agent, active, risk }: { agent: PixelAgent; active: boolean; risk: string }) {
  const [face, hair, coat, dark, accent] = paletteFor(agent);
  const style: CSSProperties = {
    animation: motion(agent.status),
    imageRendering: "pixelated",
    filter: active ? "drop-shadow(0 0 11px rgba(34,211,238,.72))" : "drop-shadow(0 4px 3px rgba(2,6,23,.7))",
  };
  return (
    <span className="pixel-agent-motion relative block h-[46px] w-[34px]" style={style}>
      <span className="absolute bottom-0 left-[6px] h-[5px] w-[23px] rounded-[50%] bg-slate-950/55" />
      <span className="absolute bottom-[4px] left-[8px] h-[12px] w-[8px] border-2 border-slate-950" style={{ background: dark }} />
      <span className="absolute bottom-[4px] right-[7px] h-[12px] w-[8px] border-2 border-slate-950" style={{ background: dark }} />
      <span className="absolute left-[6px] top-[21px] h-[18px] w-[24px] border-2 border-slate-950" style={{ background: coat }}>
        <span className="absolute left-[4px] top-[3px] h-[3px] w-[12px]" style={{ background: accent }} />
      </span>
      <span className="absolute left-[8px] top-[5px] h-[17px] w-[20px] border-2 border-slate-950" style={{ background: face }}>
        <span className="absolute left-[4px] top-[7px] h-[2px] w-[2px] bg-slate-950" />
        <span className="absolute right-[4px] top-[7px] h-[2px] w-[2px] bg-slate-950" />
      </span>
      <span className="absolute left-[6px] top-[3px] h-[7px] w-[24px] border-2 border-slate-950" style={{ background: hair }} />
      <span className="absolute -right-[5px] top-[23px] h-[10px] w-[9px] border border-slate-950" style={{ background: accent }} />
      <span className="absolute right-[-5px] top-[4px] h-[7px] w-[7px] border border-slate-950" style={{ background: risk, boxShadow: `0 0 8px ${risk}` }} />
    </span>
  );
}
