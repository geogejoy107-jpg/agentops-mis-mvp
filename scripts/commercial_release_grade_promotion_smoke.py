#!/usr/bin/env python3
"""Smoke the controlled Gate 1-5 release-grade promotion transaction."""
from __future__ import annotations

import copy
import concurrent.futures
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "commercial_release_grade_promotion.py"
LAUNCHER = ROOT / "scripts" / "commercial_release_grade_promotion"
CONTRACT_ID = "commercial_release_grade_promotion_v1"
PAYLOAD_CONTRACT_ID = "commercial_release_grade_promotion_payload_v1"
REQUIRED_GATE_IDS = [
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
]
REQUIRED_CI_JOBS = [
    "Commercial core gates",
    "Storage and Postgres parity",
    "UI parity and build evidence",
    "Independent Postgres and BYOC evidence",
    "Assemble immutable commercial CI receipt",
]
CI_RUN_ID = "29606036932"
CI_WORKFLOW_ID = 301537454
CI_WORKFLOW_PATH = ".github/workflows/commercial-migration-ci.yml"
AGENT_GATEWAY_RUN_ID = "run_gw_promotionfixture"
OPENCLAW_RUN_ID = "run_api_integrations_openclaw_probe_20260718000000000000_promotionfx"
HERMES_RUN_ID = "run_api_integrations_hermes_run_task_20260718000000000000_promotionfx"
GITHUB_ARTIFACT_ID = "42424242"
GITHUB_TOKEN = "github_pat_promotion_smoke_fixture_secret_1234567890"
PRODUCTION_GITHUB_API_BASE_LINE = 'GITHUB_API_BASE_URL = "https://api.github.com"'
PRODUCTION_GITHUB_API_HTTPS_LINE = "GITHUB_API_REQUIRE_HTTPS = True"
PRODUCTION_DIRECTORY_FSYNC_LINE = "DIRECTORY_FSYNC = os.fsync"
PRODUCTION_RUNTIME_TEST_KEYS_LINE = "RUNTIME_ENVIRONMENT_TEST_KEYS: tuple[str, ...] = ()"
LOCAL_RUNTIME_CLI_BOOTSTRAP = (
    "import runpy,sys;"
    "sys.path.insert(0,sys.argv.pop(1));"
    "runpy.run_module('agentops_mis_cli',run_name='__main__',alter_sys=True)"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 60,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
        check=False,
    )


def git(cwd: Path, *args: str) -> str:
    proc = run(["git", *args], cwd=cwd)
    require(proc.returncode == 0, f"git fixture command failed: {args}")
    return proc.stdout.strip()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def command_for_gate(index: int) -> dict[str, Any]:
    return {
        "command": f"python3 scripts/gate_{index}_release_smoke.py",
        "status": "passed",
        "contract": f"gate_{index}_release_smoke_v1",
        "skipped": False,
    }


def receipts_fixture(head: str, verified_at: str) -> dict[str, Any]:
    receipts = []
    counts = {}
    for index, gate_id in enumerate(REQUIRED_GATE_IDS, start=1):
        commands = [command_for_gate(index)]
        counts[gate_id] = len(commands)
        receipts.append({
            "gate_id": gate_id,
            "local_receipt_current": True,
            "release_grade_current": False,
            "receipt_state": "local_receipts_complete_exact_head_required",
            "verified_head": head,
            "verified_at": verified_at,
            "environment": "isolated_smoke_fixture",
            "evidence_level": "local_current_not_release_grade",
            "commands": commands,
            "release_blockers": ["release_grade_receipts_empty"],
        })
    return {
        "contract_id": "commercial_evidence_receipts_v1",
        "status": "partial_local_receipts_not_release_complete",
        "updated_at": verified_at,
        "ci_safe": True,
        "release_complete": False,
        "commercial_handoff_allowed": False,
        "ready_to_merge": False,
        "receipt_summary": {
            "gate_count": len(REQUIRED_GATE_IDS),
            "gates_with_local_receipts": list(REQUIRED_GATE_IDS),
            "gates_with_release_grade_receipts": [],
            "gates_missing_local_receipts": [],
            "local_receipt_command_counts": counts,
            "gate_5_release_grade_current": False,
            "exact_head_ci_verified": False,
            "remote_sync_verified": True,
            "clean_worktree_verified": True,
        },
        "promotion_evidence": {
            "state": "latest_exact_head_ci_and_real_runtime_recorded_current_head_requires_ci",
            "verified_head": head[:7],
            "remote_sync_verified": True,
            "release_grade_blockers": ["release_grade_receipts_empty"],
        },
        "phase_gate_receipts": receipts,
    }


def recorded_receipts_fixture(
    baseline: dict[str, Any],
    *,
    current_head: str,
    verified_at: str,
) -> dict[str, Any]:
    recorded = copy.deepcopy(baseline)
    transaction_id = f"tx_receipt_recording_{current_head[:12]}"
    for receipt in recorded.get("phase_gate_receipts") or []:
        receipt.update({
            "verified_head": current_head,
            "verified_at": verified_at,
            "local_receipt_current": True,
            "release_grade_current": False,
            "receipt_state": "local_receipt_recording_preview_ready",
            "evidence_level": "local_current_not_release_grade",
            "release_grade_update_allowed": False,
            "recording_transaction_id": transaction_id,
        })
    recorded["receipt_summary"].update({
        "gates_with_local_receipts": list(REQUIRED_GATE_IDS),
        "gates_with_release_grade_receipts": [],
        "gates_missing_local_receipts": [],
        "gate_5_release_grade_current": False,
    })
    recorded["receipt_recording_transactions"] = [{
        "transaction_id": transaction_id,
        "recorded_at": verified_at,
        "operation": "explicit_confirm_receipt_recording_transaction",
        "selected_gate_ids": list(REQUIRED_GATE_IDS),
        "current_git_head": current_head,
        "exact_head_ci_verified": True,
        "real_runtime_acceptance_verified": True,
        "current_runtime_evidence_supplied": True,
        "writes_release_grade_receipts": False,
        "allows_handoff_or_merge": False,
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "token_values_omitted": True,
    }]
    return recorded


def promotion_payload(
    head: str,
    receipts: dict[str, Any],
    verified_at: str,
    artifact_hash: str,
) -> dict[str, Any]:
    jobs = [
        {
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "job_id": str(9000 + index),
        }
        for index, name in enumerate(REQUIRED_CI_JOBS)
    ]
    return {
        "contract_id": PAYLOAD_CONTRACT_ID,
        "created_at": verified_at,
        "current_git_head": head,
        "exact_head_ci_evidence": {
            "contract": "commercial_exact_head_ci_evidence_v1",
            "status": "exact_head_ci_verified",
            "head": head,
            "exact_head_ci_verified": True,
            "github_evidence": {
                "provider": "github_actions",
                "workflow": "Commercial Migration CI",
                "workflow_matches_expected": True,
                "run_id": CI_RUN_ID,
                "head": head,
                "head_matches_current": True,
                "status": "completed",
                "conclusion": "success",
                "required_jobs_success": True,
                "required_jobs": jobs,
                "aggregate_receipt": {
                    "verified": True,
                    "contract_id": "commercial_migration_ci_receipt_v1",
                    "subject_sha": head,
                    "run_id": CI_RUN_ID,
                    "sha256": artifact_hash,
                    "raw_output_stored": False,
                    "failures": [],
                    "error": None,
                },
            },
        },
        "real_runtime_acceptance": {
            "source": "operator_supplied_smoke_fixture",
            "current_session": True,
            "verified_head": head,
            "verified_at": verified_at,
            "live_openclaw": True,
            "live_hermes": True,
            "require_hermes_api": True,
            "agent_gateway_run_id": AGENT_GATEWAY_RUN_ID,
            "openclaw_run_id": OPENCLAW_RUN_ID,
            "hermes_run_id": HERMES_RUN_ID,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "private_transcripts_omitted": True,
            "token_values_omitted": True,
        },
        "phase_gate_receipts": [
            {
                "gate_id": item["gate_id"],
                "local_receipt_current": item["local_receipt_current"],
                "verified_head": item["verified_head"],
                "verified_at": item["verified_at"],
                "commands": item["commands"],
            }
            for item in receipts["phase_gate_receipts"]
        ],
    }


def ci_run_fixture(head: str) -> dict[str, Any]:
    return {
        "id": int(CI_RUN_ID),
        "head_sha": head,
        "head_branch": "main",
        "head_repository": {"full_name": "geogejoy107-jpg/agentops-mis-mvp"},
        "repository": {"full_name": "geogejoy107-jpg/agentops-mis-mvp"},
        "workflow_id": CI_WORKFLOW_ID,
        "path": CI_WORKFLOW_PATH,
        "event": "push",
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "html_url": "https://github.com/geogejoy107-jpg/agentops-mis-mvp/actions/runs/29606036932",
        "name": "Commercial Migration CI",
    }


def ci_workflow_fixture() -> dict[str, Any]:
    return {
        "id": CI_WORKFLOW_ID,
        "name": "Commercial Migration CI",
        "path": CI_WORKFLOW_PATH,
        "state": "active",
    }


def ci_jobs_fixture() -> dict[str, Any]:
    jobs = [
        {
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "id": 9000 + index,
        }
        for index, name in enumerate(REQUIRED_CI_JOBS)
    ]
    return {
        "total_count": len(jobs),
        "jobs": jobs,
    }


def ci_artifacts_fixture() -> dict[str, Any]:
    return {
        "total_count": 1,
        "artifacts": [
            {
                "id": int(GITHUB_ARTIFACT_ID),
                "name": "commercial-migration-ci-receipt",
                "expired": False,
                "workflow_run": {"id": int(CI_RUN_ID)},
            }
        ],
    }


