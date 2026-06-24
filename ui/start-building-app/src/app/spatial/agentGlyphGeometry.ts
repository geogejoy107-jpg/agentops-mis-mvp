import type { SpatialAgentVisualIdentity } from "./contracts";
import { AGENT_GLYPH_PATTERNS } from "./agentGlyphPatterns";
import { AGENT_GLYPH_PALETTES, type AgentGlyphPalette } from "./agentGlyphPalettes";

export { AGENT_GLYPH_PALETTES } from "./agentGlyphPalettes";
export type { AgentGlyphPalette } from "./agentGlyphPalettes";

export interface AgentGlyphRect {
  x: number;
  y: number;
  width: number;
  height: number;
  layer?: "primary" | "secondary";
}

export function agentGlyphPalette(identity: SpatialAgentVisualIdentity): AgentGlyphPalette {
  return AGENT_GLYPH_PALETTES[identity.palette];
}

export function agentGlyphRects(identity: SpatialAgentVisualIdentity): readonly AgentGlyphRect[] {
  const rows = AGENT_GLYPH_PATTERNS[identity.archetype];
  const rects: AgentGlyphRect[] = [];
  rows.forEach((row, y) => {
    let start = -1;
    let token = "0";
    const flush = (x: number) => {
      if (start < 0) return;
      rects.push({ x: start, y, width: x - start, height: 1, ...(token === "2" ? { layer: "secondary" as const } : {}) });
      start = -1;
    };
    for (let x = 0; x <= row.length; x += 1) {
      const next = row[x] || "0";
      if (next !== token) flush(x);
      if (next !== "0" && start < 0) start = x;
      token = next;
    }
  });
  rects.push(identity.variant === 1
    ? { x: 10, y: 0, width: 2, height: 2, layer: "secondary" }
    : identity.variant === 2
      ? { x: 0, y: 10, width: 2, height: 2, layer: "secondary" }
      : { x: 0, y: 0, width: 2, height: 2, layer: "secondary" });
  return rects;
}

export function drawAgentGlyphCanvas(
  context: CanvasRenderingContext2D,
  identity: SpatialAgentVisualIdentity,
  x: number,
  y: number,
  pixelSize = 1,
  background = true,
): void {
  const colors = agentGlyphPalette(identity);
  if (background) {
    context.fillStyle = colors.surface;
    context.fillRect(Math.round(x), Math.round(y), 12 * pixelSize, 12 * pixelSize);
    context.strokeStyle = colors.outline;
    context.lineWidth = Math.max(1, pixelSize);
    context.strokeRect(Math.round(x) + 0.5, Math.round(y) + 0.5, 12 * pixelSize - 1, 12 * pixelSize - 1);
  }
  for (const rect of agentGlyphRects(identity)) {
    context.fillStyle = rect.layer === "secondary" ? colors.secondary : colors.primary;
    context.fillRect(
      Math.round(x + rect.x * pixelSize),
      Math.round(y + rect.y * pixelSize),
      Math.max(1, Math.round(rect.width * pixelSize)),
      Math.max(1, Math.round(rect.height * pixelSize)),
    );
  }
}
