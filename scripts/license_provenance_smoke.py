#!/usr/bin/env python3
"""Verify local MVP license/provenance evidence and Pixel Office asset boundary."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui" / "start-building-app"
PRODUCT_ASSET_ROOTS = [
    UI_DIR / "src",
    UI_DIR / "public",
]
REQUIRED_DOCS = [
    ROOT / "LICENSE",
    ROOT / "docs" / "THIRD_PARTY_NOTICES.md",
    ROOT / "docs" / "RELEASE_PROVENANCE.md",
    ROOT / "docs" / "SBOM_MINIMAL.md",
    ROOT / "docs" / "PIXEL_OFFICE_REFERENCE_AUDIT.md",
    ROOT / "docs" / "PIXEL_OFFICE_ASSET_REPLACEMENT_PLAN.md",
]
ASSET_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".aseprite",
    ".tmx",
}
FORBIDDEN_PRODUCT_MARKERS = [
    "Star-Office-UI/assets",
    "LimeZu",
    "Donarg",
    "MetroCity",
    "sprite sheet",
    "tile atlas",
]
SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def product_files() -> list[Path]:
    files: list[Path] = []
    for root in PRODUCT_ASSET_ROOTS:
        if root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file())
    return sorted(files)


def main() -> int:
    failures: list[str] = []
    for path in REQUIRED_DOCS:
        require(path.exists(), f"missing required provenance document: {path.relative_to(ROOT)}", failures)

    license_text = read(ROOT / "LICENSE") if (ROOT / "LICENSE").exists() else ""
    pyproject = read(ROOT / "pyproject.toml")
    ui_package = json.loads(read(UI_DIR / "package.json"))
    ui_lock = json.loads(read(UI_DIR / "package-lock.json"))
    notices = read(ROOT / "docs" / "THIRD_PARTY_NOTICES.md") if (ROOT / "docs" / "THIRD_PARTY_NOTICES.md").exists() else ""
    provenance = read(ROOT / "docs" / "RELEASE_PROVENANCE.md") if (ROOT / "docs" / "RELEASE_PROVENANCE.md").exists() else ""
    sbom = read(ROOT / "docs" / "SBOM_MINIMAL.md") if (ROOT / "docs" / "SBOM_MINIMAL.md").exists() else ""
    replacement = read(ROOT / "docs" / "PIXEL_OFFICE_ASSET_REPLACEMENT_PLAN.md")
    reference_audit = read(ROOT / "docs" / "PIXEL_OFFICE_REFERENCE_AUDIT.md")

    require("Proprietary Local MVP" in license_text or "Proprietary local MVP" in license_text, "root LICENSE does not declare local MVP posture", failures)
    require("All rights reserved" in license_text, "root LICENSE missing all-rights-reserved boundary", failures)
    require('license = { text = "Proprietary local MVP" }' in pyproject, "pyproject license metadata is not aligned", failures)
    require(ui_package.get("private") is True, "UI package must remain private", failures)
    require(ui_package.get("license") == "UNLICENSED", "UI package license must be UNLICENSED", failures)
    require((ui_lock.get("packages") or {}).get("", {}).get("license") == "UNLICENSED", "UI lockfile root license must be UNLICENSED", failures)

    required_phrases = [
        "Star-Office-UI",
        "non-commercial",
        "No Star-Office art is copied",
        "Package-manager metadata is authoritative",
    ]
    for phrase in required_phrases:
        require(phrase in notices, f"third-party notices missing phrase: {phrase}", failures)

    for phrase in [
        "VITE_STAR_OFFICE_URL",
        "Commercial Build Exclusion",
        "does not use copied Star-Office-UI art assets",
        "assets/pixel-office/",
    ]:
        require(phrase in provenance, f"release provenance missing phrase: {phrase}", failures)

    direct_deps = sorted((ui_package.get("dependencies") or {}).items())
    direct_dev_deps = sorted((ui_package.get("devDependencies") or {}).items())
    for name, version in direct_deps + direct_dev_deps:
        require(f"| {name} | {version} |" in sbom, f"minimal SBOM missing direct npm package: {name}@{version}", failures)
    require("agentops-mis-cli | 0.1.0" in sbom, "minimal SBOM missing CLI component", failures)
    require("No Pixel Office bitmap/sprite/tile assets" in sbom, "minimal SBOM missing asset boundary", failures)

    require("Public commercial release is blocked until:" in replacement, "asset replacement plan missing commercial release gate", failures)
    require("Do not copy Star-Office art" in reference_audit, "reference audit missing Star-Office copy boundary", failures)

    files = product_files()
    asset_like_paths = [path.relative_to(ROOT).as_posix() for path in files if path.suffix.lower() in ASSET_SUFFIXES]
    require(not asset_like_paths, f"product source must not contain Pixel Office bitmap/sprite/tile assets: {asset_like_paths}", failures)

    product_text_parts: list[str] = []
    for path in files:
        if path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx", ".css", ".md", ".html", ".json"}:
            product_text_parts.append(read(path))
    product_text = "\n".join(product_text_parts)
    forbidden_hits = [marker for marker in FORBIDDEN_PRODUCT_MARKERS if marker in product_text]
    require(not forbidden_hits, f"forbidden commercial-asset marker found in product source: {forbidden_hits}", failures)
    require("VITE_STAR_OFFICE_URL" in product_text, "legacy Star Office link should remain explicit and optional", failures)
    require("Star-Office-UI/assets" not in product_text, "product source references Star-Office asset path", failures)

    evidence_bundle = "\n".join([license_text, notices, provenance, sbom])
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(evidence_bundle)]
    require(not secret_hits, f"secret-like marker found in license/provenance evidence: {secret_hits}", failures)

    output = {
        "ok": not failures,
        "operation": "license_provenance_smoke",
        "documents": [str(path.relative_to(ROOT)) for path in REQUIRED_DOCS],
        "ui_direct_dependencies": len(direct_deps),
        "ui_direct_dev_dependencies": len(direct_dev_deps),
        "pixel_office_product_assets": asset_like_paths,
        "contract": "Local MVP license, third-party notices, minimal SBOM, release provenance, and Pixel Office commercial asset exclusion are present.",
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
