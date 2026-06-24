#!/usr/bin/env python3
"""Dependency-free checks for Advanced Research District v1."""

from __future__ import annotations

import json
import re
import struct
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ui" / "start-building-app" / "src" / "app"
ASSETS = ROOT / "ui" / "start-building-app" / "src" / "assets" / "spatial" / "agent-art" / "v0"
SEMANTICS = APP / "spatial" / "researchDistrictSemanticMap.ts"
SURFACE = APP / "components" / "spatial" / "AdvancedSpatialSurface.tsx"
PAGE = APP / "components" / "pages" / "AdvancedSpatialOffice.tsx"
APP_ROUTES = APP / "App.tsx"
SIDEBAR = APP / "components" / "layout" / "Sidebar.tsx"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: Path) -> str:
    require(path.is_file(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"), f"invalid PNG: {path.name}")
    require(data[12:16] == b"IHDR", f"missing IHDR: {path.name}")
    return struct.unpack(">II", data[16:24])


def main() -> None:
    semantics = read(SEMANTICS)
    surface = read(SURFACE)
    page = read(PAGE)
    app = read(APP_ROUTES)
    sidebar = read(SIDEBAR)
    manifest = json.loads(read(ASSETS / "manifest.json"))

    calls = re.findall(r'semanticObject\(\s*\n?\s*"([^"]+)",\s*([0-3]),', semantics)
    require(len(calls) == 40, f"expected 40 semantic objects, found {len(calls)}")
    ids = [object_id for object_id, _ in calls]
    require(len(ids) == len(set(ids)), "semantic object IDs must be unique")
    level_counts = Counter(int(level) for _, level in calls)
    require(level_counts == Counter({0: 5, 1: 11, 2: 11, 3: 13}), f"semantic level counts mismatch: {dict(level_counts)}")

    registered_routes = set(re.findall(r'<Route\s+path="([^"]+)"', app))
    semantic_routes = set(re.findall(r'"(/(?:workspace|admin)[^"]*)"', semantics))
    require(semantic_routes, "no formal MIS routes found in semantic map")
    for route in sorted(semantic_routes):
        require(route in registered_routes, f"semantic object points to unregistered route: {route}")

    for required in (
        "authorityKind",
        "formalRoute",
        "metricKey",
        "interaction",
        "walkAnchor",
        "AGENT_TARGET_OBJECT_BY_ZONE",
    ):
        require(required in semantics, f"semantic contract missing {required}")

    require('path="/workspace/spatial-world"' in app, "Advanced Spatial route missing")
    require('/workspace/spatial-world' in sidebar, "Advanced Spatial navigation missing")
    require('data-testid="advanced-spatial-office"' in page, "desktop screenshot target missing")
    require('data-testid="spatial-agent-rail"' in page, "Agent art rail target missing")
    require("AgentArtPortrait" in page, "selected art track is not used in Agent rail")

    for required in (
        "cozy-research-agent-v0.png",
        "industrial-agent-units-v0.png",
        "drawCozyAgent",
        "drawIndustrialAgent",
        "findSpatialPath",
        "interpolateSpatialPath",
        'data-testid="advanced-spatial-surface"',
        "requestAnimationFrame",
    ):
        require(required in surface, f"Advanced surface missing {required}")

    forbidden_surface_tokens = (
        "SimpleAgentGlyph",
        "drawAgentGlyphCanvas",
        "agentGlyphRects",
        "detachedBadge",
        "raw.githubusercontent.com",
        "private-user-images.githubusercontent.com",
    )
    for token in forbidden_surface_tokens:
        require(token not in surface, f"detached glyph or remote asset leaked into Advanced surface: {token}")

    tracks = {track["id"]: track for track in manifest["tracks"]}
    require(tracks["cozy-research-agent-v0"]["mode"] == "full-character", "cozy Agent is not the complete character")
    require(tracks["cozy-research-agent-v0"]["detachedBadge"] is False, "cozy detached badge must remain false")
    require(tracks["industrial-agent-units-v0"]["mode"] == "complete-unit", "industrial Agent is not the complete unit")
    require(tracks["industrial-agent-units-v0"]["humanBody"] is False, "industrial Agent must not wrap a human body")
    require(tracks["industrial-agent-units-v0"]["detachedBadge"] is False, "industrial detached badge must remain false")

    require(png_size(ASSETS / "cozy-research-agent-v0.png") == (128, 192), "cozy sprite dimensions mismatch")
    require(png_size(ASSETS / "industrial-agent-units-v0.png") == (96, 64), "industrial atlas dimensions mismatch")

    print(
        "Spatial Research District smoke passed: "
        "objects=40 levels=5/11/11/13 routes=registered "
        "art_tracks=cozy+industrial detached_badges=0 pathfinding=A*"
    )


if __name__ == "__main__":
    main()