def zip_fixture(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in entries:
            member = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_STORED
            archive.writestr(member, raw)
    return buffer.getvalue()


class FakeGitHubAPI:
    def __init__(self, token: str) -> None:
        self._token = token
        self.branch_payload: dict[str, Any] = {}
        self.workflow_payload: dict[str, Any] = {}
        self.run_payload: dict[str, Any] = {}
        self.alternate_run_payload: dict[str, Any] | None = None
        self.run_payload_after_read_count: int | None = None
        self.run_read_count = 0
        self.jobs_payload: dict[str, Any] = {}
        self.artifacts_payload: dict[str, Any] = {}
        self.artifact_archive = b""
        self.artifact_redirect_location: str | None = None
        self.artifact_content_length: int | None = None
        self.requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def send_json(self, status: int, payload: dict[str, Any]) -> None:
                self.send_bytes(status, json_bytes(payload), "application/json")

            def send_bytes(
                self,
                status: int,
                raw: bytes,
                content_type: str,
                *,
                declared_length: int | None = None,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw) if declared_length is None else declared_length))
                self.end_headers()
                if raw:
                    self.wfile.write(raw)

            def do_GET(self) -> None:
                authorization = self.headers.get("Authorization", "")
                authorized = authorization == f"Bearer {fixture._token}"
                parsed = urlsplit(self.path)
                with fixture._lock:
                    fixture.requests.append({
                        "method": "GET",
                        "path": parsed.path,
                        "query": parsed.query,
                        "authorization_present": bool(authorization),
                        "authorized": authorized,
                    })
                if not authorized:
                    self.send_json(401, {"message": "authentication required"})
                    return
                repository = "/repos/geogejoy107-jpg/agentops-mis-mvp"
                run_path = f"{repository}/actions/runs/{CI_RUN_ID}"
                if parsed.path == run_path:
                    with fixture._lock:
                        fixture.run_read_count += 1
                        use_alternate = (
                            fixture.alternate_run_payload is not None
                            and fixture.run_payload_after_read_count is not None
                            and fixture.run_read_count > fixture.run_payload_after_read_count
                        )
                        payload = fixture.alternate_run_payload if use_alternate else fixture.run_payload
                    self.send_json(200, payload or {})
                    return
                routes = {
                    f"{repository}/git/ref/heads/main": fixture.branch_payload,
                    f"{repository}/actions/workflows/{CI_WORKFLOW_ID}": fixture.workflow_payload,
                    f"{repository}/actions/runs/{CI_RUN_ID}/attempts/1/jobs": fixture.jobs_payload,
                    f"{repository}/actions/runs/{CI_RUN_ID}/artifacts": fixture.artifacts_payload,
                }
                if parsed.path in routes:
                    self.send_json(200, routes[parsed.path])
                    return
                if parsed.path == f"{repository}/actions/artifacts/{GITHUB_ARTIFACT_ID}/zip":
                    if fixture.artifact_redirect_location is not None:
                        self.send_response(302)
                        self.send_header("Location", fixture.artifact_redirect_location)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    self.send_bytes(
                        200,
                        fixture.artifact_archive,
                        "application/zip",
                        declared_length=fixture.artifact_content_length,
                    )
                    return
                self.send_json(404, {"message": "not found"})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        require(self._server is not None, "fake GitHub API was not started")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


def create_hostile_environment(tmp: Path) -> tuple[dict[str, str], Path]:
    bin_dir = tmp / "fake-bin"
    bin_dir.mkdir()
    fake_git_log_path = tmp / "fake-tool.log"
    for tool_name in ("git", "dirname", "python3"):
        fake_tool_path = bin_dir / tool_name
        fake_tool_path.write_text(
            f"#!/bin/sh\nprintf '%s\\n' {tool_name!r} >> \"$FAKE_TOOL_LOG\"\nexit 97\n",
            encoding="utf-8",
        )
        fake_tool_path.chmod(0o755)
    env = dict(os.environ)
    env.update({
        "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
        "FAKE_TOOL_LOG": str(fake_git_log_path),
        "http_proxy": "http://127.0.0.1:9",
        "https_proxy": "http://127.0.0.1:9",
        "all_proxy": "http://127.0.0.1:9",
        "no_proxy": "attacker.invalid",
    })
    return env, fake_git_log_path


def ci_artifact_fixture(head: str) -> dict[str, Any]:
    scopes = [
        "gate_3_storage_boundary_before_postgres",
        "gate_5_byoc_enterprise_deployment_ci",
    ]
    return {
        "contract_id": "commercial_migration_ci_receipt_v1",
        "generated_at": now_iso(),
        "subject_sha": head,
        "builder_sha": head,
        "github_run": {
            "run_id": CI_RUN_ID,
            "run_attempt": "1",
            "workflow": "Commercial Migration CI",
        },
        "required_scopes": scopes,
        "scope_receipts": [
            {
                "gate_id": gate_id,
                "receipt_sha256": hashlib.sha256(gate_id.encode("utf-8")).hexdigest(),
                "scope_evidence_complete": True,
            }
            for gate_id in scopes
        ],
        "missing_scopes": [],
        "invalid_scopes": [],
        "job_results": {name: "success" for name in REQUIRED_CI_JOBS[:-1]},
        "failing_jobs": [],
        "scope_evidence_complete": True,
        "ci_run_complete": True,
        "failures": [],
        "raw_output_stored": False,
        "credentials_stored": False,
        "release_complete": False,
        "commercial_handoff_allowed": False,
        "ready_to_merge": False,
    }


def runtime_acceptance_stub() -> str:
    return f'''#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

expected = [
    "--base-url",
    "http://127.0.0.1:8787",
    "--live-openclaw",
    "--live-hermes",
    "--require-hermes-api",
    "--openclaw-timeout",
    "300",
    "--hermes-timeout",
    "600",
    "--request-timeout",
    "720",
]
log_path = Path(os.environ["FAKE_RUNTIME_LOG"])
existing_calls = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
call_number = len(existing_calls) + 1
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({{
        "args": sys.argv[1:],
        "hermes_allow_real_run": os.environ.get("HERMES_ALLOW_REAL_RUN"),
        "agentops_base_url": os.environ.get("AGENTOPS_BASE_URL"),
        "github_credentials_present": any(os.environ.get(key) for key in ("GITHUB_TOKEN", "GH_TOKEN")),
        "proxy_environment_present": any(
            key.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"} and bool(value)
            for key, value in os.environ.items()
        ),
        "path": os.environ.get("PATH"),
        "python_environment": sorted(key for key in os.environ if key.upper().startswith("PYTHON")),
        "python_isolated": sys.flags.isolated,
        "python_no_user_site": sys.flags.no_user_site,
        "python_no_site": sys.flags.no_site,
        "python_dont_write_bytecode": sys.dont_write_bytecode,
    }}) + "\\n")
if (
    sys.argv[1:] != expected
    or os.environ.get("HERMES_ALLOW_REAL_RUN") != "true"
    or sys.flags.isolated != 1
    or sys.flags.no_user_site != 1
    or sys.flags.no_site != 1
    or not sys.dont_write_bytecode
):
    raise SystemExit(7)
mode = os.environ.get("FAKE_RUNTIME_MODE", "ok")
time.sleep(float(os.environ.get("FAKE_RUNTIME_DELAY", "0")))
if mode == "fail":
    raise SystemExit(8)
if mode == "invalid_json":
    print("not-json")
    raise SystemExit(0)
agent_gateway_run_id = "{AGENT_GATEWAY_RUN_ID}_call" + str(call_number)
openclaw_run_id = "{OPENCLAW_RUN_ID}_call" + str(call_number)
hermes_run_id = "{HERMES_RUN_ID}_call" + str(call_number)
if mode == "replayed_ids":
    agent_gateway_run_id = "{AGENT_GATEWAY_RUN_ID}"
    openclaw_run_id = "{OPENCLAW_RUN_ID}"
    hermes_run_id = "{HERMES_RUN_ID}"
omission_ok = mode != "bad_omission"
payload = {{
    "ok": True,
    "live_openclaw": True,
    "live_hermes": True,
    "require_hermes_api": True,
    "checks": [
        {{
            "name": "Agent Gateway CLI smoke",
            "ok": True,
            "detail": {{"run_id": agent_gateway_run_id}},
        }},
        {{
            "name": "POST /api/integrations/openclaw/probe live",
            "ok": True,
            "detail": {{
                "run_id": openclaw_run_id,
                "ok": True,
                "dry_run": False,
                "provider_call_performed": True,
                "raw_prompt_omitted": omission_ok,
                "raw_response_omitted": True,
                "token_omitted": True,
            }},
        }},
        {{
            "name": "POST /api/integrations/hermes/run-task live",
            "ok": True,
            "detail": {{
                "run_id": hermes_run_id,
                "ok": True,
                "dry_run": False,
                "provider_call_performed": True,
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "token_omitted": True,
            }},
        }},
    ],
}}
print(json.dumps(payload))
'''


