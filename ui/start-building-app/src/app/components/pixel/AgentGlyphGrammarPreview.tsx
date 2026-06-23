import type { SpatialAgentVisualIdentity } from "../../spatial/contracts";
import { SPATIAL_AGENT_GLYPH_ARCHETYPES, SPATIAL_AGENT_PALETTE_SLOTS } from "../../spatial/agentIdentity";
import { SimpleAgentGlyph } from "./SimpleAgentGlyph";
import type { PixelLocale } from "./pixelModel";

function previewIdentity(index: number): SpatialAgentVisualIdentity {
  return {
    schemaVersion: "spatial-agent-identity/v0",
    archetype: SPATIAL_AGENT_GLYPH_ARCHETYPES[index],
    palette: SPATIAL_AGENT_PALETTE_SLOTS[index],
    seed: index,
    variant: (index % 3) as 0 | 1 | 2,
  };
}

export function AgentGlyphGrammarPreview({ locale = "en" }: { locale?: PixelLocale }) {
  const zh = locale === "zh";
  return (
    <details className="rounded-md" style={{ background: "rgba(15,23,42,.48)", border: "1px solid rgba(148,163,184,.12)" }}>
      <summary className="cursor-pointer select-none px-3 py-2 text-[9px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>
        {zh ? "查看 12 种原创身份形状" : "View 12 original identity shapes"}
      </summary>
      <div className="grid grid-cols-6 gap-2 px-3 pb-3 pt-1" data-testid="agent-glyph-grammar">
        {SPATIAL_AGENT_GLYPH_ARCHETYPES.map((archetype, index) => {
          const identity = previewIdentity(index);
          return (
            <span key={archetype} className="flex min-w-0 flex-col items-center gap-1" title={archetype}>
              <SimpleAgentGlyph identity={identity} id={`grammar-${archetype}`} name={archetype} size={24} showStatus={false} showRisk={false} label={archetype} />
              <span className="max-w-full truncate text-[7px]" style={{ color: "var(--mis-muted)" }}>{archetype}</span>
            </span>
          );
        })}
      </div>
    </details>
  );
}
