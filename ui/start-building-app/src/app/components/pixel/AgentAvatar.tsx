import type { CSSProperties } from "react";
import type { PixelAgent } from "./pixelModel";
import type { PixelOfficeTheme } from "./pixelOfficeTheme";

function paletteFor(agent: PixelAgent, theme: PixelOfficeTheme) {
  const seed = `${agent.id}:${agent.role}:${agent.runtime}`.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return theme.characterPalettes[seed % theme.characterPalettes.length];
}

function animationFor(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("blocked") || normalized.includes("error")) return "pixelAgentAlert .45s steps(2,end) infinite";
  if (normalized.includes("waiting") || normalized.includes("pending") || normalized.includes("review")) return "pixelAgentWait 1.4s steps(2,end) infinite";
  if (normalized.includes("running") || normalized.includes("executing") || normalized.includes("syncing")) return "pixelAgentWork .85s steps(2,end) infinite";
  return "pixelAgentIdle 1.8s steps(2,end) infinite";
}

export function AgentAvatar({ agent, active, signal, theme }: { agent: PixelAgent; active: boolean; signal: string; theme: PixelOfficeTheme }) {
  const [face, hair, coat, dark, accent] = paletteFor(agent, theme);
  const style: CSSProperties = {
    animation: animationFor(agent.status),
    imageRendering: "pixelated",
    filter: active ? theme.effects.selectedAgentShadow : theme.effects.agentShadow,
  };

  return (
    <span className="pixel-agent-motion relative block h-[46px] w-[34px]" style={style}>
      <span className="absolute bottom-0 left-[6px] h-[5px] w-[23px] rounded-[50%]" style={{ background: theme.frame.insetBorder }} />
      <span className="absolute bottom-[4px] left-[8px] h-[12px] w-[8px] border-2" style={{ background: dark, borderColor: theme.materials.outline }} />
      <span className="absolute bottom-[4px] right-[7px] h-[12px] w-[8px] border-2" style={{ background: dark, borderColor: theme.materials.outline }} />
      <span className="absolute left-[6px] top-[21px] h-[18px] w-[24px] border-2" style={{ background: coat, borderColor: theme.materials.outline }}>
        <span className="absolute left-[4px] top-[3px] h-[3px] w-[12px]" style={{ background: accent }} />
      </span>
      <span className="absolute left-[8px] top-[5px] h-[17px] w-[20px] border-2" style={{ background: face, borderColor: theme.materials.outline }}>
        <span className="absolute left-[4px] top-[7px] h-[2px] w-[2px]" style={{ background: theme.materials.outline }} />
        <span className="absolute right-[4px] top-[7px] h-[2px] w-[2px]" style={{ background: theme.materials.outline }} />
      </span>
      <span className="absolute left-[6px] top-[3px] h-[7px] w-[24px] border-2" style={{ background: hair, borderColor: theme.materials.outline }} />
      <span className="absolute -right-[5px] top-[23px] h-[10px] w-[9px] border" style={{ background: accent, borderColor: theme.materials.outline }} />
      <span className="absolute right-[-5px] top-[4px] h-[7px] w-[7px] border" style={{ background: signal, borderColor: theme.materials.outline, boxShadow: `0 0 8px ${signal}` }} />
    </span>
  );
}