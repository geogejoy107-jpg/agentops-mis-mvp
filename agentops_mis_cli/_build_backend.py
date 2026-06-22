"""Tiny offline PEP 517 build backend for the dependency-free CLI package.

This project intentionally avoids runtime dependencies. The backend lets
`pip install .` build a pure-Python wheel without fetching setuptools/wheel
from the network on customer or demo machines.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import tarfile
import zipfile
from pathlib import Path


PROJECT = "agentops-mis-cli"
DIST = "agentops_mis_cli"
VERSION = "0.1.0"
DIST_INFO = f"{DIST}-{VERSION}.dist-info"
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "agentops_mis_cli"
PACKAGES = [
    ROOT / "agentops_mis_cli",
    ROOT / "agentops_mis_storage",
]


def _metadata() -> str:
    return "\n".join([
        "Metadata-Version: 2.1",
        f"Name: {PROJECT}",
        f"Version: {VERSION}",
        "Summary: Installable AgentOps MIS Agent Gateway CLI wrapper.",
        "Requires-Python: >=3.10",
        "License: Proprietary local MVP",
        "",
    ])


def _wheel() -> str:
    return "\n".join([
        "Wheel-Version: 1.0",
        "Generator: agentops-mis-cli offline backend",
        "Root-Is-Purelib: true",
        "Tag: py3-none-any",
        "",
    ])


def _entry_points() -> str:
    return "\n".join([
        "[console_scripts]",
        "agentops = agentops_mis_cli.cli:main",
        "agentops-worker = agentops_mis_cli.worker:main",
        "",
    ])


def _hash(data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}", str(len(data))


def _package_files() -> list[tuple[str, bytes]]:
    files = []
    for package in PACKAGES:
        for path in sorted(package.glob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            files.append((rel, path.read_bytes()))
    return files


def _wheel_files() -> list[tuple[str, bytes]]:
    return [
        *_package_files(),
        (f"{DIST_INFO}/METADATA", _metadata().encode("utf-8")),
        (f"{DIST_INFO}/WHEEL", _wheel().encode("utf-8")),
        (f"{DIST_INFO}/entry_points.txt", _entry_points().encode("utf-8")),
    ]


def _record(rows: list[tuple[str, bytes]]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    for name, data in rows:
        writer.writerow([name, *_hash(data)])
    writer.writerow([f"{DIST_INFO}/RECORD", "", ""])
    return out.getvalue().encode("utf-8")


def build_wheel(wheel_directory: str, config_settings=None, metadata_directory=None) -> str:
    rows = _wheel_files()
    wheel_name = f"{DIST}-{VERSION}-py3-none-any.whl"
    target = Path(wheel_directory) / wheel_name
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in rows:
            zf.writestr(name, data)
        zf.writestr(f"{DIST_INFO}/RECORD", _record(rows))
    return wheel_name


def prepare_metadata_for_build_wheel(metadata_directory: str, config_settings=None) -> str:
    dist_info = Path(metadata_directory) / DIST_INFO
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(_metadata(), encoding="utf-8")
    (dist_info / "WHEEL").write_text(_wheel(), encoding="utf-8")
    (dist_info / "entry_points.txt").write_text(_entry_points(), encoding="utf-8")
    (dist_info / "RECORD").write_text("", encoding="utf-8")
    return DIST_INFO


def build_sdist(sdist_directory: str, config_settings=None) -> str:
    sdist_name = f"{DIST}-{VERSION}.tar.gz"
    target = Path(sdist_directory) / sdist_name
    prefix = f"{DIST}-{VERSION}"
    include = [
        ROOT / "pyproject.toml",
        *[path for package in PACKAGES for path in sorted(package.glob("*.py"))],
        ROOT / "README.md",
    ]
    with tarfile.open(target, "w:gz") as tf:
        for path in include:
            tf.add(path, arcname=f"{prefix}/{path.relative_to(ROOT).as_posix()}")
    return sdist_name
