#!/usr/bin/env python3
"""Build the two first-party Spatial Agent art tracks deterministically."""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import struct
import zlib
from pathlib import Path

import generate_spatial_agent_art_assets as art

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "ui/start-building-app/src/assets/spatial/agent-art/v0"
DEFAULT_PREVIEW = ROOT / "artifacts/spatial-agent-art/v0"


def png_chunk(kind: bytes, data: bytes) -> bytes:
    crc = binascii.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def write_png(
    path: Path,
    canvas: art.Canvas,
    *,
    compression: int = 9,
    comment: str | None = None,
) -> None:
    raw = bytearray()
    for y in range(canvas.h):
        raw.append(0)
        for x in range(canvas.w):
            raw.extend(canvas.get(x, y))

    payload = b"\x89PNG\r\n\x1a\n"
    payload += png_chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", canvas.w, canvas.h, 8, 6, 0, 0, 0),
    )
    if comment:
        payload += png_chunk(b"tEXt", b"Comment\x00" + comment.encode("latin-1"))
    payload += png_chunk(b"IDAT", zlib.compress(bytes(raw), compression))
    payload += png_chunk(b"IEND", b"")
    path.write_bytes(payload)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(cozy_file: Path, industrial_file: Path) -> dict[str, object]:
    return {
        "schemaVersion": "spatial-agent-art-assets/v0",
        "license": "PROJECT_OWNED",
        "provenance": "first_party",
        "externalProductionAssets": [],
        "tracks": [
            {
                "id": "cozy-research-agent-v0",
                "mode": "full-character",
                "file": cozy_file.name,
                "frame": {"width": 32, "height": 48},
                "columns": 4,
                "rows": 4,
                "directions": ["south", "west", "east", "north"],
                "phases": ["idle", "step-a", "passing", "step-b"],
                "identityEncoding": [
                    "silhouette",
                    "hair",
                    "coat",
                    "scarf",
                    "satchel",
                    "notebook",
                ],
                "detachedBadge": False,
                "misRole": "research-agent",
                "formalRoute": "/workspace/agents",
            },
            {
                "id": "industrial-agent-units-v0",
                "mode": "complete-unit",
                "file": industrial_file.name,
                "frame": {"width": 32, "height": 32},
                "columns": 3,
                "rows": 2,
                "roles": [
                    "research",
                    "coder",
                    "browser",
                    "memory",
                    "approval",
                    "runtime",
                ],
                "roleRoutes": {
                    "research": "/workspace/agents",
                    "coder": "/workspace/agents",
                    "browser": "/admin/toolcalls",
                    "memory": "/workspace/memory",
                    "approval": "/workspace/approvals",
                    "runtime": "/admin/connectors",
                },
                "identityEncoding": [
                    "chassis",
                    "core",
                    "tool-module",
                    "accent-ramp",
                ],
                "humanBody": False,
                "detachedBadge": False,
            },
        ],
        "sha256": {
            cozy_file.name: digest(cozy_file),
            industrial_file.name: digest(industrial_file),
        },
        "references": [
            {
                "repository": "BenCreating/LPC-Spritesheet-Generator",
                "licenseReviewed": "MIT code; art licenses vary per item",
                "adoption": "animation, layer, palette, compatibility and provenance method only",
                "assetsCopied": False,
            },
            {
                "repository": "Anuken/Mindustry",
                "licenseReviewed": "GPL-3.0",
                "adoption": "modular chassis/core/effect regions, outline generation, palette slots and generated UI icon method only",
                "assetsCopied": False,
            },
        ],
    }


def build(output_dir: Path, preview_dir: Path | None = None) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cozy = art.make_cozy_sheet()
    industrial = art.make_industrial_sheet()

    cozy_file = output_dir / "cozy-research-agent-v0.png"
    industrial_file = output_dir / "industrial-agent-units-v0.png"
    write_png(cozy_file, cozy)
    write_png(
        industrial_file,
        industrial,
        compression=1,
        comment="AgentOps MIS first-party industrial Agent atlas v0",
    )

    result = manifest(cozy_file, industrial_file)
    (output_dir / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if preview_dir is not None:
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview = art.make_preview(cozy, industrial)
        write_png(preview_dir / "dual-agent-art-assets-v0-preview.png", preview)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--preview-dir", type=Path, default=DEFAULT_PREVIEW)
    args = parser.parse_args()
    result = build(args.output_dir, args.preview_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
