#!/usr/bin/env python3
"""Smoke-test project-scoped Commander Team Board readback."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
BASE_URL = os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787")
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def http_json(method: str, path: str, payload: dict | None = None, query: dict | None = None, timeout: int = 120) -> tuple[int, dict]:
    url = BASE_URL.rstrip("/") + path
    if query:
        url += "?" + urlencode({key: value for key, value in query.items() if value is not None}, doseq=True)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, headers={"Content-Type": "application/json", "Accept": "application/json"}, method=method)
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


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env["AGENTOPS_BASE_URL"] = BASE_URL
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def validate_board(payload: dict, project_id: str, plan_id: str, created_task_ids: list[str], failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-commander", f"wrong provider: {payload}", failures)
    require(payload.get("operation") == "project_board", f"wrong operation: {payload}", failures)
    require(payload.get("live_execution_performed") is False, f"board should not execute live runtime: {payload}", failures)
    require(payload.get("token_omitted") is True, f"token omission proof missing: {payload}", failures)
    team_board = payload.get("team_board") or {}
    require(team_board.get("project_id") == project_id, f"team board project filter missing: {team_board}", failures)
    require(team_board.get("plan_id") == plan_id, f"team board plan filter missing: {team_board}", failures)
    require((team_board.get("safety") or {}).get("read_only") is True, f"team board should be read-only: {team_board}", failures)
    require(team_board.get("live_execution_performed") is False, f"team board should not execute live work: {team_board}", failures)
    lanes = team_board.get("lanes") or []
    lane_ids = {lane.get("task_id") for lane in lanes}
    require(len(lanes) == len(created_task_ids), f"team board should include scoped lanes only: {team_board}", failures)
    require(set(created_task_ids).issubset(lane_ids), f"team board missing created lanes: {team_board}", failures)
    require((team_board.get("summary") or {}).get("total_lanes") == len(created_task_ids), f"team board total lanes wrong: {team_board}", failures)
    require((team_board.get("summary") or {}).get("missing_coding_evidence", 0) >= 1, f"missing coding evidence should be visible: {team_board}", failures)
    require(team_board.get("dependency_edges"), f"dependency edges missing: {team_board}", failures)
    require(any((lane.get("localization_gate") or {}).get("status") == "recorded" for lane in lanes), f"localization gate missing: {team_board}", failures)
    require(any(lane.get("package_status") == "ready_for_review" for lane in lanes), f"dispatched mock lane should become ready_for_review: {team_board}", failures)
    require(team_board.get("next_actions"), f"team board next actions missing: {team_board}", failures)
    filter_block = payload.get("team_board_filter") or {}
    require(filter_block.get("applied") is True, f"team board filter not applied: {filter_block}", failures)


def main() -> int:
    suffix = stamp()
    project_id = f"proj_team_board_smoke_{suffix}"
    plan_id = f"cmdplan_team_board_smoke_{suffix}"
    goal = "Use AgentOps MIS as a project manager for a small AI team and show project-scoped lane status."
    transcripts: list[str] = []
    failures: list[str] = []

    try:
        status, created = http_json("POST", "/api/commander/work-packages/plan", {
            "project_id": project_id,
            "plan_id": plan_id,
            "goal": goal,
            "max_packages": 4,
            "confirm_create": True,
        }, timeout=180)
        transcripts.append(json.dumps(created, ensure_ascii=False))
        require(status in {200, 201}, f"plan create failed: {status} {created}", failures)
        require(created.get("status") == "created", f"plan not created: {created}", failures)
        created_task_ids = created.get("created_task_ids") or []
        require(len(created_task_ids) == 4, f"expected 4 created work packages: {created}", failures)

        for task_id in created_task_ids[:2]:
            dispatch_status, dispatch = http_json("POST", f"/api/commander/work-packages/{task_id}/dispatch", {"adapter": "mock"}, timeout=240)
            transcripts.append(json.dumps(dispatch, ensure_ascii=False))
            require(dispatch_status in {200, 201}, f"dispatch failed for {task_id}: {dispatch_status} {dispatch}", failures)
            require((dispatch.get("after") or dispatch).get("task_id") or dispatch.get("task_id"), f"dispatch response missing task id: {dispatch}", failures)

        board_status, board = http_json("GET", "/api/commander/project-board", query={"project_id": project_id, "plan_id": plan_id, "limit": 10}, timeout=60)
        transcripts.append(json.dumps(board, ensure_ascii=False))
        require(board_status == 200, f"project board failed: {board_status} {board}", failures)
        validate_board(board, project_id, plan_id, created_task_ids, failures)

        cli = run_cli(["commander", "board", "--project-id", project_id, "--plan-id", plan_id, "--limit", "10"])
        transcripts.extend([cli.stdout, cli.stderr])
        cli_payload = load_json(cli)
        require(cli.returncode == 0, f"CLI board failed: {cli.stderr or cli.stdout}", failures)
        validate_board(cli_payload, project_id, plan_id, created_task_ids, failures)

        joined = "\n".join(transcripts)
        require(not leaked_secret(joined), "team board smoke leaked token-like material", failures)

        result = {
            "ok": not failures,
            "operation": "commander_team_board_smoke",
            "project_id": project_id,
            "plan_id": plan_id,
            "created_task_ids": created_task_ids,
            "team_board_status": (board.get("team_board") or {}).get("status") if isinstance(board, dict) else None,
            "failures": failures,
            "safety": {
                "live_execution_performed": False,
                "token_omitted": True,
                "raw_source_omitted": True,
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not failures else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
