#!/usr/bin/env python3
"""Verify the read-only operator command-center BFF contract."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(db_path: Path, port: int, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    log_fh = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
        cwd=ROOT,
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._agentops_log_fh = log_fh  # type: ignore[attr-defined]
    return proc


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=8)
    log_fh = getattr(proc, "_agentops_log_fh", None)
    if log_fh:
        log_fh.close()


def wait_for_server(base_url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urlopen(base_url + "/api/agent-gateway/status", timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def http_json(base_url: str, method: str, path: str, payload: dict | None = None, timeout: int = 180) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach MIS server: {exc.reason}") from exc


def run_cli(base_url: str, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def assert_command_center(payload: dict, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-operator", f"wrong provider: {payload}", failures)
    require(payload.get("operation") == "operator_command_center", f"wrong operation: {payload}", failures)
    require((payload.get("safety") or {}).get("read_only") is True, f"command center must be read-only: {payload}", failures)
    require((payload.get("safety") or {}).get("ledger_mutated") is False, f"command center mutated ledger: {payload}", failures)
    require((payload.get("safety") or {}).get("live_execution_performed") is False, f"command center ran live execution: {payload}", failures)
    require("projects" in payload and "blocked_runs" in payload and "approvals" in payload, f"missing core lanes: {payload}", failures)
    require("deliveries" in payload and "workers" in payload and "next_actions" in payload, f"missing operator lanes: {payload}", failures)
    research_consumption = payload.get("research_lab_consumption") or {}
    research_summary = research_consumption.get("summary") or {}
    research_items = research_consumption.get("items") or []
    research_commands = research_consumption.get("commands") or {}
    require(isinstance(research_consumption, dict), f"research consumption lane missing: {payload}", failures)
    require(research_consumption.get("source_operation") == "operator_loop_supervision", f"research consumption must come from loop-supervision: {research_consumption}", failures)
    require((research_consumption.get("safety") or {}).get("read_only") is True, f"research consumption lane must be read-only: {research_consumption}", failures)
    require((research_consumption.get("safety") or {}).get("server_shell_execution") is False, f"research consumption lane cannot execute shell: {research_consumption}", failures)
    require("advance-loop --source research_lab_consumption" in str(research_commands.get("advance_missing") or ""), f"research consumption advance command missing: {research_consumption}", failures)
    require(int(research_summary.get("adapters") or 0) >= 2, f"research consumption summary missing adapters: {research_summary}", failures)
    require(int(research_summary.get("missing") or 0) >= 1, f"isolated command-center should surface missing Research Lab consumption: {research_summary}", failures)
    require(len(research_items) >= 2, f"research consumption items missing: {research_consumption}", failures)
    for item in research_items:
        require(item.get("adapter") in {"hermes", "openclaw"}, f"unexpected research consumption adapter: {item}", failures)
        require(item.get("status") in {"missing", "recorded", "consumed", "partial"}, f"unexpected research consumption status: {item}", failures)
        require(item.get("server_executes_shell") is False, f"research consumption item shell proof missing: {item}", failures)
        if item.get("consumed") is not True:
            require("--confirm-record" in str(item.get("record_command") or ""), f"research consumption record command must be confirm-gated: {item}", failures)
            require("operator loop-supervision" in str(item.get("verify_command") or ""), f"research consumption verify command missing: {item}", failures)
    research_actions = [
        item for item in payload.get("next_actions") or []
        if str(item.get("source") or "").startswith("research_lab_consumption:")
    ]
    require(research_actions, f"research consumption next action missing: {payload.get('next_actions')}", failures)
    for action in research_actions:
        require("operator research-lab-consumption" in str(action.get("command") or ""), f"research action command missing: {action}", failures)
        require("--confirm-record" in str(action.get("command") or ""), f"research action must be confirmation-gated: {action}", failures)
        require(action.get("receipt_required") is True, f"research action receipt_required missing: {action}", failures)
        require(action.get("control_readback_required") is True, f"research action control readback missing: {action}", failures)
        require((action.get("evidence") or {}).get("server_executes_shell") is False, f"research action shell proof missing: {action}", failures)
        require("advance-loop --source research_lab_consumption" in str((action.get("evidence") or {}).get("advance_command") or ""), f"research action advance command missing: {action}", failures)
    require(((payload.get("commander") or {}).get("raw_source_omitted") is True), f"raw source omission missing: {payload}", failures)
    require(((payload.get("commander") or {}).get("raw_patch_omitted") is True), f"raw patch omission missing: {payload}", failures)
    for item in payload.get("next_actions") or []:
        require(bool(item.get("action_id")), f"next action id missing: {item}", failures)
        require(bool(item.get("action_signature")), f"next action signature missing: {item}", failures)
        require(isinstance(item.get("receipt_required"), bool), f"next action receipt_required missing: {item}", failures)
        if item.get("receipt_required"):
            require(item.get("receipt_status") in {"missing", "recorded", "verified", "failed", "skipped", "stale"}, f"next action receipt status missing: {item}", failures)
    service_actions = [
        item for item in payload.get("next_actions") or []
        if item.get("source") == "operator_action_plan:local_service_control"
    ]
    if service_actions:
        service_action = service_actions[0]
        evidence = service_action.get("evidence") or {}
        require("service-control" in str(service_action.get("command") or ""), f"service-control command center action missing command: {service_action}", failures)
        require("service-check" in str(service_action.get("verify_command") or ""), f"service-control command center verify missing: {service_action}", failures)
        require(service_action.get("receipt_status") in {"missing", "recorded", "verified", "stale"}, f"service-control command center receipt status missing: {service_action}", failures)
        require(service_action.get("control_readback_required") is True, f"service-control command center readback flag missing: {service_action}", failures)
        require(evidence.get("service_control_preview") is True, f"service-control command center evidence missing: {service_action}", failures)
        require(evidence.get("server_executes_shell") is False, f"service-control command center server-shell proof missing: {service_action}", failures)
        require(evidence.get("live_execution_performed") is False, f"service-control command center live proof missing: {service_action}", failures)


def main() -> int:
    suffix = stamp()
    project_id = f"proj_command_center_{suffix}"
    plan_id = f"cmdplan_command_center_{suffix}"
    failures: list[str] = []
    transcripts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-command-center-") as tmp:
        tmpdir = Path(tmp)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(tmpdir / "agentops_mis.db", port, tmpdir / "server.log")
        try:
            wait_for_server(base_url)
            initial_status, initial = http_json(base_url, "GET", "/api/operator/command-center?limit=8")
            transcripts.append(json.dumps(initial, ensure_ascii=False))
            require(initial_status == 200, f"initial command center failed: {initial_status} {initial}", failures)
            assert_command_center(initial, failures)

            status, created = http_json(base_url, "POST", "/api/commander/work-packages/plan", {
                "project_id": project_id,
                "plan_id": plan_id,
                "goal": "Verify a unified command-center BFF can guide a Commander coding loop.",
                "max_packages": 1,
                "confirm_create": True,
                "lanes": [{
                    "lane_id": "command-center",
                    "title": "Prove command-center coding evidence gaps",
                    "owner_agent_id": "agt_builder",
                    "priority": "high",
                    "risk_level": "medium",
                    "scope": "operator command center, Commander coding gate, next action routing",
                    "avoid_scope": "do not run live Hermes/OpenClaw or store raw patches",
                    "verification": ["agentops operator command-center --limit 8"],
                }],
            })
            transcripts.append(json.dumps(created, ensure_ascii=False))
            require(status == 201, f"Commander plan create failed: {status} {created}", failures)
            task_id = (created.get("created_task_ids") or [""])[0]
            require(bool(task_id), f"created task id missing: {created}", failures)

            gap_status, gap_payload = http_json(base_url, "GET", f"/api/operator/command-center?project_id={project_id}&limit=8")
            transcripts.append(json.dumps(gap_payload, ensure_ascii=False))
            require(gap_status == 200, f"gap command center failed: {gap_status} {gap_payload}", failures)
            assert_command_center(gap_payload, failures)
            require((gap_payload.get("summary") or {}).get("projects", 0) >= 1, f"project lane missing: {gap_payload}", failures)
            require((gap_payload.get("summary") or {}).get("commander_packages", 0) >= 1, f"commander packages missing: {gap_payload}", failures)
            require((gap_payload.get("summary") or {}).get("commander_coding_evidence_missing", 0) >= 1, f"coding gap not surfaced: {gap_payload}", failures)
            gap_actions = " ".join(item.get("command", "") for item in gap_payload.get("next_actions") or [])
            require("commander dispatch-package" in gap_actions, f"dispatch next action missing before run: {gap_actions}", failures)

            dispatch_status, dispatch = http_json(base_url, "POST", f"/api/commander/work-packages/{task_id}/dispatch", {"adapter": "mock"}, timeout=220)
            transcripts.append(json.dumps(dispatch, ensure_ascii=False))
            run_id = dispatch.get("run_id")
            require(dispatch_status == 201 and run_id, f"dispatch failed: {dispatch_status} {dispatch}", failures)

            after_dispatch_status, after_dispatch = http_json(base_url, "GET", f"/api/operator/command-center?project_id={project_id}&limit=8")
            transcripts.append(json.dumps(after_dispatch, ensure_ascii=False))
            require(after_dispatch_status == 200, f"post-dispatch command center failed: {after_dispatch_status} {after_dispatch}", failures)
            assert_command_center(after_dispatch, failures)
            post_dispatch_actions = " ".join(item.get("command", "") for item in after_dispatch.get("next_actions") or [])
            require("commander coding-evidence" in post_dispatch_actions, f"coding evidence next action missing after run: {post_dispatch_actions}", failures)

            evidence_status, evidence = http_json(base_url, "POST", f"/api/commander/work-packages/{task_id}/coding-evidence", {
                "run_id": run_id,
                "confirm_record": True,
                "patch_summary": "Command-center smoke patch manifest: summary/hash only.",
                "test_summary": "Command-center smoke syntax/diff checks passed.",
                "verifier_summary": "Command-center smoke independent verifier accepted evidence.",
                "merge_summary": "Merge remains gated by human approval and strict release checks.",
                "changed_files": ["server.py", "agentops_mis_cli/agentops.py"],
                "verification_commands": ["python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py", "git diff --check"],
            })
            transcripts.append(json.dumps(evidence, ensure_ascii=False))
            require(evidence_status == 201, f"coding evidence failed: {evidence_status} {evidence}", failures)

            final_status, final_payload = http_json(base_url, "GET", f"/api/operator/command-center?project_id={project_id}&limit=8&refresh_cache=true")
            transcripts.append(json.dumps(final_payload, ensure_ascii=False))
            require(final_status == 200, f"final command center failed: {final_status} {final_payload}", failures)
            assert_command_center(final_payload, failures)
            require((final_payload.get("summary") or {}).get("commander_coding_evidence_recorded", 0) >= 1, f"recorded coding evidence not summarized: {final_payload}", failures)

            cli = run_cli(base_url, ["operator", "command-center", "--project-id", project_id, "--limit", "8"])
            transcripts.extend([cli.stdout, cli.stderr])
            cli_payload = load_json(cli)
            require(cli.returncode == 0, f"CLI command center failed: {cli.stderr or cli.stdout}", failures)
            assert_command_center(cli_payload, failures)
            alias_status, alias_payload = http_json(base_url, "GET", f"/api/command-center/overview?project_id={project_id}&limit=8")
            transcripts.append(json.dumps(alias_payload, ensure_ascii=False))
            require(alias_status == 200, f"alias command center failed: {alias_status} {alias_payload}", failures)
            assert_command_center(alias_payload, failures)
            require(alias_payload.get("alias_operation") == "command_center_overview", f"alias metadata missing: {alias_payload}", failures)
            alias_cli = run_cli(base_url, ["command-center", "overview", "--project-id", project_id, "--limit", "8"])
            transcripts.extend([alias_cli.stdout, alias_cli.stderr])
            alias_cli_payload = load_json(alias_cli)
            require(alias_cli.returncode == 0, f"CLI alias command center failed: {alias_cli.stderr or alias_cli.stdout}", failures)
            assert_command_center(alias_cli_payload, failures)
            require(alias_cli_payload.get("alias_operation") == "command_center_overview", f"CLI alias metadata missing: {alias_cli_payload}", failures)
            require(not leaked_secret("\n".join(transcripts)), "operator command-center output leaked token-like material", failures)
        except Exception as exc:
            failures.append(str(exc))
        finally:
            stop_server(server)

    print(json.dumps({
        "operation": "operator_command_center_smoke",
        "ok": not failures,
        "project_id": project_id,
        "plan_id": plan_id,
        "secret_leaked": leaked_secret("\n".join(transcripts)),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