def run_promotion(
    *,
    repo: Path,
    payload_path: Path,
    receipts_path: Path,
    confirm: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    args = [
        str(repo / "scripts" / "commercial_release_grade_promotion"),
        "--promotion-payload-json",
        str(payload_path),
        "--receipts-path",
        str(receipts_path),
        "--max-evidence-age-seconds",
        "3600",
    ]
    if confirm:
        args.append("--confirm-promotion")
    return run(args, cwd=ROOT, timeout=90, env=env)


def create_synced_repo(tmp: Path, github_api_base_url: str) -> tuple[Path, str]:
    remote = tmp / "remote.git"
    repo = tmp / "repo"
    require(run(["git", "init", "--bare", str(remote)], cwd=tmp).returncode == 0, "bare remote init failed")
    require(run(["git", "clone", str(remote), str(repo)], cwd=tmp).returncode == 0, "fixture clone failed")
    git(repo, "config", "user.name", "AgentOps Promotion Smoke")
    git(repo, "config", "user.email", "promotion-smoke@example.invalid")
    git(repo, "remote", "rename", "origin", "fixture")
    git(repo, "remote", "add", "origin", "https://github.com/geogejoy107-jpg/agentops-mis-mvp.git")
    (repo / "fixture.txt").write_text("promotion fixture\n", encoding="utf-8")
    docs = repo / "docs"
    docs.mkdir()
    scripts = repo / "scripts"
    scripts.mkdir()
    production_script = (ROOT / "scripts" / "commercial_release_grade_promotion.py").read_text(encoding="utf-8")
    require(
        production_script.count(PRODUCTION_GITHUB_API_BASE_LINE) == 1,
        "production GitHub API base marker changed",
    )
    require(
        production_script.count(PRODUCTION_GITHUB_API_HTTPS_LINE) == 1,
        "production GitHub API HTTPS marker changed",
    )
    require(production_script.count(PRODUCTION_DIRECTORY_FSYNC_LINE) == 1, "production directory fsync marker changed")
    require(production_script.count(PRODUCTION_RUNTIME_TEST_KEYS_LINE) == 1, "production runtime test-key marker changed")
    fixture_script = production_script.replace(
        PRODUCTION_GITHUB_API_BASE_LINE,
        f"GITHUB_API_BASE_URL = {github_api_base_url!r}",
    ).replace(
        PRODUCTION_GITHUB_API_HTTPS_LINE,
        "GITHUB_API_REQUIRE_HTTPS = False",
    )
    fixture_script = fixture_script.replace(
        PRODUCTION_DIRECTORY_FSYNC_LINE,
        """def DIRECTORY_FSYNC(descriptor):
    if os.environ.get("FAKE_DIRECTORY_FSYNC_FAIL") == "1":
        raise OSError("fixture directory fsync failure")
    return os.fsync(descriptor)""",
    )
    fixture_script = fixture_script.replace(
        PRODUCTION_RUNTIME_TEST_KEYS_LINE,
        "RUNTIME_ENVIRONMENT_TEST_KEYS = (\"FAKE_RUNTIME_LOG\", \"FAKE_RUNTIME_MODE\", \"FAKE_RUNTIME_DELAY\", \"FAKE_DIRECTORY_FSYNC_FAIL\")",
    )
    (scripts / "commercial_release_grade_promotion.py").write_text(fixture_script, encoding="utf-8")
    launcher_path = scripts / "commercial_release_grade_promotion"
    launcher_path.write_text((ROOT / "scripts" / "commercial_release_grade_promotion").read_text(encoding="utf-8"), encoding="utf-8")
    launcher_path.chmod(0o755)
    (scripts / "local_runtime_acceptance.py").write_text(runtime_acceptance_stub(), encoding="utf-8")
    shutil.copy2(ROOT / "scripts" / "agentops", scripts / "agentops")
    shutil.copytree(ROOT / "agentops_mis_cli", repo / "agentops_mis_cli")
    write_json(docs / "COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", {
        "contract_id": "commercial_release_evidence_packet_v1",
        "phase_gate_evidence": [
            {
                "id": gate_id,
                "required_commands": [command_for_gate(index)["command"]],
            }
            for index, gate_id in enumerate(REQUIRED_GATE_IDS, start=1)
        ],
    })
    git(
        repo,
        "add",
        "fixture.txt",
        "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json",
        "scripts/commercial_release_grade_promotion.py",
        "scripts/commercial_release_grade_promotion",
        "scripts/local_runtime_acceptance.py",
        "scripts/agentops",
        "agentops_mis_cli",
    )
    git(repo, "commit", "-m", "promotion fixture")
    git(repo, "branch", "-M", "main")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "config", "branch.main.remote", "origin")
    git(repo, "config", "branch.main.merge", "refs/heads/main")
    require(git(repo, "rev-parse", "--abbrev-ref", "@{u}") == "origin/main", "fixture upstream was not origin/main")
    return repo, git(repo, "rev-parse", "HEAD")


def prefilled_existing_promotion(
    receipts: dict[str, Any],
    *,
    transaction_id: str,
    head: str,
    artifact_hash: str,
    verified_at: str,
) -> dict[str, Any]:
    forged = copy.deepcopy(receipts)
    summary = forged["receipt_summary"]
    summary.update({
        "gates_with_release_grade_receipts": list(REQUIRED_GATE_IDS),
        "gate_5_release_grade_current": True,
        "exact_head_ci_verified": True,
        "remote_sync_verified": True,
        "clean_worktree_verified": True,
        "release_grade_verified_head": head,
        "release_grade_verified_at": verified_at,
        "release_grade_promotion_id": transaction_id,
    })
    forged_runtime = {
        "verified_head": head,
        "live_openclaw": True,
        "live_hermes": True,
        "require_hermes_api": True,
        "real_runtime_acceptance_verified": True,
        "independent_reexecution_verified": True,
        "operator_run_ids_distinct": True,
        "agent_gateway_run_id": "run_gw_prefilled_attack",
        "openclaw_run_id": "run_api_integrations_openclaw_probe_prefilled_attack",
        "hermes_run_id": "run_api_integrations_hermes_run_task_prefilled_attack",
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "private_transcripts_omitted": True,
        "token_values_omitted": True,
    }
    ci_reference = {
        "contract": "commercial_exact_head_ci_evidence_v1",
        "provider": "github_actions",
        "workflow": "Commercial Migration CI",
        "run_id": CI_RUN_ID,
        "head": head,
        "status": "success",
        "required_jobs": [
            {
                "name": name,
                "job_id": 9000 + index,
                "status": "success",
            }
            for index, name in enumerate(REQUIRED_CI_JOBS)
        ],
        "aggregate_receipt_contract": "commercial_migration_ci_receipt_v1",
        "aggregate_receipt_sha256": artifact_hash,
        "raw_output_stored": False,
        "credentials_stored": False,
        "independently_verified_via_github_api": True,
    }
    forged["promotion_evidence"] = {
        "promotion_transaction_id": transaction_id,
        "verified_head": head,
        "exact_head_ci": ci_reference,
        "real_runtime_acceptance": forged_runtime,
    }
    for gate in forged["phase_gate_receipts"]:
        gate.update({
            "release_grade_current": True,
            "release_grade_promotion_id": transaction_id,
            "release_grade_verified_head": head,
        })
    return forged


def changed_paths(before: Any, after: Any) -> list[str]:
    paths: list[str] = []

    def walk(left: Any, right: Any, prefix: str) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                walk(left.get(key), right.get(key), f"{prefix}/{key}")
            return
        if isinstance(left, list) and isinstance(right, list):
            for index in range(max(len(left), len(right))):
                left_value = left[index] if index < len(left) else None
                right_value = right[index] if index < len(right) else None
                walk(left_value, right_value, f"{prefix}/{index}")
            return
        if left != right:
            paths.append(prefix)

    walk(before, after, "")
    return paths


