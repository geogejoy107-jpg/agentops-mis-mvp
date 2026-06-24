#!/usr/bin/env python3
"""Dependency-free validation for the two Spatial Agent art tracks."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import tempfile
import zlib
from pathlib import Path

import build_spatial_agent_art_assets as builder

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "ui/start-building-app/src/assets/spatial/agent-art/v0"
APP_PATH = ROOT / "ui/start-building-app/src/app/App.tsx"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode_png(path: Path) -> tuple[int, int, list[bytes]]:
    data = path.read_bytes()
    require(data.startswith(PNG_SIGNATURE), f"invalid PNG signature: {path.name}")
    offset = len(PNG_SIGNATURE)
    width = height = 0
    idat = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", payload)
            require(depth == 8 and color_type == 6 and interlace == 0, f"unsupported PNG format: {path.name}")
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    require(width > 0 and height > 0, f"missing IHDR: {path.name}")
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    require(len(raw) == height * (stride + 1), f"unexpected pixel payload: {path.name}")
    rows: list[bytes] = []
    for y in range(height):
        start = y * (stride + 1)
        require(raw[start] == 0, f"only filter 0 is accepted: {path.name} row {y}")
        rows.append(raw[start + 1 : start + 1 + stride])
    return width, height, rows


def alpha_mask(rows: list[bytes], x0: int, y0: int, width: int, height: int) -> bytes:
    mask = bytearray()
    for y in range(y0, y0 + height):
        row = rows[y]
        for x in range(x0, x0 + width):
            mask.append(1 if row[x * 4 + 3] else 0)
    return bytes(mask)


def validate_manifest(manifest: dict[str, object]) -> None:
    require(manifest.get("schemaVersion") == "spatial-agent-art-assets/v0", "schema mismatch")
    require(manifest.get("license") == "PROJECT_OWNED", "asset license must be project-owned")
    require(manifest.get("provenance") == "first_party", "asset provenance must be first-party")
    require(manifest.get("externalProductionAssets") == [], "external production assets are forbidden")

    tracks = manifest.get("tracks")
    require(isinstance(tracks, list) and len(tracks) == 2, "exactly two art tracks are required")
    by_id = {track.get("id"): track for track in tracks if isinstance(track, dict)}
    cozy = by_id.get("cozy-research-agent-v0")
    industrial = by_id.get("industrial-agent-units-v0")
    require(isinstance(cozy, dict), "cozy track missing")
    require(isinstance(industrial, dict), "industrial track missing")
    require(cozy.get("mode") == "full-character", "cozy Agent must be the complete character")
    require(cozy.get("detachedBadge") is False, "cozy Agent may not carry a detached identity badge")
    require(industrial.get("mode") == "complete-unit", "industrial glyph must be the complete Agent")
    require(industrial.get("humanBody") is False, "industrial Agent may not wrap a human body")
    require(industrial.get("detachedBadge") is False, "industrial Agent may not be a detached badge")

    app_source = APP_PATH.read_text(encoding="utf-8")
    registered_routes = set(re.findall(r'<Route\s+path="([^"]+)"', app_source))
    formal_route = cozy.get("formalRoute")
    require(formal_route in registered_routes, f"unregistered cozy route: {formal_route}")
    role_routes = industrial.get("roleRoutes")
    require(isinstance(role_routes, dict), "industrial role routes missing")
    for role, route in role_routes.items():
        require(route in registered_routes, f"unregistered route for {role}: {route}")

    for ref in manifest.get("references", []):
        require(isinstance(ref, dict) and ref.get("assetsCopied") is False, "reference assets must not be copied")


def validate_pixels() -> None:
    cozy_path = ASSET_DIR / "cozy-research-agent-v0.png"
    industrial_path = ASSET_DIR / "industrial-agent-units-v0.png"
    cozy_w, cozy_h, cozy_rows = decode_png(cozy_path)
    industrial_w, industrial_h, industrial_rows = decode_png(industrial_path)
    require((cozy_w, cozy_h) == (128, 192), "cozy sheet must be 4x4 frames of 32x48")
    require((industrial_w, industrial_h) == (96, 64), "industrial atlas must be 3x2 frames of 32x32")

    cozy_frames: list[bytes] = []
    for row in range(4):
        for column in range(4):
            frame = alpha_mask(cozy_rows, column * 32, row * 48, 32, 48)
            require(any(frame), f"empty cozy frame at {column},{row}")
            cozy_frames.append(frame)
            # Upper-right badge zone must remain empty; identity lives in the character itself.
            for y in range(row * 48, row * 48 + 16):
                pixels = cozy_rows[y]
                for x in range(column * 32 + 26, column * 32 + 32):
                    require(pixels[x * 4 + 3] == 0, f"detached cozy badge pixel at frame {column},{row}")
    require(len(set(cozy_frames)) >= 8, "cozy direction/step silhouettes are insufficiently varied")

    unit_masks = [
        alpha_mask(industrial_rows, (index % 3) * 32, (index // 3) * 32, 32, 32)
        for index in range(6)
    ]
    require(all(any(mask) for mask in unit_masks), "industrial unit frame is empty")
    require(len(set(unit_masks)) == 6, "industrial Agent silhouettes must all be unique")


def validate_reproducibility(committed_manifest: dict[str, object]) -> None:
    with tempfile.TemporaryDirectory(prefix="agent-art-a-") as first, tempfile.TemporaryDirectory(prefix="agent-art-b-") as second:
        first_dir = Path(first)
        second_dir = Path(second)
        first_manifest = builder.build(first_dir, None)
        second_manifest = builder.build(second_dir, None)
        require(first_manifest == second_manifest, "builder manifests are not deterministic")
        require(first_manifest == committed_manifest, "generated manifest differs from committed manifest")
        for filename in ("cozy-research-agent-v0.png", "industrial-agent-units-v0.png"):
            require(sha256(first_dir / filename) == sha256(second_dir / filename), f"non-deterministic asset: {filename}")
            require(sha256(first_dir / filename) == sha256(ASSET_DIR / filename), f"committed asset drift: {filename}")


def main() -> None:
    manifest_path = ASSET_DIR / "manifest.json"
    require(manifest_path.is_file(), "asset manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    validate_pixels()
    validate_reproducibility(manifest)
    print(
        "Spatial Agent art assets smoke passed: "
        "tracks=2 cozy_frames=16 industrial_units=6 provenance=first_party detached_badges=0"
    )


if __name__ == "__main__":
    main()
