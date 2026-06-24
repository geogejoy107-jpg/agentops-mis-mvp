#!/usr/bin/env python3
"""Validate the Pixel Office template foundation stays visual-only."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "page": ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "PixelOffice.tsx",
    "selector": ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pixel" / "PixelOfficeThemeSelector.tsx",
    "theme": ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pixel" / "pixelOfficeTheme.ts",
    "packs": ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pixel" / "pixelOfficeThemePacks.ts",
    "spec": ROOT / "docs" / "design" / "PIXEL_OFFICE_TEMPLATE_FOUNDATION.md",
    "handoff": ROOT / "docs" / "project" / "PIXEL_OFFICE_TEMPLATE_HANDOFF.md",
    "plan": ROOT / "docs" / "agent_plans" / "2026-06-22-pixel-office-template-foundation.md",
}

REQUIRED_MARKERS = {
    "page": [
        "PixelOfficeThemeSelector",
        "PIXEL_OFFICE_THEME_STORAGE_KEY",
        "data-pixel-office-theme",
        "getPixelOfficeTheme",
        "<PixelOperatingMap",
        "basicPixelProjectionAdapter",
    ],
    "selector": [
        "role=\"radiogroup\"",
        "role=\"radio\"",
        "ArrowRight",
        "data-testid=\"pixel-office-theme-selector\"",
        "Templates change scene materials and pixel characters only",
    ],
    "theme": [
        "night-shift",
        "cozy-studio",
        "blueprint",
        "harvest-commons",
        "orbital-deck",
        "DEFAULT_PIXEL_OFFICE_THEME_ID",
    ],
    "packs": [
        "harvestCommons",
        "orbitalDeck",
        "characterPalettes",
    ],
    "spec": [
        "Scope: Pixel Office only; no backend or authority semantics change",
        "The selected theme is persisted under `agentops.pixel-office.theme.v1`",
        "Non-negotiable authority boundary",
        "Third-party assets require provenance and license review before inclusion",
    ],
    "handoff": [
        "no backend/authority files changed",
        "Pixel Office Template Foundation",
        "No third-party art assets are approved for bundling",
    ],
    "plan": [
        "plan-pixel-office-template-foundation",
        "Keep formal MIS pages and ledgers authoritative",
        "no server/database/runtime files changed",
    ],
}

FORBIDDEN_PATTERNS = [
    ("bitmap_asset", re.compile(r"['\"][^'\"]+\.(?:png|jpe?g|gif|webp|bmp|aseprite|tmx|tsx|tileset|sprite)['\"]", re.IGNORECASE)),
    ("star_office_import", re.compile(r"from ['\"].*Star-Office", re.IGNORECASE)),
    ("runtime_write_endpoint", re.compile(r"/api/(?:agent-gateway|integrations|operator)/.*(?:run|execute|approve)", re.IGNORECASE)),
    ("secret_literal", re.compile(r"\b(?:sk-|ntn_|agtok_|agtsess_)[A-Za-z0-9._~+/=-]{8,}\b")),
]


def main() -> int:
    failures: list[dict[str, str]] = []
    evidence: dict[str, object] = {"files": {}, "matched_markers": {}}

    for key, path in FILES.items():
        relative = str(path.relative_to(ROOT))
        if not path.exists():
            failures.append({"file": relative, "reason": "missing"})
            continue

        text = path.read_text(encoding="utf-8")
        evidence["files"][key] = {
            "path": relative,
            "line_count": len(text.splitlines()),
            "bytes": len(text.encode("utf-8")),
        }
        matched = [marker for marker in REQUIRED_MARKERS[key] if marker in text]
        evidence["matched_markers"][key] = matched
        for marker in REQUIRED_MARKERS[key]:
            if marker not in text:
                failures.append({"file": relative, "reason": "missing_marker", "marker": marker})

        for name, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                failures.append({"file": relative, "reason": "forbidden_pattern", "pattern": name})

    result = {
        "ok": not failures,
        "operation": "pixel_office_template_foundation_smoke",
        "contract": "Pixel Office templates are selectable visual skins over MIS state; they do not own runtime, approval, audit, memory, or permission authority.",
        "failures": failures,
        "evidence": evidence,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
