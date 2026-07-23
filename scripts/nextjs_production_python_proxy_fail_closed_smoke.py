#!/usr/bin/env python3
"""Prove a built production Next artifact cannot fall through to Python."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXT_APP = ROOT / "ui" / "next-app"
WORKSPACE_ROUTE_ROOT = NEXT_APP / "app" / "workspace"
CONTRACT_ID = "nextjs_production_python_proxy_fail_closed_v2"
COMPATIBILITY_CONTRACT_ID = "nextjs_production_python_proxy_fail_closed_v1"
EXPECTED_DIRECT_READ_ROUTE_COUNT = 10
EXPECTED_WORKSPACE_PROXY_ROUTE_COUNT = 16
EXPECTED_APPROVAL_DECISION_ROUTE_COUNT = 2
EXPECTED_AGENT_GATEWAY_APPROVAL_REQUEST_ROUTE_COUNT = 1
BUILD_TIMEOUT_SECONDS = 300
STARTUP_TIMEOUT_SECONDS = 90
REQUEST_TIMEOUT_SECONDS = 10
PROCESS_STOP_TIMEOUT_SECONDS = 10
WORKSPACE_APPROVAL_REVIEW_PATH = "/workspace/approvals/review"

POSTGRES_UNAVAILABLE_ERROR = "typescript_control_plane_unavailable"
POSTGRES_UNAVAILABLE_MESSAGE = "The TypeScript Postgres control plane could not complete the request."

DIRECT_READ_PATHS = (
    "/api/mis/tasks",
    "/api/mis/tasks/python-proxy-smoke-task",
    "/api/mis/runs",
    "/api/mis/runs/python-proxy-smoke-run",
    "/api/mis/runs/python-proxy-smoke-run/graph",
    "/api/mis/approvals",
    "/api/mis/audit",
    "/api/mis/dashboard/metrics",
    "/api/mis/tool-calls",
    "/api/mis/evaluations",
)
DIRECT_READ_CASES = tuple(
    (path, 503, POSTGRES_UNAVAILABLE_ERROR, POSTGRES_UNAVAILABLE_MESSAGE)
    for path in DIRECT_READ_PATHS
)

APPROVAL_DECISION_PATHS = (
    "/api/mis/approvals/python-proxy-smoke-approval/approve",
    "/api/mis/approvals/python-proxy-smoke-approval/reject",
)
APPROVAL_DECISION_CASES = tuple(
    (path, 503, POSTGRES_UNAVAILABLE_ERROR, POSTGRES_UNAVAILABLE_MESSAGE)
    for path in APPROVAL_DECISION_PATHS
)

AGENT_GATEWAY_APPROVAL_REQUEST_CASES = (
    (
        "/api/mis/agent-gateway/approvals/request",
        503,
        POSTGRES_UNAVAILABLE_ERROR,
        POSTGRES_UNAVAILABLE_MESSAGE,
    ),
)

EXPECTED_COMPILED_API_ROUTE_KEYS = {
    "/api/mis/[...path]/route",
    "/api/mis/agent-gateway/approvals/request/route",
    "/api/mis/approvals/[approvalId]/[decision]/route",
    "/api/mis/approvals/route",
    "/api/mis/audit/route",
    "/api/mis/dashboard/metrics/route",
    "/api/mis/evaluations/route",
    "/api/mis/runs/[runId]/graph/route",
    "/api/mis/runs/[runId]/route",
    "/api/mis/runs/route",
    "/api/mis/tasks/[taskId]/route",
    "/api/mis/tasks/route",
    "/api/mis/tool-calls/route",
}


class UpstreamHandler(BaseHTTPRequestHandler):
    hits = 0
    hits_lock = threading.Lock()

    @classmethod
    def reset(cls) -> None:
        with cls.hits_lock:
            cls.hits = 0

    @classmethod
    def hit_count(cls) -> int:
        with cls.hits_lock:
            return cls.hits

    def respond(self) -> None:
        with type(self).hits_lock:
            type(self).hits += 1
        body = json.dumps({"ok": True, "unexpected_python_proxy": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self.respond()

    def do_POST(self) -> None:  # noqa: N802
        self.respond()

    def log_message(self, _format: str, *_args: object) -> None:
        return


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        _request: urllib.request.Request,
        _file_pointer: object,
        _code: int,
        _message: str,
        _headers: object,
        _new_url: str,
    ) -> None:
        return None


def free_port() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    port = int(server.server_port)
    server.server_close()
    return port


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object], dict[str, str]]:
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw or "{}")
            require(isinstance(payload, dict), f"response was not a JSON object: {url}")
            return int(response.status), payload, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(raw or "{}")
        require(isinstance(payload, dict), f"error response was not a JSON object: {url}")
        return int(exc.code), payload, dict(exc.headers.items())


def request_without_redirect(
    url: str,
    *,
    method: str,
    body: bytes,
    headers: dict[str, str],
) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(NoRedirectHandler())
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return int(response.status), response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(), dict(exc.headers.items())


def log_tail(path: Path, limit: int = 5000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except FileNotFoundError:
        return ""


def stop_process_group(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=PROCESS_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


class ProcessGuard:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None

    def __enter__(self) -> ProcessGuard:
        return self

    def __exit__(self, _exc_type: object, _exc_value: object, _traceback: object) -> None:
        stop_process_group(self.process)


def run_next_build(node: str, next_cli: Path, app_dir: Path, env: dict[str, str], log_path: Path) -> None:
    process: subprocess.Popen[str] | None = None
    with log_path.open("w", encoding="utf-8") as output:
        try:
            process = subprocess.Popen(
                [node, str(next_cli), "build"],
                cwd=app_dir,
                env=env,
                text=True,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                return_code = process.wait(timeout=BUILD_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as exc:
                stop_process_group(process)
                raise RuntimeError(
                    f"Next production build exceeded {BUILD_TIMEOUT_SECONDS}s: {log_tail(log_path)}"
                ) from exc
        finally:
            stop_process_group(process)
    if return_code != 0:
        raise RuntimeError(f"Next production build failed with {return_code}: {log_tail(log_path)}")


def wait_for_next(
    base_url: str,
    process: subprocess.Popen[str],
    log_path: Path,
) -> tuple[int, dict[str, object], dict[str, str]]:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Next production artifact exited early: {log_tail(log_path)}")
        try:
            return request_json(f"{base_url}/api/mis/not-migrated-production-probe")
        except (OSError, ValueError, json.JSONDecodeError) as exc:  # pragma: no cover - readiness diagnostics
            last_error = str(exc)
            time.sleep(0.2)
    raise RuntimeError(f"Next production artifact did not become ready: {last_error}; {log_tail(log_path)}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_no_store(headers: dict[str, str], path: str) -> None:
    cache_control = next((value for key, value in headers.items() if key.lower() == "cache-control"), "")
    require("no-store" in cache_control.lower(), f"production response is cacheable: {path}")


def require_no_python_hit(path: str) -> None:
    require(UpstreamHandler.hit_count() == 0, f"production route reached the Python upstream: {path}")


def production_environment(upstream_port: int) -> dict[str, str]:
    env = {
        key: os.environ[key]
        for key in ("HOME", "LANG", "LC_ALL", "PATH", "SHELL", "TMPDIR", "TMP", "TEMP")
        if os.environ.get(key)
    }
    env.update({
        "AGENTOPS_DEPLOYMENT_MODE": "production",
        "AGENTOPS_CONTROL_PLANE_MODE": "proxy",
        "AGENTOPS_API_BASE": f"http://127.0.0.1:{upstream_port}/api",
        "NEXT_TELEMETRY_DISABLED": "1",
        "NODE_ENV": "production",
    })
    return env


def copy_isolated_next_app(destination: Path) -> None:
    def hardlink_or_copy(source: str, target: str) -> str:
        try:
            os.link(source, target)
            return target
        except OSError:
            return shutil.copy2(source, target)

    def ignore(_directory: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name in {".next", "node_modules"} or name.startswith(".env")}
        return ignored

    shutil.copytree(NEXT_APP, destination, ignore=ignore)
    shutil.copytree(
        NEXT_APP / "node_modules",
        destination / "node_modules",
        copy_function=hardlink_or_copy,
        symlinks=True,
    )


def require_compiled_api_routes(app_dir: Path) -> set[str]:
    manifest_path = app_dir / ".next" / "server" / "app-paths-manifest.json"
    require(manifest_path.is_file(), "next build did not create the app paths manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict), "Next app paths manifest is not a JSON object")
    compiled_routes = {str(key) for key in manifest}
    missing_routes = sorted(EXPECTED_COMPILED_API_ROUTE_KEYS - compiled_routes)
    require(not missing_routes, f"production artifact omitted expected API routes: {missing_routes}")
    return EXPECTED_COMPILED_API_ROUTE_KEYS & compiled_routes


def workspace_python_proxy_route_paths() -> list[str]:
    paths: list[str] = []
    for route_file in sorted(WORKSPACE_ROUTE_ROOT.glob("**/route.ts")):
        route_text = route_file.read_text(encoding="utf-8")
        if "AGENTOPS_API_BASE" not in route_text:
            continue
        guard_index = route_text.find("legacyWorkspacePythonProxyGuard(request)")
        require(guard_index >= 0, f"legacy workspace route has no request-bound guard: {route_file}")
        for operation in ("request.formData(", "request.json(", "fetch("):
            operation_index = route_text.find(operation)
            require(
                operation_index < 0 or guard_index < operation_index,
                f"legacy workspace route guard follows {operation}: {route_file}",
            )
        route_parts: list[str] = []
        for part in route_file.parent.relative_to(WORKSPACE_ROUTE_ROOT).parts:
            if part.startswith("[") and part.endswith("]"):
                parameter = part[1:-1]
                require(parameter == "projectId", f"unmapped dynamic workspace route segment: {part}")
                route_parts.append("python-proxy-smoke-project")
            else:
                route_parts.append(part)
        paths.append("/workspace/" + "/".join(route_parts))
    require(
        len(paths) == EXPECTED_WORKSPACE_PROXY_ROUTE_COUNT,
        f"expected {EXPECTED_WORKSPACE_PROXY_ROUTE_COUNT} legacy workspace proxy routes, found {len(paths)}",
    )
    return paths


def exercise_json_cases(
    base_url: str,
    cases: tuple[tuple[str, int, str, str], ...],
    *,
    method: str = "GET",
) -> dict[str, int]:
    statuses: dict[str, int] = {}
    for path, expected_status, expected_error, expected_message in cases:
        body = json.dumps({"workspace_id": "workspace-python-proxy-smoke"}).encode("utf-8") if method == "POST" else None
        headers = None
        if body is not None:
            decision_name = path.rsplit("/", 1)[-1]
            headers = {
                "Content-Type": "application/json",
                "Idempotency-Key": f"python-proxy-smoke-{decision_name}-0001",
                "Origin": base_url,
            }
        status, payload, response_headers = request_json(
            f"{base_url}{path}",
            method=method,
            body=body,
            headers=headers,
        )
        require(status == expected_status, f"production route returned {status}, expected {expected_status}: {path}")
        require(
            payload.get("error") == expected_error,
            f"production route returned {payload.get('error')!r}, expected {expected_error}: {path}",
        )
        require(payload.get("message") == expected_message, f"production request did not reach its compiled route: {path}")
        require(payload.get("unexpected_python_proxy") is not True, f"production route returned the Python observer: {path}")
        require_no_store(response_headers, path)
        require_no_python_hit(path)
        statuses[path] = status
    return statuses


def exercise_workspace_approval_form(base_url: str) -> int:
    approval_id = "python-proxy-smoke-approval"
    form = urllib.parse.urlencode({
        "approval_id": approval_id,
        "decision": "approve",
        "workspace_id": "workspace-python-proxy-smoke",
        "csrf_token": "0" * 64,
        "idempotency_key": "python-proxy-smoke-approval-form-0001",
    }).encode("ascii")
    status, _response_body, headers = request_without_redirect(
        f"{base_url}{WORKSPACE_APPROVAL_REVIEW_PATH}",
        method="POST",
        body=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": base_url,
            "Sec-Fetch-Site": "same-origin",
        },
    )
    require(status == 303, f"production approval review form returned {status}")
    location = next((value for key, value in headers.items() if key.lower() == "location"), "")
    parsed_location = urllib.parse.urlparse(location)
    query = urllib.parse.parse_qs(parsed_location.query)
    require(parsed_location.path == "/workspace/approvals", "approval review redirect target drifted")
    require(
        query.get("review_error") == [POSTGRES_UNAVAILABLE_ERROR],
        "production approval review form did not reach the TypeScript Postgres owner",
    )
    require(query.get("approval_id") == [approval_id], "approval review redirect lost its synthetic reference")
    require_no_store(headers, WORKSPACE_APPROVAL_REVIEW_PATH)
    require_no_python_hit(WORKSPACE_APPROVAL_REVIEW_PATH)
    return status


def main() -> int:
    node = shutil.which("node")
    require(bool(node), "node is required")
    next_cli = NEXT_APP / "node_modules" / "next" / "dist" / "bin" / "next"
    require(next_cli.exists(), "ui/next-app dependencies are required")
    require(len(DIRECT_READ_CASES) == EXPECTED_DIRECT_READ_ROUTE_COUNT, "direct-read coverage count drifted")
    require(
        len(APPROVAL_DECISION_CASES) == EXPECTED_APPROVAL_DECISION_ROUTE_COUNT,
        "approval-decision coverage count drifted",
    )
    require(
        len(AGENT_GATEWAY_APPROVAL_REQUEST_CASES)
        == EXPECTED_AGENT_GATEWAY_APPROVAL_REQUEST_ROUTE_COUNT,
        "Agent Gateway approval-request coverage count drifted",
    )

    UpstreamHandler.reset()
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    env = production_environment(int(upstream.server_port))
    process: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-production-smoke-") as temporary_directory, ProcessGuard() as process_guard:
            temporary_root = Path(temporary_directory)
            env.update({
                "TMPDIR": str(temporary_root),
                "TMP": str(temporary_root),
                "TEMP": str(temporary_root),
            })
            isolated_app = temporary_root / "next-app"
            build_log = temporary_root / "next-build.log"
            start_log = temporary_root / "next-start.log"
            copy_isolated_next_app(isolated_app)
            require(not (isolated_app / ".next").exists(), "isolated Next app unexpectedly contained a stale build")
            isolated_next_cli = isolated_app / "node_modules" / "next" / "dist" / "bin" / "next"
            require(isolated_next_cli.exists(), "isolated Next app is missing the Next CLI")
            run_next_build(str(node), isolated_next_cli, isolated_app, env, build_log)
            build_id_path = isolated_app / ".next" / "BUILD_ID"
            require(build_id_path.is_file(), "next build did not create .next/BUILD_ID")
            require(bool(build_id_path.read_text(encoding="utf-8").strip()), "next build created an empty BUILD_ID")
            compiled_api_routes = require_compiled_api_routes(isolated_app)

            next_port = free_port()
            base_url = f"http://127.0.0.1:{next_port}"
            env["AGENTOPS_ALLOWED_ORIGINS"] = base_url
            with start_log.open("w", encoding="utf-8") as output:
                process = subprocess.Popen(
                    [str(node), str(isolated_next_cli), "start", "-H", "127.0.0.1", "-p", str(next_port)],
                    cwd=isolated_app,
                    env=env,
                    text=True,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                process_guard.process = process
                status, payload, headers = wait_for_next(base_url, process, start_log)
                require(status == 503, f"production catch-all returned {status}")
                require(
                    payload.get("error") == "typescript_route_owner_required",
                    "production catch-all lost its route-owner error",
                )
                require(
                    payload.get("python_proxy_performed") is False,
                    "production catch-all did not deny Python proxy execution",
                )
                require_no_store(headers, "/api/mis/not-migrated-production-probe")
                require_no_python_hit("/api/mis/not-migrated-production-probe")

                direct_read_statuses = exercise_json_cases(base_url, DIRECT_READ_CASES)
                approval_decision_statuses = exercise_json_cases(
                    base_url,
                    APPROVAL_DECISION_CASES,
                    method="POST",
                )
                approval_request_statuses = exercise_json_cases(
                    base_url,
                    AGENT_GATEWAY_APPROVAL_REQUEST_CASES,
                    method="POST",
                )
                workspace_route_statuses: dict[str, int] = {}
                for path in workspace_python_proxy_route_paths():
                    if path == WORKSPACE_APPROVAL_REVIEW_PATH:
                        workspace_route_statuses[path] = exercise_workspace_approval_form(base_url)
                        continue
                    route_status, route_payload, route_headers = request_json(
                        f"{base_url}{path}",
                        method="POST",
                        body=b"{}",
                        headers={"Content-Type": "application/json"},
                    )
                    require(route_status == 503, f"production legacy workspace route returned {route_status}: {path}")
                    require(
                        route_payload.get("error") == "typescript_route_owner_required",
                        f"production legacy workspace route lost its route-owner error: {path}",
                    )
                    require(
                        route_payload.get("python_proxy_performed") is False,
                        f"production legacy workspace route did not deny Python proxy execution: {path}",
                    )
                    require_no_store(route_headers, path)
                    require_no_python_hit(path)
                    workspace_route_statuses[path] = route_status

                upstream_request_count = UpstreamHandler.hit_count()
                require(upstream_request_count == 0, "production acceptance observed a Python upstream request")
                print(json.dumps({
                    "ok": True,
                    "contract": CONTRACT_ID,
                    "compatibility_contract": COMPATIBILITY_CONTRACT_ID,
                    "status": status,
                    "production_artifact_built": True,
                    "production_artifact_started_with_next_start": True,
                    "compiled_api_route_count": len(compiled_api_routes),
                    "next_dev_used": False,
                    "isolated_build_directory": True,
                    "isolated_loopback_port": True,
                    "production_proxy_configuration_coerced_to_postgres": True,
                    "bounded_build_timeout_seconds": BUILD_TIMEOUT_SECONDS,
                    "bounded_startup_timeout_seconds": STARTUP_TIMEOUT_SECONDS,
                    "python_api_started": False,
                    "python_proxy_performed": False,
                    "upstream_request_count": upstream_request_count,
                    "production_route_owner_required": True,
                    "direct_read_route_count": len(direct_read_statuses),
                    "direct_read_route_statuses": direct_read_statuses,
                    "typescript_owned_workspace_route_statuses": direct_read_statuses,
                    "typescript_owned_workspace_routes_python_blocked": True,
                    "approval_decision_route_count": len(approval_decision_statuses),
                    "approval_decision_route_statuses": approval_decision_statuses,
                    "approval_decision_routes_python_blocked": True,
                    "agent_gateway_approval_request_route_count": len(approval_request_statuses),
                    "agent_gateway_approval_request_route_statuses": approval_request_statuses,
                    "agent_gateway_approval_request_python_blocked": True,
                    "synthetic_human_mutation_headers_used": True,
                    "legacy_workspace_route_count": len(workspace_route_statuses),
                    "legacy_workspace_route_statuses": workspace_route_statuses,
                    "legacy_workspace_guard_precedes_body_and_upstream": True,
                    "legacy_workspace_routes_python_blocked": True,
                    "workspace_approval_review_redirect_not_followed": True,
                    "temporary_artifact_cleanup_enabled": True,
                    "credentials_omitted": True,
                    "raw_data_omitted": True,
                }, indent=2, sort_keys=True))
                return 0
    finally:
        stop_process_group(process)
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
