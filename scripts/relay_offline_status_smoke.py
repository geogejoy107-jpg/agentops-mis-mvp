#!/usr/bin/env python3
"""Exercise Relayctl status against disposable roots without changing the repo."""
from __future__ import annotations

import base64
import builtins
import csv
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from types import ModuleType


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "agentops_mis_cli" / "relay_admin.py"
BACKEND = ROOT / "agentops_mis_cli" / "_build_backend.py"
STATUS_SCHEMA = "agentops.relay.offline-status.v0"
UNIT_NAME = "agentops-mis-relay.service"
LAUNCHER_NAME = "agentops-relay"
CANARY = b"RELAY_STATUS_PROTECTED_CANARY_DO_NOT_TOUCH"
PATH_CANARY = "relay-status-path-canary"
CONFIG_CANARY = b"relay.invalid status config canary"
ENV_CANARY = "RELAY_STATUS_ENV_CREDENTIAL_CANARY_DO_NOT_PRINT"
SECRET_PATTERNS = (
    ("nt" + "n_RELAY_STATUS_SECRET_CANARY").encode("ascii"),
    ("sk" + "-relay-status-secret-canary").encode("ascii"),
    ("gh" + "p_relay_status_secret_canary").encode("ascii"),
)

ABSENT_KEYS = {
    "installed",
    "ok",
    "operation_id",
    "recovery_required",
    "schema_id",
    "state_id",
}
INVALID_KEYS = {"installed", "ok", "operation_id", "schema_id", "state_id"}
RECOVERY_KEYS = {
    "installed",
    "ok",
    "operation_id",
    "recovery_marker_count",
    "recovery_required",
    "schema_id",
    "state_id",
}
VALID_KEYS = {
    "installed",
    "ok",
    "operation_id",
    "provenance_archive_sha256",
    "provenance_git_commit",
    "provenance_manifest_sha256",
    "provenance_only",
    "provenance_wheel_sha256",
    "record_integrity_valid",
    "relationships_valid",
    "release_directory_count",
    "release_file_count",
    "release_id",
    "schema_id",
    "site_package_file_count",
    "state_id",
    "version_id",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_backend() -> ModuleType:
    return load_module(BACKEND, "_relay_status_smoke_backend")


def snapshot(path: Path) -> tuple[int, bytes, int, int, int, int]:
    metadata = path.stat()
    return (
        metadata.st_ino,
        path.read_bytes(),
        metadata.st_mtime_ns,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_gid,
    )


def tree_digest(root: Path) -> str:
    records: list[bytes] = []
    paths = [root] if root.is_symlink() else [root, *root.rglob("*")]
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            value = os.readlink(path).encode("utf-8")
            kind = b"L"
        elif stat.S_ISDIR(metadata.st_mode):
            value = b""
            kind = b"D"
        elif stat.S_ISREG(metadata.st_mode):
            value = path.read_bytes()
            kind = b"F"
        else:
            value = b""
            kind = b"X"
        identity = (
            f"{metadata.st_dev}:{metadata.st_ino}:{metadata.st_nlink}:"
            f"{metadata.st_size}:{metadata.st_mtime_ns}:"
            f"{stat.S_IMODE(metadata.st_mode)}:{metadata.st_uid}:{metadata.st_gid}"
        ).encode("ascii")
        records.append(kind + b"\0" + relative + b"\0" + identity + b"\0" + value)
    return sha256(b"\n".join(records))


def add_tar_directory(archive: tarfile.TarFile, name: str) -> None:
    info = tarfile.TarInfo(name)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.mode = 0o755
    info.type = tarfile.DIRTYPE
    archive.addfile(info)


def add_tar_file(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.mode = 0o644
    info.type = tarfile.REGTYPE
    info.size = len(data)
    archive.addfile(info, io.BytesIO(data))


def build_formal_bundle(destination: Path) -> tuple[Path, str, bytes, str]:
    backend = load_backend()
    wheel_dir = destination / "wheel-build"
    wheel_dir.mkdir()
    wheel_name = backend.build_wheel(str(wheel_dir))
    wheel_data = (wheel_dir / wheel_name).read_bytes()
    version = str(backend.VERSION)
    commit = git_output("rev-parse", "HEAD")
    if len(commit) != 40:
        raise RuntimeError("HEAD is not a full commit")
    payload = {
        "config/config.example.json": (
            ROOT / "packaging" / "relay" / "config.example.json"
        ).read_bytes(),
        "systemd/agentops-mis-relay.service": (
            ROOT / "packaging" / "relay" / "systemd" / UNIT_NAME
        ).read_bytes(),
        f"wheel/{wheel_name}": wheel_data,
    }
    manifest = {
        "files": [
            {"path": path, "sha256": sha256(data), "size": len(data)}
            for path, data in sorted(payload.items())
        ],
        "git_commit": commit,
        "schema": "agentops.relay.release-bundle.v1",
        "version": version,
    }
    manifest_data = canonical_json(manifest)
    checksums = "".join(
        f"{sha256(data)}  {path}\n"
        for path, data in sorted({**payload, "manifest.json": manifest_data}.items())
    ).encode("ascii")
    root_name = f"agentops-mis-relay-{version}"
    archive_data = io.BytesIO()
    with tarfile.open(fileobj=archive_data, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        add_tar_directory(archive, root_name)
        for directory in ("config", "systemd", "wheel"):
            add_tar_directory(archive, f"{root_name}/{directory}")
        for path, data in sorted(
            {**payload, "manifest.json": manifest_data, "SHA256SUMS": checksums}.items()
        ):
            add_tar_file(archive, f"{root_name}/{path}", data)
    compressed = io.BytesIO()
    import gzip

    with gzip.GzipFile(
        filename="", fileobj=compressed, mode="wb", compresslevel=9, mtime=0
    ) as output:
        output.write(archive_data.getvalue())
    bundle = destination / f"{root_name}.tar.gz"
    bundle.write_bytes(compressed.getvalue())
    bundle.chmod(0o600)
    return bundle, sha256(compressed.getvalue()), wheel_data, wheel_name


def write_guard(path: Path) -> None:
    path.mkdir()
    (path / "sitecustomize.py").write_text(
        """
import os
import socket
import subprocess
import builtins
import io
import pathlib

def _blocked(*args, **kwargs):
    raise RuntimeError("relay status attempted forbidden external behavior")

socket.create_connection = _blocked
socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
subprocess.Popen = _blocked
subprocess.run = _blocked
os.system = _blocked
os.popen = _blocked
_real_os_open = os.open
_write_flags = (
    os.O_WRONLY
    | os.O_RDWR
    | os.O_CREAT
    | os.O_TRUNC
    | os.O_APPEND
    | os.O_EXCL
    | getattr(os, "O_TMPFILE", 0)
)
def _guarded_open(*args, **kwargs):
    _flags = args[1] if len(args) > 1 else kwargs.get("flags", 0)
    if _flags & _write_flags:
        raise RuntimeError("relay status attempted write-capable os.open")
    return _real_os_open(*args, **kwargs)

os.open = _guarded_open
os.write = _blocked
if hasattr(os, "pwrite"):
    os.pwrite = _blocked
if hasattr(os, "truncate"):
    os.truncate = _blocked
for _name in ("chmod", "chown", "fchmod", "fchown", "link", "mkdir", "makedirs", "remove", "rename", "replace", "rmdir", "symlink", "unlink"):
    if hasattr(os, _name):
        setattr(os, _name, _blocked)

_real_builtin_open = builtins.open
def _guarded_file_open(file, mode="r", *args, **kwargs):
    if any(_flag in mode for _flag in ("w", "a", "x", "+")):
        raise RuntimeError("relay status attempted writable builtins.open")
    return _real_builtin_open(file, mode, *args, **kwargs)

builtins.open = _guarded_file_open
_real_io_open = io.open
def _guarded_io_open(file, mode="r", *args, **kwargs):
    if any(_flag in mode for _flag in ("w", "a", "x", "+")):
        raise RuntimeError("relay status attempted writable io.open")
    return _real_io_open(file, mode, *args, **kwargs)

io.open = _guarded_io_open
for _name in ("chmod", "lchmod", "mkdir", "open", "rename", "replace", "rmdir", "symlink_to", "touch", "unlink", "write_bytes", "write_text"):
    if hasattr(pathlib.Path, _name):
        setattr(pathlib.Path, _name, _blocked)
""".lstrip(),
        encoding="ascii",
    )


def base_env(temporary: Path) -> dict[str, str]:
    home = temporary / "home"
    temp_dir = temporary / "tmp"
    cache = temporary / "cache"
    for path in (home, temp_dir, cache):
        path.mkdir()
    return {
        "HOME": str(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PIP_NO_INDEX": "1",
        "TMPDIR": str(temp_dir),
        "XDG_CACHE_HOME": str(cache),
        "RELAY_STATUS_ENV_CANARY": ENV_CANARY,
    }


def status_env(environment: dict[str, str], guard: Path, *extra: Path) -> dict[str, str]:
    result = dict(environment)
    result["PYTHONPATH"] = os.pathsep.join(str(path) for path in (guard, *extra))
    return result


def run_status(
    command: list[str],
    root: Path,
    environment: dict[str, str],
    failures: list[str],
    label: str,
) -> tuple[int, dict[str, object], bytes]:
    before_digest = tree_digest(root)
    result = subprocess.run(
        [*command, "--root", str(root.absolute()), "status"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        timeout=30,
    )
    combined = result.stdout + result.stderr
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    require(isinstance(payload, dict), f"{label}: status JSON missing", failures)
    require(result.stderr == b"", f"{label}: status wrote diagnostics to stderr", failures)
    require(payload.get("schema_id") == STATUS_SCHEMA, f"{label}: schema missing", failures)
    require(payload.get("operation_id") == "status", f"{label}: operation mismatch", failures)
    require(
        PATH_CANARY.encode("ascii") not in combined
        and b"config.example.json" not in combined
        and CONFIG_CANARY not in combined
        and ENV_CANARY.encode("ascii") not in combined
        and b"Traceback" not in combined
        and b"Exception" not in combined
        and not any(pattern in combined for pattern in SECRET_PATTERNS),
        f"{label}: status output leaked path/config/credential/exception data",
        failures,
    )
    require(
        tree_digest(root) == before_digest,
        f"{label}: status changed the tested root",
        failures,
    )
    return result.returncode, payload, combined


def assert_status(
    code: int,
    payload: dict[str, object],
    *,
    expected_code: int,
    expected_state: str,
    expected_keys: set[str],
    failures: list[str],
    label: str,
) -> None:
    require(code == expected_code, f"{label}: exit code {code}", failures)
    require(payload.get("state_id") == expected_state, f"{label}: state mismatch", failures)
    require(set(payload) == expected_keys, f"{label}: JSON shape mismatch", failures)
    require(payload.get("ok") is (expected_code == 0), f"{label}: ok mismatch", failures)


def create_protected_state(root: Path) -> tuple[Path, Path, tuple, tuple]:
    config = root / "etc" / "agentops-mis-relay" / "config.json"
    epoch = root / "var" / "lib" / "agentops-mis-relay" / "epochs.json"
    config.parent.mkdir(parents=True, mode=0o700)
    epoch.parent.mkdir(parents=True, mode=0o700)
    config.write_bytes(CONFIG_CANARY + b"\n" + CANARY)
    epoch.write_bytes(CANARY + b"\n" + SECRET_PATTERNS[0])
    config.chmod(0o600)
    epoch.chmod(0o600)
    old_ns = 1_600_000_000_123_456_789
    os.utime(config, ns=(old_ns, old_ns))
    os.utime(epoch, ns=(old_ns + 1, old_ns + 1))
    return config, epoch, snapshot(config), snapshot(epoch)


def install_confirmed(
    python: str,
    root: Path,
    bundle: Path,
    bundle_sha: str,
    environment: dict[str, str],
    failures: list[str],
) -> dict[str, object]:
    command = [python, str(ADMIN)]
    preview = subprocess.run(
        [
            *command,
            "--root",
            str(root.absolute()),
            "install",
            "--bundle",
            str(bundle.absolute()),
            "--expect-sha256",
            bundle_sha,
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        timeout=60,
    )
    require(preview.returncode == 0, "install preview failed", failures)
    try:
        preview_payload = json.loads(preview.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        preview_payload = {}
    plan = preview_payload.get("plan_sha256")
    require(isinstance(plan, str) and len(plan) == 64, "install plan missing", failures)
    confirmed = subprocess.run(
        [
            *command,
            "--root",
            str(root.absolute()),
            "install",
            "--bundle",
            str(bundle.absolute()),
            "--expect-sha256",
            bundle_sha,
            "--confirm-install",
            "--plan-sha256",
            str(plan),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        timeout=60,
    )
    require(confirmed.returncode == 0, "confirmed install failed", failures)
    try:
        return json.loads(confirmed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def release_paths(root: Path) -> tuple[Path, Path, Path, Path]:
    base = root / "opt" / "agentops-mis-relay"
    release = next((base / "releases").iterdir())
    site = release / "private" / "site-packages"
    dist_info = next(site.glob("*.dist-info"))
    return release, site, dist_info, base


def copy_root(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination, symlinks=True)
    return destination


def mutate_release_json(root: Path, mutation: str) -> None:
    release, _site, _dist, _base = release_paths(root)
    path = release / "release.json"
    if mutation == "canonicality":
        path.write_bytes(path.read_bytes() + b" ")
        return
    metadata = json.loads(path.read_bytes())
    if mutation == "identifier":
        metadata["release_id"] = "wrong-release-id"
    elif mutation == "count":
        metadata["installed_file_count"] += 1
    else:
        raise ValueError(mutation)
    path.write_bytes(canonical_json(metadata))


def mutate_record(root: Path, mutation: str) -> None:
    _release, _site, dist_info, _base = release_paths(root)
    path = dist_info / "RECORD"
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
    if mutation == "missing":
        path.unlink()
        return
    if mutation == "extra":
        rows.append(["agentops_mis_cli/status-extra.py", "sha256=bad", "1"])
    else:
        index = next(index for index, row in enumerate(rows) if row[0] != f"{dist_info.name}/RECORD")
        if mutation == "digest":
            rows[index][1] = "sha256=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        elif mutation == "size":
            rows[index][2] = str(int(rows[index][2]) + 1)
        else:
            raise ValueError(mutation)
    output = io.StringIO()
    csv.writer(output, lineterminator="\n").writerows(rows)
    path.write_text(output.getvalue(), encoding="utf-8")


def mutate_symlink(path: Path, target: str) -> None:
    path.unlink()
    path.symlink_to(target)


def build_wheel_entrypoint(
    python: str,
    wheel_data: bytes,
    wheel_name: str,
    temporary: Path,
    environment: dict[str, str],
    failures: list[str],
) -> tuple[Path | None, Path | None]:
    wheel = temporary / wheel_name
    wheel.write_bytes(wheel_data)
    target = temporary / "wheel-prefix"
    probe = subprocess.run(
        [python, "-c", "import pip._internal.commands.install"],
        env=environment,
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if probe.returncode != 0:
        return None, None
    result = subprocess.run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--no-compile",
            "--prefix",
            str(target),
            str(wheel),
        ],
        env=environment,
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=60,
    )
    require(result.returncode == 0, "wheel installation for entrypoint failed", failures)
    entrypoints = [
        path
        for path in target.rglob("agentops-relayctl")
        if path.is_file() and path.parent.name in {"bin", "Scripts"}
    ]
    entrypoint = entrypoints[0] if len(entrypoints) == 1 else None
    site_packages = [
        path
        for path in target.rglob("site-packages")
        if path.is_dir()
    ]
    import_root = site_packages[0] if len(site_packages) == 1 else None
    require(
        entrypoint is not None and entrypoint.is_file(),
        "generated agentops-relayctl entrypoint missing",
        failures,
    )
    require(import_root is not None, "installed wheel site-packages missing", failures)
    return entrypoint, import_root


def main() -> int:
    failures: list[str] = []
    status_before = git_output("status", "--porcelain=v1", "--untracked-files=all")
    with tempfile.TemporaryDirectory(prefix=f"{PATH_CANARY}-") as temporary_name:
        temporary = Path(temporary_name).resolve()
        guard = temporary / "guard"
        write_guard(guard)
        environment = base_env(temporary)
        status_environment = status_env(environment, guard)
        bundle, bundle_sha, wheel_data, wheel_name = build_formal_bundle(temporary)

        empty = temporary / "empty"
        empty.mkdir(mode=0o700)
        for label, runner in (("source", [sys.executable, str(ADMIN)]),):
            code, payload, _ = run_status(runner, empty, status_environment, failures, f"empty:{label}")
            assert_status(
                code,
                payload,
                expected_code=0,
                expected_state="absent",
                expected_keys=ABSENT_KEYS,
                failures=failures,
                label=f"empty:{label}",
            )

        scaffolding = temporary / "scaffolding"
        scaffolding.mkdir(mode=0o700)
        (scaffolding / "opt" / "agentops-mis-relay" / "releases").mkdir(
            parents=True, mode=0o755
        )
        admin_state = scaffolding / "var" / "lib" / "agentops-relayctl"
        admin_state.mkdir(parents=True, mode=0o700)
        lifecycle = admin_state / "lifecycle.lock"
        lifecycle.touch(mode=0o600)
        code, payload, _ = run_status(
            [sys.executable, str(ADMIN)],
            scaffolding,
            status_environment,
            failures,
            "scaffolding:source",
        )
        assert_status(
            code,
            payload,
            expected_code=0,
            expected_state="absent",
            expected_keys=ABSENT_KEYS,
            failures=failures,
            label="scaffolding:source",
        )

        valid = temporary / "valid"
        valid.mkdir(mode=0o700)
        protected_config, protected_epoch, config_before, epoch_before = create_protected_state(valid)
        installed = install_confirmed(
            sys.executable, valid, bundle, bundle_sha, environment, failures
        )
        require(installed.get("installed") is True, "formal confirmed install missing", failures)

        entrypoint, wheel_target = build_wheel_entrypoint(
            sys.executable, wheel_data, wheel_name, temporary, environment, failures
        )
        runners = [("source", [sys.executable, str(ADMIN)], status_environment)]
        if entrypoint is not None and wheel_target is not None:
            runners.append(
                (
                    "installed-wheel",
                    [str(entrypoint)],
                    status_env(environment, guard, wheel_target),
                )
            )

        for label, runner, runner_env in runners:
            code, payload, _ = run_status(runner, valid, runner_env, failures, f"valid:{label}")
            assert_status(
                code,
                payload,
                expected_code=0,
                expected_state="installed_valid",
                expected_keys=VALID_KEYS,
                failures=failures,
                label=f"valid:{label}",
            )
            require(payload.get("installed") is True, f"valid:{label}: installed false", failures)
            require(
                payload.get("provenance_only") is True
                and payload.get("record_integrity_valid") is True
                and payload.get("relationships_valid") is True,
                f"valid:{label}: truth flags missing",
                failures,
            )

        require(snapshot(protected_config) == config_before, "config canary changed", failures)
        require(snapshot(protected_epoch) == epoch_before, "epoch canary changed", failures)

        recovery_cases: list[tuple[str, callable]] = []

        def transaction(root: Path) -> None:
            path = root / "var" / "lib" / "agentops-relayctl" / "transaction.json"
            path.write_text('{"state_id":"prepared"}\n', encoding="ascii")
            path.chmod(0o600)

        def transaction_temp(root: Path) -> None:
            path = root / "var" / "lib" / "agentops-relayctl" / ".transaction-status.tmp"
            path.write_text("prepared\n", encoding="ascii")
            path.chmod(0o600)

        def release_staging(root: Path) -> None:
            release, _site, _dist, base = release_paths(root)
            del release
            stage = base / "releases" / ".installing-status"
            stage.mkdir(mode=0o755)

        def unit_temp(root: Path) -> None:
            path = root / "etc" / "systemd" / "system" / f".{UNIT_NAME}.status.tmp"
            path.write_text("prepared\n", encoding="ascii")
            path.chmod(0o600)

        recovery_cases.extend(
            [
                ("transaction", transaction),
                ("transaction-temp", transaction_temp),
                ("release-staging", release_staging),
                ("unit-temp", unit_temp),
            ]
        )
        for case_name, mutate in recovery_cases:
            case_root = copy_root(valid, temporary / f"recovery-{case_name}")
            mutate(case_root)
            for label, runner, runner_env in runners:
                code, payload, _ = run_status(
                    runner,
                    case_root,
                    runner_env,
                    failures,
                    f"recovery-{case_name}:{label}",
                )
                assert_status(
                    code,
                    payload,
                    expected_code=1,
                    expected_state="recovery_required",
                    expected_keys=RECOVERY_KEYS,
                    failures=failures,
                    label=f"recovery-{case_name}:{label}",
                )

        invalid_cases: list[tuple[str, callable]] = []

        invalid_cases.append(("missing-release-json", lambda root: (release_paths(root)[0] / "release.json").unlink()))
        invalid_cases.append(("extra-release-file", lambda root: (release_paths(root)[0] / "extra-status-file.py").write_bytes(b"extra")))
        invalid_cases.append(("tampered-release-file", lambda root: (release_paths(root)[1] / "agentops_mis_cli" / "relay_admin.py").write_bytes(b"tampered")))
        invalid_cases.extend(
            [
                (f"release-json-{mutation}", lambda root, mutation=mutation: mutate_release_json(root, mutation))
                for mutation in ("identifier", "count", "canonicality")
            ]
        )

        def wrong_current(root: Path) -> None:
            release, _site, _dist, base = release_paths(root)
            del release
            mutate_symlink(base / "current", "releases/wrong-release")

        def wrong_controller(root: Path) -> None:
            release, _site, _dist, base = release_paths(root)
            del release
            mutate_symlink(base / "controller", "releases/wrong-release")

        def wrong_stable(root: Path) -> None:
            mutate_symlink(root / "usr" / "local" / "bin" / LAUNCHER_NAME, "wrong-target")

        def wrong_unit(root: Path) -> None:
            path = root / "etc" / "systemd" / "system" / UNIT_NAME
            path.write_bytes(b"tampered unit\n")

        invalid_cases.extend(
            [
                ("current-mismatch", wrong_current),
                ("controller-mismatch", wrong_controller),
                ("stable-launcher-mismatch", wrong_stable),
                ("unit-mismatch", wrong_unit),
            ]
        )

        def symlink_module(root: Path) -> None:
            _release, site, _dist, _base = release_paths(root)
            mutate_symlink(
                site / "agentops_mis_cli" / "relay_admin.py",
                "cli.py",
            )

        def native_module(root: Path) -> None:
            _release, site, _dist, _base = release_paths(root)
            path = site / "agentops_mis_cli" / "native_extension.so"
            path.write_bytes(b"native")
            path.chmod(0o644)

        def wrong_mode(root: Path) -> None:
            release, _site, _dist, _base = release_paths(root)
            (release / "release.json").chmod(0o600)

        invalid_cases.extend(
            [("symlink-module", symlink_module), ("native-module", native_module), ("wrong-mode", wrong_mode)]
        )
        if os.geteuid() == 0:
            def wrong_owner(root: Path) -> None:
                _release, site, _dist, _base = release_paths(root)
                os.chown(site / "agentops_mis_cli" / "relay_admin.py", 65534, 65534)

            invalid_cases.append(("wrong-owner", wrong_owner))

        invalid_cases.extend(
            [
                (f"record-{mutation}", lambda root, mutation=mutation: mutate_record(root, mutation))
                for mutation in ("missing", "extra", "digest", "size")
            ]
        )

        def unsafe_parent(root: Path) -> None:
            outside = root.parent / f"{PATH_CANARY}-outside"
            outside.mkdir(mode=0o700)
            opt = root / "opt"
            shutil.rmtree(opt)
            opt.symlink_to(outside, target_is_directory=True)

        invalid_cases.append(("unsafe-parent", unsafe_parent))

        def writable_parent(root: Path) -> None:
            (root / "opt").chmod(0o777)

        invalid_cases.append(("writable-parent", writable_parent))

        for case_name, mutate in invalid_cases:
            case_root = copy_root(valid, temporary / f"invalid-{case_name}")
            mutate(case_root)
            for label, runner, runner_env in runners:
                code, payload, _ = run_status(
                    runner,
                    case_root,
                    runner_env,
                    failures,
                    f"invalid-{case_name}:{label}",
                )
                assert_status(
                    code,
                    payload,
                    expected_code=1,
                    expected_state="invalid",
                    expected_keys=INVALID_KEYS,
                    failures=failures,
                    label=f"invalid-{case_name}:{label}",
                )

        root_link = temporary / f"{PATH_CANARY}-symlink-root"
        root_link.symlink_to(valid, target_is_directory=True)
        for label, runner, runner_env in runners:
            code, payload, _ = run_status(
                runner,
                root_link,
                runner_env,
                failures,
                f"root-symlink:{label}",
            )
            assert_status(
                code,
                payload,
                expected_code=1,
                expected_state="invalid",
                expected_keys=INVALID_KEYS,
                failures=failures,
                label=f"root-symlink:{label}",
            )

        swap_root = copy_root(valid, temporary / f"{PATH_CANARY}-swap-root")
        retired_root = temporary / f"{PATH_CANARY}-retired-root"
        before_digest = tree_digest(swap_root)
        status_module = load_module(ADMIN, "_relay_status_smoke_admin")
        original_scan = status_module._status_scan_anchored
        swapped = False

        def swap_after_scan(root_descriptor: int):
            nonlocal swapped
            result = original_scan(root_descriptor)
            swap_root.rename(retired_root)
            swap_root.mkdir(mode=0o700)
            swapped = True
            return result

        status_module._status_scan_anchored = swap_after_scan
        try:
            swap_payload, swap_code = status_module.relay_status(swap_root)
        finally:
            status_module._status_scan_anchored = original_scan
        require(swapped, "root-swap injection did not run", failures)
        require(swap_code == 1, "root-swap status did not fail", failures)
        require(set(swap_payload) == INVALID_KEYS, "root-swap JSON shape mismatch", failures)
        require(swap_payload.get("schema_id") == STATUS_SCHEMA, "root-swap schema missing", failures)
        require(tree_digest(retired_root) == before_digest, "root-swap retired root changed", failures)
        require(not any(swap_root.iterdir()), "root-swap replacement received writes", failures)

        symlink_race_root = copy_root(
            valid,
            temporary / f"{PATH_CANARY}-symlink-race-root",
        )
        symlink_race_module = load_module(
            ADMIN,
            "_relay_status_smoke_symlink_race_admin",
        )
        original_readlink = symlink_race_module.os.readlink
        current_link = (
            symlink_race_root / "opt" / "agentops-mis-relay" / "current"
        )
        symlink_raced = False
        symlink_race_digest = ""

        def replace_during_readlink(path, *, dir_fd=None):
            nonlocal symlink_raced, symlink_race_digest
            if not symlink_raced and path == "current" and dir_fd is not None:
                expected_target = original_readlink(path, dir_fd=dir_fd)
                current_link.unlink()
                current_link.symlink_to(expected_target)
                symlink_raced = True
                symlink_race_digest = tree_digest(symlink_race_root)
            return original_readlink(path, dir_fd=dir_fd)

        symlink_race_module.os.readlink = replace_during_readlink
        try:
            symlink_race_payload, symlink_race_code = (
                symlink_race_module.relay_status(symlink_race_root)
            )
        finally:
            symlink_race_module.os.readlink = original_readlink
        require(
            symlink_raced,
            "symlink-race injection did not run",
            failures,
        )
        require(
            symlink_race_code == 1,
            "symlink-race status did not fail",
            failures,
        )
        require(
            set(symlink_race_payload) == INVALID_KEYS
            and symlink_race_payload.get("state_id") == "invalid",
            "symlink-race JSON shape mismatch",
            failures,
        )
        require(
            tree_digest(symlink_race_root) == symlink_race_digest,
            "symlink-race root changed after injected replacement",
            failures,
        )

        exception_module = load_module(ADMIN, "_relay_status_smoke_exception_admin")
        original_exception_scan = exception_module._status_scan_anchored

        def unexpected_exception(_root_descriptor: int):
            raise RuntimeError(f"{PATH_CANARY}:{CANARY.decode('ascii')}")

        exception_module._status_scan_anchored = unexpected_exception
        try:
            try:
                exception_result, exception_code = exception_module.relay_status(valid)
            except Exception:
                failures.append("unexpected internal exception escaped status boundary")
            else:
                require(exception_code == 1, "unexpected exception did not fail closed", failures)
                require(
                    set(exception_result) == INVALID_KEYS
                    and exception_result.get("state_id") == "invalid"
                    and exception_result.get("schema_id") == STATUS_SCHEMA,
                    "unexpected exception did not produce invalid JSON",
                    failures,
                )
                exception_output = json.dumps(exception_result, ensure_ascii=True).encode("ascii")
                require(
                    PATH_CANARY.encode("ascii") not in exception_output
                    and CANARY not in exception_output,
                    "unexpected exception canary leaked into status JSON",
                    failures,
                )
        finally:
            exception_module._status_scan_anchored = original_exception_scan

        status_after = git_output("status", "--porcelain=v1", "--untracked-files=all")
        require(status_after == status_before, "status smoke changed repository status", failures)
        result = {
            "cases": len(recovery_cases) + len(invalid_cases) + 5,
            "default_python": sys.version.split()[0],
            "failures": failures,
            "installed_entrypoint": "verified" if entrypoint is not None else "unavailable",
            "ok": not failures,
            "protected_canaries_preserved": (
                snapshot(protected_config) == config_before
                and snapshot(protected_epoch) == epoch_before
            ),
            "root_swap_rejected": swapped and swap_code == 1,
            "schema_id": STATUS_SCHEMA,
            "status_contract": "installed_tree_only",
            "symlink_swap_rejected": symlink_raced and symlink_race_code == 1,
        }
        print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
        return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
