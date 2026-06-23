#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ui" / "start-building-app" / "src" / "app"
SPATIAL = APP / "spatial"
PIXEL = APP / "components" / "pixel"

ARCHETYPES = {"bridge", "spark", "forge", "fork", "lattice", "orbit", "archive", "shield", "pulse", "prism", "portal", "stack"}
PALETTES = {"azure", "violet", "amber", "coral", "mint", "rose", "indigo", "lime", "sky", "orange", "slate", "gold"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: Path) -> str:
    require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def main() -> None:
    art_kit = json.loads(read(SPATIAL / "manifests" / "warm-research-art-kit.v0.json"))
    grammar = art_kit.get("agentIdentityGrammar", {})
    require(grammar.get("schemaVersion") == "spatial-agent-identity/v0", "identity schema mismatch")
    require(grammar.get("strategy") == "archetype-palette-seed", "identity strategy mismatch")
    require(set(grammar.get("archetypes", [])) == ARCHETYPES, "archetype set mismatch")
    require(set(grammar.get("paletteSlots", [])) == PALETTES, "palette set mismatch")
    require(grammar.get("statusChannel") == "separate", "status channel must be separate")
    require(grammar.get("riskChannel") == "separate", "risk channel must be separate")
    require(grammar.get("glyphGrid") == {"width": 12, "height": 12}, "glyph grid must be 12x12")

    contracts = read(SPATIAL / "contracts.ts")
    identity = read(SPATIAL / "agentIdentity.ts")
    projection = read(SPATIAL / "basicPixelProjection.ts")
    glyph = read(PIXEL / "SimpleAgentGlyph.tsx")
    roster = read(PIXEL / "AgentGlyphRoster.tsx")
    preview = read(PIXEL / "AgentGlyphGrammarPreview.tsx")
    sprite = read(PIXEL / "AgentSprite.tsx")
    inspector = read(PIXEL / "ZoneInspector.tsx")

    require("SpatialAgentVisualIdentity" in contracts, "visual identity contract missing")
    require("visualIdentity?: SpatialAgentVisualIdentity" in contracts, "entity visual identity missing")
    require("stableAgentIdentityHash" in identity, "stable hash missing")
    require("visualIdentity: deriveSpatialAgentIdentity" in projection, "projection identity missing")
    for item in ARCHETYPES:
        require(f'"{item}"' in identity and f"  {item}: [" in glyph, f"missing archetype {item}")
    for item in PALETTES:
        require(f'"{item}"' in identity, f"missing palette {item}")
    require("shapeRendering=\"crispEdges\"" in glyph, "crisp-edge SVG missing")
    require("data-agent-status-channel" in glyph, "status marker missing")
    require("data-agent-risk-channel" in glyph, "risk marker missing")
    require('data-testid="agent-glyph-roster"' in roster, "roster target missing")
    require('data-testid="agent-glyph-grammar"' in preview, "grammar target missing")
    require("SimpleAgentGlyph" in sprite, "map glyph missing")
    require("AgentGlyphRoster" in inspector, "inspector roster missing")
    print(f"Spatial Agent identity smoke passed: archetypes={len(ARCHETYPES)} palettes={len(PALETTES)}")


if __name__ == "__main__":
    main()