def main() -> int:
    require(SCRIPT.exists(), "promotion script missing")
    script_text = SCRIPT.read_text(encoding="utf-8")
    for marker in [
        CONTRACT_ID,
        "--promotion-payload-json",
        "--confirm-promotion",
        "load_recording_payload",
        "normalize_runtime_evidence",
        "has_forbidden_payload_text",
        "atomic_write_json",
        "independently_verify_ci",
        "github_api_token_required",
        "github_api_json",
        "download_ci_artifact",
        "extract_ci_receipt",
        "CI_ARTIFACT_NAME",
        "CI_WORKFLOW_ID",
        "CI_WORKFLOW_PATH",
        "CI_RECEIPT_KEYS",
        "run_fixed_runtime_acceptance",
        "FIXED_RUNTIME_ARGUMENTS",
        "GIT_EXECUTABLE_CANDIDATES",
        PRODUCTION_GITHUB_API_BASE_LINE,
        PRODUCTION_GITHUB_API_HTTPS_LINE,
        "sanitized_environment",
        "fixed_runtime_environment",
        "require_no_git_object_overrides",
        "exact_head_ci_reverified_after_runtime",
        "upstream_not_origin_branch",
        "receipts_changed_before_transaction_lock",
        "HERMES_ALLOW_REAL_RUN",
        "GATE_ALLOWED_UPDATE_FIELDS",
        "FORBIDDEN_RECEIPT_FIELDS",
    ]:
        require(marker in script_text, f"promotion implementation missing {marker}")
    require("commercial_release_promotion_preflight" not in script_text, "promotion must not depend on circular preflight state")
    require("validate_existing_promotion" not in script_text, "dirty receipt can still self-attest an existing promotion")
    require("os.environ.get(\"GITHUB_API_BASE_URL\")" not in script_text, "production GitHub API base has an environment bypass")
    require("os.environ.get(\"GITHUB_API_REQUIRE_HTTPS\")" not in script_text, "production GitHub HTTPS policy has an environment bypass")
    runtime_acceptance_text = (ROOT / "scripts" / "local_runtime_acceptance.py").read_text(encoding="utf-8")
    require("ProxyHandler({})" in runtime_acceptance_text, "runtime acceptance does not disable proxy routing")
    require("CLI_BOOTSTRAP" in runtime_acceptance_text, "runtime acceptance CLI bootstrap is missing")
    for marker in (
        '"import runpy,sys;"',
        '"sys.path.insert(0,sys.argv.pop(1));"',
        '"runpy.run_module(\'agentops_mis_cli\',run_name=\'__main__\',alter_sys=True)"',
    ):
        require(marker in runtime_acceptance_text, f"runtime acceptance CLI bootstrap changed: {marker}")
    require(
        '[sys.executable, "-I", "-B", "-S", "-c", CLI_BOOTSTRAP, str(ROOT)' in runtime_acceptance_text,
        "runtime acceptance CLI does not use the trusted isolated source bootstrap",
    )
    isolated_cli = run(
        [sys.executable, "-I", "-B", "-S", "-c", LOCAL_RUNTIME_CLI_BOOTSTRAP, str(ROOT), "--help"],
        cwd=ROOT,
        timeout=30,
    )
    require(isolated_cli.returncode == 0, f"isolated source CLI bootstrap failed: {isolated_cli.stderr}")
    for forbidden_override in [
        "--gh-path",
        "--runtime-command",
        "--acceptance-script",
        "--skip-independent-ci",
        "--skip-runtime-reexecution",
        "--repo-root",
        "--test-only",
    ]:
        require(forbidden_override not in script_text, f"production bypass flag present: {forbidden_override}")

    with tempfile.TemporaryDirectory(prefix="agentops-release-grade-promotion-") as tmp_value:
        tmp = Path(tmp_value)
        source_path = tmp / "source-receipts.json"
        payload_path = tmp / "promotion-payload.json"
        runtime_log_path = tmp / "fixed-runtime.log"
        github_api = FakeGitHubAPI(GITHUB_TOKEN)
        github_api.start()
        env, fake_git_log_path = create_hostile_environment(tmp)
        repo, baseline_head = create_synced_repo(tmp, github_api.base_url)
        verified_at = now_iso()
        target_path = repo / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.json"
        baseline_receipts = receipts_fixture(baseline_head, verified_at)
        write_json(target_path, baseline_receipts)
        git(repo, "add", "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json")
        git(repo, "commit", "-m", "receipt baseline fixture")
        head = git(repo, "rev-parse", "HEAD")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        source_receipts = recorded_receipts_fixture(
            baseline_receipts,
            current_head=head,
            verified_at=verified_at,
        )
        write_json(source_path, source_receipts)
        write_json(target_path, source_receipts)
        artifact_receipt = ci_artifact_fixture(head)
        artifact_raw = json_bytes(artifact_receipt)
        artifact_hash = hashlib.sha256(artifact_raw).hexdigest()
        github_api.branch_payload = {
            "ref": "refs/heads/main",
            "object": {"type": "commit", "sha": head},
        }
        github_api.workflow_payload = ci_workflow_fixture()
        github_api.run_payload = ci_run_fixture(head)
        github_api.jobs_payload = ci_jobs_fixture()
        github_api.artifacts_payload = ci_artifacts_fixture()
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", artifact_raw),
        ])
        payload = promotion_payload(head, source_receipts, verified_at, artifact_hash)
        write_json(payload_path, payload)
        env["FAKE_RUNTIME_LOG"] = str(runtime_log_path)
        env["GITHUB_TOKEN"] = GITHUB_TOKEN
        env.pop("GH_TOKEN", None)
        env["AGENTOPS_BASE_URL"] = "http://127.0.0.1:1"
        env["GIT_DIR"] = str(tmp / "redirected.git")
        env["GIT_WORK_TREE"] = str(tmp / "redirected-worktree")
        env["GH_HOST"] = "example.invalid"
        env["GH_REPO"] = "attacker/redirected"
        env["GH_CONFIG_DIR"] = str(tmp / "redirected-gh-config")
        env["GITHUB_API_URL"] = "https://attacker.invalid/api"
        env["HTTP_PROXY"] = "http://127.0.0.1:1"
        env["HTTPS_PROXY"] = "http://127.0.0.1:1"
        env["ALL_PROXY"] = "http://127.0.0.1:1"
        env["PYTHONPATH"] = str(tmp / "redirected-python-path")
        env["PYTHONUSERBASE"] = str(tmp / "redirected-python-userbase")
        env["PYTHONSTARTUP"] = str(tmp / "redirected-python-startup.py")
        env["PYTHONSAFEPATH"] = "0"
        redirected_python_path = Path(env["PYTHONPATH"])
        redirected_python_path.mkdir(parents=True)
        sitecustomize_marker = tmp / "sitecustomize-loaded"
        (redirected_python_path / "sitecustomize.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(sitecustomize_marker)!r}).write_text('loaded', encoding='utf-8')\n",
            encoding="utf-8",
        )
        fixture_status_proc = run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repo,
        )
        require(fixture_status_proc.returncode == 0, "promotion fixture status unavailable")
        fixture_status = fixture_status_proc.stdout.splitlines()
        require(
            fixture_status == [" M docs/COMMERCIAL_EVIDENCE_RECEIPTS.json"],
            f"promotion fixture has unexpected dirty paths: {fixture_status}",
        )

        direct_env = dict(env)
        direct_env.pop("PYTHONPATH", None)
        direct = run([
            sys.executable,
            str(repo / "scripts" / "commercial_release_grade_promotion.py"),
            "--promotion-payload-json",
            str(payload_path),
            "--receipts-path",
            str(target_path),
        ], cwd=ROOT, timeout=30, env=direct_env)
        require(direct.returncode != 0, "non-isolated direct promotion invocation unexpectedly passed")
        require(json.loads(direct.stdout).get("error_code") == "isolated_launcher_required", "direct invocation isolation rejection mismatch")

        before_preview_hash = file_hash(target_path)
        preview = run_promotion(repo=repo, payload_path=payload_path, receipts_path=target_path, env=env)
        require(preview.returncode == 0, f"promotion preview failed: {preview.stdout}{preview.stderr}")
        require(not sitecustomize_marker.exists(), "promotion launcher loaded attacker-controlled sitecustomize")
        preview_payload = json.loads(preview.stdout)
        require(preview_payload.get("contract") == CONTRACT_ID, "preview contract mismatch")
        require(preview_payload.get("status") == "promotion_preview_ready", "preview status mismatch")
        require(preview_payload.get("applied") is False, "preview must not apply")
        require(preview_payload.get("confirmation_supplied") is False, "preview must not imply confirmation")
        preview_checks = preview_payload.get("checks") or {}
        require(
            preview_checks.get("exact_head_ci_independently_verified_via_github_api") is True,
            "preview did not independently verify CI via the GitHub API",
        )
        require(preview_checks.get("payload_runtime_reference_valid") is True, "preview did not validate runtime reference")
        require(preview_checks.get("real_runtime_acceptance_independently_verified") is False, "preview falsely claimed runtime reexecution")
        require(preview_checks.get("confirm_runtime_reexecution_required") is True, "preview must require confirm runtime reexecution")
        require(preview_checks.get("clean_worktree_verified") is False, "dirty recording receipt was falsely reported as a clean worktree")
        require(preview_checks.get("clean_source_head_verified") is True, "clean source HEAD was not verified")
        require(preview_checks.get("recording_receipt_derivation_verified") is True, "recording receipt was not derived from HEAD")
        require(preview_checks.get("critical_head_bytes_verified") is True, "critical executable HEAD bytes were not verified")
        require((preview_payload.get("safety") or {}).get("live_runtime_executed") is False, "preview executed runtime")
        require((preview_payload.get("safety") or {}).get("receipts_written") is False, "preview must not write receipts")
        require(file_hash(target_path) == before_preview_hash, "preview changed receipt target")
        require(not runtime_log_path.exists(), "preview invoked fixed runtime acceptance")
        api_requests = copy.deepcopy(github_api.requests)
        requested_paths = [item["path"] for item in api_requests]
        repository_path = "/repos/geogejoy107-jpg/agentops-mis-mvp"
        for expected_path in [
            f"{repository_path}/git/ref/heads/main",
            f"{repository_path}/actions/workflows/{CI_WORKFLOW_ID}",
            f"{repository_path}/actions/runs/{CI_RUN_ID}",
            f"{repository_path}/actions/runs/{CI_RUN_ID}/attempts/1/jobs",
            f"{repository_path}/actions/runs/{CI_RUN_ID}/artifacts",
            f"{repository_path}/actions/artifacts/{GITHUB_ARTIFACT_ID}/zip",
        ]:
            require(expected_path in requested_paths, f"preview did not request GitHub API route {expected_path}")
        require(
            all(item.get("authorization_present") is True and item.get("authorized") is True for item in api_requests),
            "GitHub API calls were not authenticated",
        )
        require(
            GITHUB_TOKEN not in json.dumps(api_requests, sort_keys=True),
            "GitHub token leaked into fake API request logs",
        )
        require(
            GITHUB_TOKEN not in preview.stdout and GITHUB_TOKEN not in preview.stderr,
            "GitHub token leaked into promotion output",
        )

        def require_api_rejection(expected_code: str, message: str) -> subprocess.CompletedProcess[str]:
            rejected = run_promotion(repo=repo, payload_path=payload_path, receipts_path=target_path, env=env)
            require(rejected.returncode != 0, f"{message} unexpectedly passed")
            require(bool(rejected.stdout.strip()), f"{message} did not return bounded JSON")
            require(json.loads(rejected.stdout).get("error_code") == expected_code, f"{message} rejection mismatch")
            require(file_hash(target_path) == before_preview_hash, f"{message} changed receipt target")
            require(GITHUB_TOKEN not in rejected.stdout and GITHUB_TOKEN not in rejected.stderr, f"{message} leaked token")
            return rejected

        github_api.branch_payload["object"]["sha"] = "0" * 40
        require_api_rejection(
            "independent_remote_branch_head_mismatch",
            "stale remote-tracking ref bypassed live GitHub branch verification",
        )
        github_api.branch_payload["object"]["sha"] = head
        require(not fake_git_log_path.exists(), "promotion used a PATH-injected launcher tool")

        git(repo, "update-ref", f"refs/replace/{head}", baseline_head)
        require_api_rejection("git_replace_refs_present", "Git replace ref")
        git(repo, "update-ref", "-d", f"refs/replace/{head}")
        common_dir = Path(git(repo, "rev-parse", "--git-common-dir"))
        if not common_dir.is_absolute():
            common_dir = repo / common_dir
        grafts_path = common_dir / "info" / "grafts"
        grafts_path.parent.mkdir(parents=True, exist_ok=True)
        grafts_path.write_text(f"{head}\n", encoding="utf-8")
        require_api_rejection("git_grafts_present", "legacy Git graft")
        grafts_path.unlink()

        git(repo, "update-ref", "refs/remotes/fixture/main", "HEAD")
        git(repo, "config", "branch.main.remote", "fixture")
        wrong_upstream = run_promotion(repo=repo, payload_path=payload_path, receipts_path=target_path, env=env)
        require(wrong_upstream.returncode != 0, "non-origin upstream unexpectedly passed")
        require(
            json.loads(wrong_upstream.stdout).get("error_code") == "upstream_not_origin_branch",
            "non-origin upstream rejection code mismatch",
        )
        git(repo, "config", "branch.main.remote", "origin")
        require(git(repo, "rev-parse", "--abbrev-ref", "@{u}") == "origin/main", "origin upstream was not restored")

        prefilled = prefilled_existing_promotion(
            source_receipts,
            transaction_id=str(preview_payload["transaction_id"]),
            head=head,
            artifact_hash=artifact_hash,
            verified_at=verified_at,
        )
        write_json(target_path, prefilled)
        prefilled_runtime_calls_before = len(runtime_log_path.read_text(encoding="utf-8").splitlines()) if runtime_log_path.exists() else 0
        prefilled_confirm = run_promotion(
            repo=repo,
            payload_path=payload_path,
            receipts_path=target_path,
            confirm=True,
            env=env,
        )
        require(prefilled_confirm.returncode != 0, "prefilled forged promotion receipt unexpectedly self-attested")
        prefilled_payload = json.loads(prefilled_confirm.stdout)
        require(prefilled_payload.get("error_code") == "recording_receipt_derivation_mismatch", "prefilled receipt rejection mismatch")
        require(
            (len(runtime_log_path.read_text(encoding="utf-8").splitlines()) if runtime_log_path.exists() else 0)
            == prefilled_runtime_calls_before,
            "prefilled receipt reached fixed runtime before provenance rejection",
        )
        write_json(target_path, source_receipts)

        failure_cases: list[tuple[str, dict[str, Any], str]] = []
        missing_ci = copy.deepcopy(payload)
        missing_ci.pop("exact_head_ci_evidence")
        failure_cases.append(("missing_ci", missing_ci, "exact_head_ci_evidence_missing"))
        missing_runtime = copy.deepcopy(payload)
        missing_runtime.pop("real_runtime_acceptance")
        failure_cases.append(("missing_runtime", missing_runtime, "real_runtime_evidence_missing"))
        stale = copy.deepcopy(payload)
        stale["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0).isoformat()
        failure_cases.append(("stale_payload", stale, "promotion_payload_created_at_invalid_stale"))
        wrong_head = copy.deepcopy(payload)
        wrong_head["current_git_head"] = "0" * 40
        failure_cases.append(("wrong_head", wrong_head, "promotion_payload_head_mismatch"))
        stale_runtime = copy.deepcopy(payload)
        stale_runtime["real_runtime_acceptance"]["verified_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).replace(microsecond=0).isoformat()
        failure_cases.append(("stale_runtime", stale_runtime, "real_runtime_verified_at_invalid_stale"))
        bypass = copy.deepcopy(payload)
        bypass["release_complete"] = True
        failure_cases.append(("release_bypass", bypass, "promotion_payload_keys_invalid"))
        for name, fixture, expected_code in failure_cases:
            fixture_path = tmp / f"{name}.json"
            write_json(fixture_path, fixture)
            failed = run_promotion(repo=repo, payload_path=fixture_path, receipts_path=target_path, env=env)
            require(failed.returncode != 0, f"{name} promotion unexpectedly passed")
            failed_payload = json.loads(failed.stdout)
            require(failed_payload.get("error_code") == expected_code, f"{name} rejection code mismatch")
            require(file_hash(target_path) == before_preview_hash, f"{name} failure changed receipt target")

        forged_ci_payload = copy.deepcopy(payload)
        forged_ci_payload["exact_head_ci_evidence"]["github_evidence"]["required_jobs"][0]["job_id"] = "forged-job"
        forged_ci_payload_path = tmp / "forged-ci-payload.json"
        write_json(forged_ci_payload_path, forged_ci_payload)
        forged_ci = run_promotion(
            repo=repo,
            payload_path=forged_ci_payload_path,
            receipts_path=target_path,
            env=env,
        )
        require(forged_ci.returncode != 0, "forged payload CI reference unexpectedly passed")
        require(json.loads(forged_ci.stdout).get("error_code") == "payload_ci_job_reference_mismatch", "forged payload CI rejection mismatch")

        github_api.run_payload["head_sha"] = "0" * 40
        require_api_rejection("independent_ci_head_mismatch", "forged GitHub API run")
        github_api.run_payload["head_sha"] = head

        github_api.run_payload["workflow_id"] = 999
        require_api_rejection("independent_ci_workflow_id_mismatch", "forged workflow id")
        github_api.run_payload["workflow_id"] = CI_WORKFLOW_ID
        github_api.run_payload["path"] = ".github/workflows/forged.yml"
        require_api_rejection("independent_ci_workflow_path_mismatch", "forged workflow path")
        github_api.run_payload["path"] = CI_WORKFLOW_PATH
        github_api.run_payload["event"] = "workflow_dispatch"
        require_api_rejection("independent_ci_event_mismatch", "forged workflow event")
        github_api.run_payload["event"] = "push"
        github_api.run_payload["head_repository"] = {"full_name": "attacker/forged"}
        require_api_rejection("independent_ci_head_repository_mismatch", "forged head repository")
        github_api.run_payload["head_repository"] = {"full_name": "geogejoy107-jpg/agentops-mis-mvp"}
        github_api.run_payload["repository"] = {"full_name": "attacker/forged"}
        require_api_rejection("independent_ci_repository_mismatch", "forged run repository")
        github_api.run_payload["repository"] = {"full_name": "geogejoy107-jpg/agentops-mis-mvp"}
        github_api.run_payload["run_attempt"] = 0
        require_api_rejection("independent_ci_run_attempt_invalid", "invalid run attempt")
        github_api.run_payload["run_attempt"] = 1

        github_api.workflow_payload["path"] = ".github/workflows/forged.yml"
        require_api_rejection("independent_ci_workflow_path_mismatch", "forged workflow metadata")
        github_api.workflow_payload = ci_workflow_fixture()
        github_api.workflow_payload["id"] = 999
        require_api_rejection("independent_ci_workflow_id_mismatch", "forged workflow metadata id")
        github_api.workflow_payload = ci_workflow_fixture()
        github_api.workflow_payload["name"] = "Forged Workflow"
        require_api_rejection("independent_ci_workflow_mismatch", "forged workflow metadata name")
        github_api.workflow_payload = ci_workflow_fixture()
        github_api.workflow_payload["state"] = "disabled_manually"
        require_api_rejection("independent_ci_workflow_inactive", "inactive workflow metadata")
        github_api.workflow_payload = ci_workflow_fixture()

        original_job_id = github_api.jobs_payload["jobs"][0]["id"]
        github_api.jobs_payload["jobs"][0]["id"] = 999999
        require_api_rejection("payload_ci_job_reference_mismatch", "forged GitHub API job metadata")
        github_api.jobs_payload["jobs"][0]["id"] = original_job_id

        tampered_artifact = ci_artifact_fixture(head)
        tampered_artifact["generated_at"] = "2099-01-01T00:00:00+00:00"
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", json_bytes(tampered_artifact)),
        ])
        require_api_rejection("payload_ci_artifact_hash_mismatch", "tampered CI artifact")
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", artifact_raw),
        ])

        embedded_pat_artifact = ci_artifact_fixture(head)
        embedded_pat_artifact["generated_at"] = "xgithub_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        embedded_pat_raw = json_bytes(embedded_pat_artifact)
        embedded_pat_payload = copy.deepcopy(payload)
        embedded_pat_payload["exact_head_ci_evidence"]["github_evidence"]["aggregate_receipt"]["sha256"] = hashlib.sha256(
            embedded_pat_raw
        ).hexdigest()
        embedded_pat_payload_path = tmp / "embedded-pat-artifact-payload.json"
        write_json(embedded_pat_payload_path, embedded_pat_payload)
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", embedded_pat_raw),
        ])
        embedded_pat_result = run_promotion(
            repo=repo,
            payload_path=embedded_pat_payload_path,
            receipts_path=target_path,
            env=env,
        )
        require(embedded_pat_result.returncode != 0, "prefixed github_pat artifact value unexpectedly passed")
        require(
            json.loads(embedded_pat_result.stdout).get("error_code") == "sensitive_payload_value_rejected",
            "prefixed github_pat artifact rejection mismatch",
        )
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", artifact_raw),
        ])

        wrong_attempt_artifact = ci_artifact_fixture(head)
        wrong_attempt_artifact["github_run"]["run_attempt"] = "2"
        wrong_attempt_raw = json_bytes(wrong_attempt_artifact)
        wrong_attempt_payload = copy.deepcopy(payload)
        wrong_attempt_payload["exact_head_ci_evidence"]["github_evidence"]["aggregate_receipt"]["sha256"] = hashlib.sha256(
            wrong_attempt_raw
        ).hexdigest()
        wrong_attempt_payload_path = tmp / "wrong-attempt-artifact-payload.json"
        write_json(wrong_attempt_payload_path, wrong_attempt_payload)
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", wrong_attempt_raw),
        ])
        wrong_attempt_result = run_promotion(
            repo=repo,
            payload_path=wrong_attempt_payload_path,
            receipts_path=target_path,
            env=env,
        )
        require(wrong_attempt_result.returncode != 0, "cross-attempt CI artifact unexpectedly passed")
        require(
            json.loads(wrong_attempt_result.stdout).get("error_code") == "independent_ci_receipt_run_attempt_mismatch",
            "cross-attempt CI artifact rejection mismatch",
        )
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", artifact_raw),
        ])

        mixed_scope_artifact = ci_artifact_fixture(head)
        mixed_scope_artifact["scope_receipts"].append("unexpected")
        mixed_scope_raw = json_bytes(mixed_scope_artifact)
        mixed_scope_payload = copy.deepcopy(payload)
        mixed_scope_payload["exact_head_ci_evidence"]["github_evidence"]["aggregate_receipt"]["sha256"] = hashlib.sha256(
            mixed_scope_raw
        ).hexdigest()
        mixed_scope_payload_path = tmp / "mixed-scope-artifact-payload.json"
        write_json(mixed_scope_payload_path, mixed_scope_payload)
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", mixed_scope_raw),
        ])
        mixed_scope_result = run_promotion(
            repo=repo,
            payload_path=mixed_scope_payload_path,
            receipts_path=target_path,
            env=env,
        )
        require(mixed_scope_result.returncode != 0, "mixed-type scope receipt unexpectedly passed")
        require(
            json.loads(mixed_scope_result.stdout).get("error_code") == "independent_ci_receipt_scope_schema_invalid",
            "mixed-type scope receipt rejection mismatch",
        )
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", artifact_raw),
        ])

        invalid_list_artifact = ci_artifact_fixture(head)
        invalid_list_artifact["missing_scopes"] = {}
        invalid_list_raw = json_bytes(invalid_list_artifact)
        invalid_list_payload = copy.deepcopy(payload)
        invalid_list_payload["exact_head_ci_evidence"]["github_evidence"]["aggregate_receipt"]["sha256"] = hashlib.sha256(
            invalid_list_raw
        ).hexdigest()
        invalid_list_payload_path = tmp / "invalid-list-artifact-payload.json"
        write_json(invalid_list_payload_path, invalid_list_payload)
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", invalid_list_raw),
        ])
        invalid_list_result = run_promotion(
            repo=repo,
            payload_path=invalid_list_payload_path,
            receipts_path=target_path,
            env=env,
        )
        require(invalid_list_result.returncode != 0, "non-list missing_scopes unexpectedly passed")
        require(
            json.loads(invalid_list_result.stdout).get("error_code") == "independent_ci_receipt_missing_scopes_schema_invalid",
            "non-list missing_scopes rejection mismatch",
        )
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", artifact_raw),
        ])

        unknown_field_artifact = ci_artifact_fixture(head)
        unknown_field_artifact["details"] = {"raw_output": "hidden material"}
        unknown_field_raw = json_bytes(unknown_field_artifact)
        unknown_field_payload = copy.deepcopy(payload)
        unknown_field_payload["exact_head_ci_evidence"]["github_evidence"]["aggregate_receipt"]["sha256"] = hashlib.sha256(
            unknown_field_raw
        ).hexdigest()
        unknown_field_payload_path = tmp / "unknown-field-artifact-payload.json"
        write_json(unknown_field_payload_path, unknown_field_payload)
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", unknown_field_raw),
        ])
        unknown_field_result = run_promotion(
            repo=repo,
            payload_path=unknown_field_payload_path,
            receipts_path=target_path,
            env=env,
        )
        require(unknown_field_result.returncode != 0, "unknown CI artifact field unexpectedly passed")
        require(
            json.loads(unknown_field_result.stdout).get("error_code") == "independent_ci_receipt_schema_invalid",
            "unknown CI artifact field rejection mismatch",
        )
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", artifact_raw),
        ])

        forged_policy_artifact = ci_artifact_fixture(head)
        forged_policy_artifact["raw_output_stored"] = True
        forged_policy_artifact_raw = json_bytes(forged_policy_artifact)
        forged_policy_payload = copy.deepcopy(payload)
        forged_policy_payload["exact_head_ci_evidence"]["github_evidence"]["aggregate_receipt"]["sha256"] = hashlib.sha256(
            forged_policy_artifact_raw
        ).hexdigest()
        forged_policy_payload_path = tmp / "forged-policy-payload.json"
        write_json(forged_policy_payload_path, forged_policy_payload)
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", forged_policy_artifact_raw),
        ])
        forged_policy = run_promotion(
            repo=repo,
            payload_path=forged_policy_payload_path,
            receipts_path=target_path,
            env=env,
        )
        require(forged_policy.returncode != 0, "forged CI artifact policy unexpectedly passed")
        require(
            json.loads(forged_policy.stdout).get("error_code") == "independent_ci_receipt_raw_output_policy_invalid",
            "forged artifact policy rejection mismatch",
        )
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", artifact_raw),
        ])

        unauthenticated_env = dict(env)
        unauthenticated_env.pop("GITHUB_TOKEN", None)
        unauthenticated_env.pop("GH_TOKEN", None)
        unauthenticated = run_promotion(repo=repo, payload_path=payload_path, receipts_path=target_path, env=unauthenticated_env)
        require(unauthenticated.returncode != 0, "missing GitHub API token unexpectedly passed")
        require(
            json.loads(unauthenticated.stdout).get("error_code") == "github_api_token_required",
            "GitHub API token requirement rejection mismatch",
        )
        require(GITHUB_TOKEN not in unauthenticated.stdout and GITHUB_TOKEN not in unauthenticated.stderr, "token leaked on auth rejection")

        original_artifacts = copy.deepcopy(github_api.artifacts_payload)
        github_api.artifacts_payload["artifacts"][0]["expired"] = True
        require_api_rejection("independent_ci_artifact_expired", "expired GitHub artifact metadata")
        github_api.artifacts_payload = copy.deepcopy(original_artifacts)
        github_api.artifacts_payload["artifacts"][0]["workflow_run"]["id"] = 1
        require_api_rejection("independent_ci_artifact_run_mismatch", "cross-run GitHub artifact metadata")
        github_api.artifacts_payload = copy.deepcopy(original_artifacts)
        github_api.artifacts_payload["artifacts"].append(copy.deepcopy(github_api.artifacts_payload["artifacts"][0]))
        require_api_rejection("independent_ci_artifact_count_invalid", "duplicate GitHub artifact metadata")
        github_api.artifacts_payload = original_artifacts

        github_api.artifact_archive = zip_fixture([
            ("../commercial-migration-ci-receipt.json", artifact_raw),
        ])
        require_api_rejection("independent_ci_artifact_file_invalid", "traversal ZIP member path")
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", artifact_raw),
            ("duplicate/commercial-migration-ci-receipt.json", artifact_raw),
        ])
        require_api_rejection("independent_ci_artifact_file_count_invalid", "duplicate ZIP receipt files")
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", b"x" * (4 * 1024 * 1024 + 1)),
        ])
        require_api_rejection("independent_ci_artifact_file_too_large", "oversized ZIP receipt member")
        github_api.artifact_archive = b""
        github_api.artifact_content_length = 16 * 1024 * 1024 + 1
        require_api_rejection("independent_ci_artifact_archive_too_large", "oversized GitHub artifact ZIP")
        github_api.artifact_content_length = None
        github_api.artifact_redirect_location = "https://artifacts.attacker.invalid/receipt.zip"
        require_api_rejection("independent_ci_artifact_redirect_invalid", "untrusted GitHub artifact redirect host")
        github_api.artifact_redirect_location = None
        github_api.artifact_archive = zip_fixture([
            ("commercial-migration-ci-receipt.json", artifact_raw),
        ])
        require(file_hash(target_path) == before_preview_hash, "CI trust failures changed receipt target")

        external_receipts_path = tmp / "COMMERCIAL_EVIDENCE_RECEIPTS.json"
        write_json(external_receipts_path, source_receipts)
        external_target = run_promotion(
            repo=repo,
            payload_path=payload_path,
            receipts_path=external_receipts_path,
            env=env,
        )
        require(external_target.returncode != 0, "non-canonical same-name receipt target unexpectedly passed")
        require(
            json.loads(external_target.stdout).get("error_code") == "receipts_path_not_canonical",
            "non-canonical receipt target rejection code mismatch",
        )
        require(file_hash(external_receipts_path) == file_hash(source_path), "non-canonical receipt target changed")

        dirty_path = repo / "untracked-dirty.txt"
        dirty_path.write_text("dirty\n", encoding="utf-8")
        dirty = run_promotion(repo=repo, payload_path=payload_path, receipts_path=target_path, env=env)
        require(dirty.returncode != 0, "dirty worktree promotion unexpectedly passed")
        require(json.loads(dirty.stdout).get("error_code") == "worktree_not_clean", "dirty worktree rejection code mismatch")
        dirty_path.unlink()

        target_path.unlink()
        git(repo, "mv", "fixture.txt", str(target_path.relative_to(repo)))
        renamed_target = run_promotion(repo=repo, payload_path=payload_path, receipts_path=target_path, env=env)
        require(renamed_target.returncode != 0, "renamed receipt target unexpectedly passed")
        require(json.loads(renamed_target.stdout).get("error_code") == "worktree_not_clean", "renamed target rejection code mismatch")
        git(repo, "mv", str(target_path.relative_to(repo)), "fixture.txt")
        git(repo, "reset", "HEAD", "--", "fixture.txt", str(target_path.relative_to(repo)))
        write_json(target_path, source_receipts)

        sensitive_fields = [
            ("raw_prompt", "private prompt"),
            ("raw_response", "private response"),
            ("private_transcript", "private transcript"),
            ("token", "not-a-real-token"),
        ]
        for field, value in sensitive_fields:
            sensitive = copy.deepcopy(payload)
            sensitive[field] = value
            sensitive_path = tmp / f"sensitive-{field}.json"
            write_json(sensitive_path, sensitive)
            rejected = run_promotion(repo=repo, payload_path=sensitive_path, receipts_path=target_path, env=env)
            require(rejected.returncode != 0, f"sensitive field {field} unexpectedly passed")
            rejected_payload = json.loads(rejected.stdout)
            require(rejected_payload.get("error_code") == "sensitive_payload_field_rejected", f"sensitive field {field} rejection mismatch")
            require((rejected_payload.get("safety") or {}).get("raw_payload_echoed") is False, "rejection echoed raw payload")

        forged_runtime_payload = copy.deepcopy(payload)
        forged_runtime_payload["real_runtime_acceptance"]["openclaw_run_id"] = "forged-runtime-id"
        forged_runtime_payload_path = tmp / "forged-runtime-payload.json"
        write_json(forged_runtime_payload_path, forged_runtime_payload)
        require(env.get("GITHUB_TOKEN") == GITHUB_TOKEN and not env.get("GH_TOKEN"), "forged runtime token fixture drifted")
        require(github_api.branch_payload["object"]["sha"] == head, "forged runtime branch fixture drifted")
        require(github_api.run_payload.get("head_sha") == head, "forged runtime run fixture drifted")
        require(github_api.jobs_payload == ci_jobs_fixture(), "forged runtime jobs fixture drifted")
        require(github_api.artifacts_payload == ci_artifacts_fixture(), "forged runtime artifact metadata fixture drifted")
        require(github_api.artifact_redirect_location is None, "forged runtime redirect fixture drifted")
        require(github_api.artifact_content_length is None, "forged runtime archive length fixture drifted")
        require(
            github_api.artifact_archive == zip_fixture([
                ("commercial-migration-ci-receipt.json", artifact_raw),
            ]),
            "forged runtime artifact ZIP fixture drifted",
        )
        forged_runtime_status = run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repo,
        )
        require(forged_runtime_status.returncode == 0, "forged runtime fixture status unavailable")
        require(
            forged_runtime_status.stdout.splitlines() == [" M docs/COMMERCIAL_EVIDENCE_RECEIPTS.json"],
            f"forged runtime fixture has unexpected dirty paths: {forged_runtime_status.stdout.splitlines()}",
        )
        forged_runtime = run_promotion(
            repo=repo,
            payload_path=forged_runtime_payload_path,
            receipts_path=target_path,
            confirm=True,
            env=env,
        )
        require(forged_runtime.returncode != 0, "forged payload runtime IDs unexpectedly passed")
        require(bool(forged_runtime.stdout.strip()), f"forged runtime rejection was not bounded JSON: {forged_runtime.stderr}")
        require(
            json.loads(forged_runtime.stdout).get("error_code") == "real_runtime_acceptance_not_verified",
            f"forged runtime payload rejection mismatch: {forged_runtime.stdout}",
        )

        for mode, expected_code in [
            ("fail", "fixed_runtime_acceptance_failed"),
            ("invalid_json", "fixed_runtime_acceptance_json_invalid"),
            ("replayed_ids", "fixed_runtime_reexecution_not_distinct"),
            ("bad_omission", "fixed_runtime_raw_prompt_omission_missing"),
        ]:
            runtime_env = dict(env)
            runtime_env["FAKE_RUNTIME_MODE"] = mode
            failed_runtime = run_promotion(
                repo=repo,
                payload_path=payload_path,
                receipts_path=target_path,
                confirm=True,
                env=runtime_env,
            )
            require(failed_runtime.returncode != 0, f"runtime mode {mode} unexpectedly passed")
            require(json.loads(failed_runtime.stdout).get("error_code") == expected_code, f"runtime mode {mode} rejection mismatch")
            require(file_hash(target_path) == before_preview_hash, f"runtime mode {mode} changed receipt target")

        runtime_script_path = repo / "scripts" / "local_runtime_acceptance.py"
        runtime_script_original = runtime_script_path.read_text(encoding="utf-8")
        git(repo, "update-index", "--assume-unchanged", "scripts/local_runtime_acceptance.py")
        runtime_script_path.write_text(runtime_script_original + "\n# hidden fixture tamper\n", encoding="utf-8")
        hidden_runtime_tamper = run_promotion(
            repo=repo,
            payload_path=payload_path,
            receipts_path=target_path,
            confirm=True,
            env=env,
        )
        require(hidden_runtime_tamper.returncode != 0, "assume-unchanged runtime script tamper unexpectedly passed")
        require(
            json.loads(hidden_runtime_tamper.stdout).get("error_code") == "critical_head_bytes_mismatch",
            "runtime script HEAD-byte mismatch rejection code mismatch",
        )
        require(file_hash(target_path) == before_preview_hash, "hidden runtime script tamper changed receipt target")
        runtime_script_path.write_text(runtime_script_original, encoding="utf-8")
        git(repo, "update-index", "--no-assume-unchanged", "scripts/local_runtime_acceptance.py")

        github_api.alternate_run_payload = copy.deepcopy(github_api.run_payload)
        github_api.alternate_run_payload["conclusion"] = "failure"
        github_api.run_payload_after_read_count = github_api.run_read_count + 1
        runtime_calls_before_ci_drift = len(runtime_log_path.read_text(encoding="utf-8").splitlines())
        ci_drift = run_promotion(
            repo=repo,
            payload_path=payload_path,
            receipts_path=target_path,
            confirm=True,
            env=env,
        )
        require(ci_drift.returncode != 0, "post-runtime CI drift unexpectedly passed")
        require(
            json.loads(ci_drift.stdout).get("error_code") == "independent_ci_run_not_successful",
            f"post-runtime CI drift rejection mismatch: {ci_drift.stdout}",
        )
        require(file_hash(target_path) == before_preview_hash, "post-runtime CI drift changed receipt target")
        require(
            len(runtime_log_path.read_text(encoding="utf-8").splitlines()) == runtime_calls_before_ci_drift + 1,
            "post-runtime CI drift did not execute the fixed runtime exactly once",
        )
        github_api.alternate_run_payload = None
        github_api.run_payload_after_read_count = None

        for relative_path, expected_code in [
            ("scripts/commercial_release_grade_promotion.py", "promotion_entrypoint_head_mismatch"),
            ("scripts/commercial_release_grade_promotion", "promotion_entrypoint_head_mismatch"),
            ("scripts/agentops", "critical_head_bytes_mismatch"),
            ("agentops_mis_cli/__main__.py", "critical_head_bytes_mismatch"),
        ]:
            hidden_path = repo / relative_path
            hidden_original = hidden_path.read_text(encoding="utf-8")
            git(repo, "update-index", "--assume-unchanged", relative_path)
            hidden_path.write_text(hidden_original + "\n# hidden fixture tamper\n", encoding="utf-8")
            hidden_result = run_promotion(
                repo=repo,
                payload_path=payload_path,
                receipts_path=target_path,
                env=env,
            )
            require(hidden_result.returncode != 0, f"assume-unchanged {relative_path} tamper unexpectedly passed")
            require(json.loads(hidden_result.stdout).get("error_code") == expected_code, f"{relative_path} tamper rejection mismatch")
            require(file_hash(target_path) == before_preview_hash, f"{relative_path} tamper changed receipt target")
            hidden_path.write_text(hidden_original, encoding="utf-8")
            git(repo, "update-index", "--no-assume-unchanged", relative_path)

        fsync_env = dict(env)
        fsync_env["FAKE_DIRECTORY_FSYNC_FAIL"] = "1"
        fsync_result = run_promotion(
            repo=repo,
            payload_path=payload_path,
            receipts_path=target_path,
            confirm=True,
            env=fsync_env,
        )
        require(fsync_result.returncode == 3, f"post-replace fsync uncertainty was not reported as failure: {fsync_result.stdout}{fsync_result.stderr}")
        fsync_payload = json.loads(fsync_result.stdout)
        require(fsync_payload.get("ok") is False, "post-replace fsync uncertainty falsely reported success")
        require(
            fsync_payload.get("status") == "promotion_applied_durability_unverified",
            "post-replace fsync uncertainty status mismatch",
        )
        require((fsync_payload.get("safety") or {}).get("receipts_written") is True, "post-replace fsync warning falsely reported no write")
        require((fsync_payload.get("safety") or {}).get("directory_fsync_verified") is False, "post-replace fsync warning was not surfaced")
        require(
            "receipt_replaced_but_directory_fsync_not_verified" in (fsync_payload.get("warnings") or []),
            "post-replace fsync warning code missing",
        )
        require(file_hash(target_path) != before_preview_hash, "post-replace fsync fixture did not commit receipt")
        write_json(target_path, source_receipts)

        confirmed_api_requests_before = len(github_api.requests)
        confirmed = run_promotion(repo=repo, payload_path=payload_path, receipts_path=target_path, confirm=True, env=env)
        require(confirmed.returncode == 0, f"confirmed promotion failed: {confirmed.stdout}{confirmed.stderr}")
        confirmed_payload = json.loads(confirmed.stdout)
        require(confirmed_payload.get("status") == "promotion_applied", "confirmed promotion status mismatch")
        require(confirmed_payload.get("applied") is True and confirmed_payload.get("changed") is True, "confirmed promotion did not write")
        confirmed_checks = confirmed_payload.get("checks") or {}
        require(confirmed_checks.get("real_runtime_acceptance_independently_verified") is True, "confirm did not independently verify runtime")
        require(confirmed_checks.get("runtime_reexecution_distinct_from_operator_reference") is True, "confirm did not prove a distinct runtime reexecution")
        require(confirmed_checks.get("exact_head_ci_reverified_after_runtime") is True, "confirm did not reverify exact-head CI after runtime")
        require((confirmed_payload.get("safety") or {}).get("live_runtime_executed") is True, "confirm did not execute fixed runtime")
        require((confirmed_payload.get("safety") or {}).get("atomic_replace") is True, "confirmed promotion was not atomic")
        runtime_calls = [json.loads(line) for line in runtime_log_path.read_text(encoding="utf-8").splitlines()]
        require(runtime_calls, "fixed runtime acceptance was not invoked")
        require(runtime_calls[-1].get("hermes_allow_real_run") == "true", "fixed runtime did not enable real Hermes")
        require(runtime_calls[-1].get("agentops_base_url") is None, "fixed runtime inherited AGENTOPS_BASE_URL override")
        require(runtime_calls[-1].get("github_credentials_present") is False, "fixed runtime inherited GitHub credentials")
        require(runtime_calls[-1].get("proxy_environment_present") is False, "fixed runtime inherited proxy routing")
        require(runtime_calls[-1].get("path") == "/usr/bin:/bin", "fixed runtime PATH was not pinned")
        require(runtime_calls[-1].get("python_environment") == [], "fixed runtime inherited Python environment overrides")
        require(runtime_calls[-1].get("python_isolated") == 1, "fixed runtime Python was not isolated")
        require(runtime_calls[-1].get("python_no_user_site") == 1, "fixed runtime Python user site was enabled")
        require(runtime_calls[-1].get("python_no_site") == 1, "fixed runtime Python loaded global sitecustomize")
        require(runtime_calls[-1].get("python_dont_write_bytecode") is True, "fixed runtime Python bytecode writes were enabled")
        require(runtime_calls[-1].get("args") == [
            "--base-url",
            "http://127.0.0.1:8787",
            "--live-openclaw",
            "--live-hermes",
            "--require-hermes-api",
            "--openclaw-timeout",
            "300",
            "--hermes-timeout",
            "600",
            "--request-timeout",
            "720",
        ], "fixed runtime arguments changed")
        confirmed_requests = github_api.requests[confirmed_api_requests_before:]
        confirmed_run_path = f"/repos/geogejoy107-jpg/agentops-mis-mvp/actions/runs/{CI_RUN_ID}"
        confirmed_artifact_path = f"/repos/geogejoy107-jpg/agentops-mis-mvp/actions/artifacts/{GITHUB_ARTIFACT_ID}/zip"
        require(
            sum(item.get("path") == confirmed_run_path for item in confirmed_requests) == 2,
            "confirmed promotion did not read the CI run both before and after runtime",
        )
        require(
            sum(item.get("path") == confirmed_artifact_path for item in confirmed_requests) == 2,
            "confirmed promotion did not revalidate the CI artifact after runtime",
        )
        promoted = json.loads(target_path.read_text(encoding="utf-8"))
        require(source_path.read_text(encoding="utf-8") == json.dumps(source_receipts, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "source receipt fixture changed")
        require(promoted.get("release_complete") is False, "promotion changed release_complete")
        require(promoted.get("commercial_handoff_allowed") is False, "promotion changed commercial_handoff_allowed")
        require(promoted.get("ready_to_merge") is False, "promotion changed ready_to_merge")
        require((promoted.get("receipt_summary") or {}).get("gates_with_release_grade_receipts") == REQUIRED_GATE_IDS, "release-grade summary mismatch")
        require((promoted.get("receipt_summary") or {}).get("clean_worktree_verified") is False, "promoted receipt falsely claimed the worktree remained clean")
        require((promoted.get("receipt_summary") or {}).get("clean_source_head_verified") is True, "promoted receipt omitted source HEAD integrity")
        require((promoted.get("receipt_summary") or {}).get("canonical_receipt_transaction_dirty") is True, "promoted receipt omitted bounded dirty transaction state")
        for item in promoted.get("phase_gate_receipts") or []:
            require(item.get("release_grade_current") is True, f"{item.get('gate_id')} was not promoted")
            require(item.get("local_receipt_current") is True, f"{item.get('gate_id')} local receipt changed")
            original = next(row for row in source_receipts["phase_gate_receipts"] if row["gate_id"] == item["gate_id"])
            require(item.get("commands") == original.get("commands"), f"{item.get('gate_id')} commands changed")

        allowed_prefixes = (
            "/phase_gate_receipts/",
            "/receipt_summary/",
            "/promotion_evidence/",
        )
        actual_changes = changed_paths(source_receipts, promoted)
        require(actual_changes and all(path.startswith(allowed_prefixes) for path in actual_changes), "promotion changed a non-whitelisted receipt path")
        for forbidden in ["release_complete", "commercial_handoff_allowed", "ready_to_merge", "/commands", "/local_receipt_current"]:
            require(not any(forbidden in path for path in actual_changes), f"promotion changed forbidden field {forbidden}")

        promoted_hash = file_hash(target_path)
        repeated_runtime_calls_before = len(runtime_log_path.read_text(encoding="utf-8").splitlines())
        repeated = run_promotion(repo=repo, payload_path=payload_path, receipts_path=target_path, confirm=True, env=env)
        require(repeated.returncode != 0, "repeated dirty promotion receipt unexpectedly self-attested")
        repeated_payload = json.loads(repeated.stdout)
        require(repeated_payload.get("error_code") == "recording_receipt_derivation_mismatch", "repeated promotion rejection mismatch")
        require(file_hash(target_path) == promoted_hash, "repeated rejected promotion changed target evidence")
        repeated_runtime_calls = runtime_log_path.read_text(encoding="utf-8").splitlines()
        require(len(repeated_runtime_calls) == repeated_runtime_calls_before, "repeated rejected promotion reran fixed runtime")

        write_json(target_path, source_receipts)
        concurrent_runtime_calls_before = len(runtime_log_path.read_text(encoding="utf-8").splitlines())
        concurrent_env = dict(env)
        concurrent_env["FAKE_RUNTIME_DELAY"] = "1.0"
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    run_promotion,
                    repo=repo,
                    payload_path=payload_path,
                    receipts_path=target_path,
                    confirm=True,
                    env=concurrent_env,
                )
                for _index in range(2)
            ]
            concurrent_results = [future.result() for future in futures]
        require(sorted(item.returncode for item in concurrent_results) == [0, 2], "concurrent confirmations were not single-winner")
        concurrent_payloads = [json.loads(item.stdout) for item in concurrent_results]
        require(
            sorted(item.get("status") for item in concurrent_payloads)
            == ["promotion_applied", "promotion_rejected"],
            "concurrent confirmations were not one applied plus one fail-closed rejection",
        )
        rejected_concurrent = next(item for item in concurrent_payloads if item.get("status") == "promotion_rejected")
        require(
            rejected_concurrent.get("error_code") == "receipts_changed_before_transaction_lock",
            "concurrent loser rejection code mismatch",
        )
        concurrent_runtime_calls_after = len(runtime_log_path.read_text(encoding="utf-8").splitlines())
        require(
            concurrent_runtime_calls_after == concurrent_runtime_calls_before + 1,
            "concurrent confirmations executed fixed runtime more than once",
        )
        require(
            (next(item for item in concurrent_payloads if item.get("status") == "promotion_applied").get("checks") or {}).get(
                "cross_process_transaction_lock"
            ) is True,
            "concurrent winner omitted transaction-lock evidence",
        )

        (repo / "fixture.txt").write_text("promotion fixture ahead\n", encoding="utf-8")
        git(repo, "add", "fixture.txt")
        git(repo, "commit", "-m", "local ahead fixture")
        unsynced = run_promotion(repo=repo, payload_path=payload_path, receipts_path=target_path, env=env)
        require(unsynced.returncode != 0, "unsynced remote promotion unexpectedly passed")
        require(json.loads(unsynced.stdout).get("error_code") == "remote_sync_not_verified", "remote sync rejection code mismatch")
        require(
            GITHUB_TOKEN not in json.dumps(github_api.requests, sort_keys=True),
            "GitHub token leaked into accumulated API request logs",
        )
        require(
            GITHUB_TOKEN not in runtime_log_path.read_text(encoding="utf-8"),
            "GitHub token leaked into runtime logs",
        )
        github_api.close()

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "preview_did_not_write": True,
        "missing_ci_rejected": True,
        "missing_runtime_rejected": True,
        "github_api_token_required": True,
        "canonical_receipt_target_required": True,
        "renamed_receipt_target_rejected": True,
        "independent_github_branch_verified": True,
        "independent_ci_run_verified": True,
        "independent_ci_jobs_verified": True,
        "independent_ci_artifact_metadata_verified": True,
        "independent_ci_artifact_verified": True,
        "independent_ci_zip_download_verified": True,
        "forged_payload_ci_rejected": True,
        "forged_github_api_run_rejected": True,
        "forged_github_api_jobs_rejected": True,
        "tampered_ci_artifact_rejected": True,
        "forged_ci_artifact_policy_rejected": True,
        "cross_attempt_ci_artifact_rejected": True,
        "unknown_ci_artifact_schema_rejected": True,
        "nested_ci_artifact_schema_rejected": True,
        "prefixed_github_pat_rejected": True,
        "expired_ci_artifact_rejected": True,
        "cross_run_ci_artifact_rejected": True,
        "duplicate_ci_artifact_metadata_rejected": True,
        "zip_traversal_path_rejected": True,
        "zip_duplicate_receipts_rejected": True,
        "zip_oversized_member_rejected": True,
        "zip_oversized_archive_rejected": True,
        "artifact_redirect_host_fail_closed": True,
        "github_api_secret_not_logged": True,
        "post_runtime_ci_drift_rejected": True,
        "dirty_worktree_rejected": True,
        "remote_sync_required": True,
        "exact_origin_branch_upstream_required": True,
        "live_github_branch_head_verified": True,
        "current_head_required": True,
        "stale_payload_rejected": True,
        "stale_runtime_rejected": True,
        "release_bypass_field_rejected": True,
        "confirmed_temporary_copy_written": True,
        "confirm_fixed_runtime_executed": True,
        "prefilled_receipt_cannot_self_attest": True,
        "recording_receipt_derivation_verified": True,
        "clean_source_head_reported_truthfully": True,
        "fixed_git_and_github_api_base_used": True,
        "git_replace_and_grafts_rejected": True,
        "github_api_routing_environment_ignored": True,
        "isolated_outer_launcher_verified": True,
        "global_sitecustomize_disabled": True,
        "isolated_python_runtime_verified": True,
        "isolated_source_cli_bootstrap_verified": True,
        "fixed_runtime_environment_whitelisted": True,
        "runtime_script_matches_head_bytes": True,
        "critical_execution_closure_matches_head_bytes": True,
        "post_replace_fsync_warning_truthful": True,
        "concurrent_confirmation_single_winner": True,
        "forged_payload_runtime_rejected": True,
        "failed_runtime_rejected": True,
        "non_json_runtime_rejected": True,
        "replayed_runtime_ids_rejected": True,
        "runtime_omission_failure_rejected": True,
        "repeated_dirty_confirmation_rejected_before_runtime": True,
        "sensitive_fields_rejected": ["raw_prompt", "raw_response", "private_transcript", "token"],
        "release_authority_fields_unchanged": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
