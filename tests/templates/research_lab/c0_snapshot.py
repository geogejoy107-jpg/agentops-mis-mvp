"""Immutable C0 test dependency exported from the reviewed implementation commit."""

from __future__ import annotations

import subprocess
import tarfile
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

C0_IMPLEMENTATION_COMMIT = "aa667fcc012a5eed4a6e823741d8867f750417a1"


@contextmanager
def exported_c0(root: Path) -> Iterator[Path]:
    repository = root.parent / "agentops-mis-template-platform-runtime"
    if not (repository / ".git").exists():
        raise AssertionError("exact C0 platform runtime checkout is required")
    head = subprocess.run(("git", "rev-parse", "HEAD"), cwd=repository, check=True, capture_output=True, text=True).stdout.strip()
    if head != C0_IMPLEMENTATION_COMMIT:
        raise AssertionError(f"C0 HEAD must be {C0_IMPLEMENTATION_COMMIT}, observed {head}")
    index = subprocess.run(("git", "diff", "--cached", "--quiet"), cwd=repository, check=False)
    if index.returncode != 0:
        raise AssertionError("C0 index must be clean")
    with tempfile.TemporaryDirectory(prefix="research-c0-export-") as raw:
        destination = Path(raw)
        archive = destination / "c0.tar"
        subprocess.run(("git", "archive", "--format=tar", f"--output={archive}", C0_IMPLEMENTATION_COMMIT), cwd=repository, check=True)
        export = destination / "source"
        export.mkdir()
        with tarfile.open(archive, "r:") as handle:
            for member in handle.getmembers():
                target = (export / member.name).resolve()
                if export.resolve() not in target.parents and target != export.resolve():
                    raise AssertionError("C0 archive path escapes export root")
            handle.extractall(export)
        yield export
