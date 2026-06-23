import { deriveSpatialAgentIdentity } from "../../spatial/agentIdentity";
import { SimpleAgentGlyph } from "./SimpleAgentGlyph";
import type { PixelAgent, PixelLocale } from "./pixelModel";
import { statusDisplay } from "./pixelModel";

interface AgentGlyphRosterProps {
  agents: PixelAgent[];
  selectedAgentId?: string | null;
  onOpenAgent: (agent: PixelAgent) => void;
  locale?: PixelLocale;
}

export function AgentGlyphRoster({ agents, selectedAgentId, onOpenAgent, locale = "en" }: AgentGlyphRosterProps) {
  const zh = locale === "zh";
  return (
    <section className="overflow-hidden rounded-md" style={{ background: "rgba(15,23,42,.68)", border: "1px solid rgba(148,163,184,.16)" }} data-testid="agent-glyph-roster" aria-labelledby="agent-glyph-roster-title">
      <div className="flex items-center justify-between gap-3 px-3 py-2" style={{ borderBottom: "1px solid rgba(148,163,184,.12)" }}>
        <div>
          <h3 id="agent-glyph-roster-title" className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{zh ? "Agent 身份栏" : "Agent identity rail"}</h3>
          <p className="mt-0.5 text-[9px]" style={{ color: "var(--mis-muted)" }}>{zh ? "形状代表身份；状态与风险独立显示" : "Shape identifies; state and risk stay separate"}</p>
        </div>
        <span className="rounded px-1.5 py-0.5 text-[9px] font-mono" style={{ background: "rgba(148,163,184,.1)", color: "var(--mis-muted)" }}>{agents.length}</span>
      </div>
      <div className="max-h-64 overflow-auto py-1">
        {agents.length === 0 && <p className="px-3 py-3 text-[10px]" style={{ color: "var(--mis-muted)" }}>{zh ? "暂无可显示 Agent。" : "No Agents available."}</p>}
        {agents.map((agent) => {
          const identity = deriveSpatialAgentIdentity({ id: agent.id, name: agent.name, role: agent.role, runtime: agent.runtime });
          const selected = selectedAgentId === agent.id;
          return (
            <button key={agent.id} type="button" onClick={() => onOpenAgent(agent)} className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left hover:bg-white/[.04]" style={{ background: selected ? "rgba(34,211,238,.08)" : "transparent" }} data-agent-id={agent.id} data-agent-archetype={identity.archetype}>
              <SimpleAgentGlyph identity={identity} id={agent.id} name={agent.name} role={agent.role} runtime={agent.runtime} size={22} status={agent.status} risk={agent.risk} selected={selected} label={`${agent.name} · ${agent.role} · ${statusDisplay(agent.status, locale)}`} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[11px] font-medium" style={{ color: "var(--mis-text)" }}>{agent.name}</span>
                <span className="mt-0.5 block truncate text-[9px]" style={{ color: "var(--mis-muted)" }}>{agent.role} · {agent.runtime}</span>
              </span>
              <span className="shrink-0 text-[9px]" style={{ color: "var(--mis-dim)" }}>{statusDisplay(agent.status, locale)}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
