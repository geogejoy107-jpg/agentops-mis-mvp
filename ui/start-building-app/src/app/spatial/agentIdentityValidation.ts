import type { ArtKitManifest, SpatialAgentVisualIdentity } from "./contracts";
import {
  SPATIAL_AGENT_GLYPH_ARCHETYPES,
  SPATIAL_AGENT_PALETTE_SLOTS,
} from "./agentIdentity";

function assertIdentity(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(`[Spatial Agent identity] ${message}`);
}

export function validateAgentIdentityGrammar(artKit: ArtKitManifest): ArtKitManifest {
  const grammar = artKit.agentIdentityGrammar;
  assertIdentity(grammar.schemaVersion === "spatial-agent-identity/v0", "unsupported schemaVersion");
  assertIdentity(grammar.strategy === "archetype-palette-seed", "unsupported strategy");
  assertIdentity(grammar.statusChannel === "separate", "status must remain separate from identity");
  assertIdentity(grammar.riskChannel === "separate", "risk must remain separate from identity");
  assertIdentity(Number.isInteger(grammar.glyphGrid.width) && grammar.glyphGrid.width >= 12, "glyph width must be at least 12");
  assertIdentity(Number.isInteger(grammar.glyphGrid.height) && grammar.glyphGrid.height >= 12, "glyph height must be at least 12");

  const archetypes = new Set(grammar.archetypes);
  assertIdentity(archetypes.size === SPATIAL_AGENT_GLYPH_ARCHETYPES.length, "archetype set is incomplete or duplicated");
  SPATIAL_AGENT_GLYPH_ARCHETYPES.forEach((archetype) => {
    assertIdentity(archetypes.has(archetype), `missing archetype ${archetype}`);
  });

  const palettes = new Set(grammar.paletteSlots);
  assertIdentity(palettes.size === SPATIAL_AGENT_PALETTE_SLOTS.length, "palette set is incomplete or duplicated");
  SPATIAL_AGENT_PALETTE_SLOTS.forEach((palette) => {
    assertIdentity(palettes.has(palette), `missing palette ${palette}`);
  });

  return artKit;
}

export function validateSpatialAgentVisualIdentity(identity: SpatialAgentVisualIdentity): SpatialAgentVisualIdentity {
  assertIdentity(identity.schemaVersion === "spatial-agent-identity/v0", "identity schemaVersion mismatch");
  assertIdentity(SPATIAL_AGENT_GLYPH_ARCHETYPES.includes(identity.archetype), `unsupported archetype ${identity.archetype}`);
  assertIdentity(SPATIAL_AGENT_PALETTE_SLOTS.includes(identity.palette), `unsupported palette ${identity.palette}`);
  assertIdentity(Number.isInteger(identity.seed) && identity.seed >= 0, "seed must be a non-negative integer");
  assertIdentity(identity.variant === 0 || identity.variant === 1 || identity.variant === 2, "variant must be 0, 1 or 2");
  return identity;
}
