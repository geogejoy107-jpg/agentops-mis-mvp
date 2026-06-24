#!/usr/bin/env python3
"""Dependency-free validation for the two Spatial Agent art tracks."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "ui" / "start-building-app" / "src" / "assets" / "spatial" / "agents"

ASSETS = {
    "village-research-agent-v0": {
        "png": "village-research-agent-v0.png",
        "json": "village-research-agent-v0.json",
        "size": (192, 192),
        "frame": (32, 48),
        "count": 24,
        "family": "village-life-sim",
        "body": "full-character",
        "sha256": "7c5af2207046c9458afc0e6735986600cbe0ffdb1d033a9372c6143286242cb0",
    },
    "industrial-research-unit-v0": {
        "png": "industrial-research-unit-v0.png",
        "json": "industrial-research-unit-v0.json",
        "size": (256, 96),
        "frame": (32, 32),
        "count": 24,
        "family": "industrial-unit",
        "body": "machine-unit",
        "sha256": "cea70e84fa98526c6f4001a68ff9763168aa39d4cc75490798671352d607d098",
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def png_size(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    require(raw.startswith(b"\x89PNG\r\n\x1a\n"), f"not a PNG: {path}")
    require(raw[12:16] == b"IHDR", f"missing IHDR: {path}")
    return struct.unpack(">II", raw[16:24])


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"metadata must be an object: {path}")
    return value


def main() -> None:
    renderer_bodies: set[str] = set()
    for asset_id, expected in ASSETS.items():
        png_path = ASSET_ROOT / str(expected["png"])
        json_path = ASSET_ROOT / str(expected["json"])
        require(png_path.is_file(), f"missing PNG: {png_path.relative_to(ROOT)}")
        require(json_path.is_file(), f"missing metadata: {json_path.relative_to(ROOT)}")

        metadata = load_json(json_path)
        require(metadata.get("schemaVersion") == "spatial-agent-art/v0", f"schema mismatch: {asset_id}")
        require(metadata.get("id") == asset_id, f"id mismatch: {asset_id}")
        require(metadata.get("license") == "PROJECT_OWNED", f"license mismatch: {asset_id}")
        require(metadata.get("provenance") == "first_party", f"provenance mismatch: {asset_id}")
        require(metadata.get("copiedPixels") is False, f"copiedPixels must be false: {asset_id}")
        require(metadata.get("rendererFamily") == expected["family"], f"renderer family mismatch: {asset_id}")

        identity = metadata.get("identityMapping", {})
        require(identity.get("floatingGlyph") is False, f"floating glyph must be disabled: {asset_id}")
        require(identity.get("statusChannel") == "separate", f"status channel must be separate: {asset_id}")
        require(identity.get("riskChannel") == "separate", f"risk channel must be separate: {asset_id}")
        require(identity.get("bodyRenderer") == expected["body"], f"body renderer mismatch: {asset_id}")
        renderer_bodies.add(str(identity.get("bodyRenderer")))

        width, height = png_size(png_path)
        require((width, height) == expected["size"], f"PNG size mismatch: {asset_id}")
        frame = metadata.get("frame", {})
        frame_size = (frame.get("width"), frame.get("height"))
        require(frame_size == expected["frame"], f"frame size mismatch: {asset_id}")
        require(width % frame_size[0] == 0 and height % frame_size[1] == 0, f"sheet does not divide into frames: {asset_id}")
        require((width // frame_size[0]) * (height // frame_size[1]) == expected["count"], f"frame count mismatch: {asset_id}")

        digest = hashlib.sha256(png_path.read_bytes()).hexdigest()
        require(digest == expected["sha256"], f"PNG hash mismatch: {asset_id}")
        require(metadata.get("sha256") == digest, f"metadata hash mismatch: {asset_id}")

        serialized = json.dumps(metadata, ensure_ascii=False).lower()
        require("http://" not in serialized and "https://" not in serialized, f"remote production URL found: {asset_id}")

    require(renderer_bodies == {"full-character", "machine-unit"}, "the two assets must remain alternative body renderers")
    print("Spatial Agent art smoke passed: assets=2 frames=48 floating_glyph=false bodies=full-character,machine-unit")


if __name__ == "__main__":
    main()
