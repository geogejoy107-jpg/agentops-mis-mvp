#!/usr/bin/env python3
"""Smoke-test the Local Coding Project template through API and CLI."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
BASE_URL = os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787")
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def http_json(method: str, path: str, payload: dict | None = None, timeout: int = 120) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(
        BASE_URL.rstrip("/") + path,
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


def run_cli(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env["AGENTOPS_BASE_URL"] = BASE_URL
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
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_local_coding_payload(payload: dict, *, expected_project_id: str | None = None) -> None:
    template = payload.get("template") or {}
    execution = payload.get("template_execution") or {}
    workspace = execution.get("worktree_branch_workspace") or {}
    merge_gate = execution.get("merge_gate") or {}
    packages = payload.get("work_packages") or []
    localization_summary = payload.get("localization_summary") or {}
    safe = payload.get("safe_defaults") or {}

    require(payload.get("ok") is True, f"template run not ok: {payload}")
    require(payload.get("workflow") == "local_coding_project", f"wrong workflow: {payload}")
    require(template.get("template_id") == "tpl_local_coding_project", f"wrong template metadata: {template}")
    require(payload.get("dry_run") is False, f"template should create Commander packages by default: {payload}")
    require(payload.get("created_count") == 4, f"expected four coding work packages: {payload}")
    require(len(packages) == 4, f"missing work packages: {payload}")
    if expected_project_id:
        require(payload.get("project_id") == expected_project_id, f"wrong project id: {payload.get('project_id')}")
    require(execution.get("mode") == "commander_work_packages", f"wrong execution mode: {execution}")
    require(execution.get("live_execution_performed") is False, f"template should not run live runtime: {execution}")
    require(execution.get("patch_test_verifier_required") is True, f"patch/test verifier not required: {execution}")
    require(execution.get("repo_map_localization_required") is True, f"repo-map localization not required: {execution}")
    require(workspace.get("branch_prefix") == "codex/", f"branch prefix missing: {workspace}")
    require(workspace.get("worktree_required_before_merge") is True, f"worktree gate missing: {workspace}")
    require(workspace.get("raw_source_stored") is False, f"raw source should not be stored: {workspace}")
    require(merge_gate.get("requires_clean_tree") is True and merge_gate.get("requires_green_ci") is True, f"merge gate too weak: {merge_gate}")
    require(merge_gate.get("requires_human_approval_before_merge") is True, f"human merge approval missing: {merge_gate}")
    require(any("--require-green-ci" in command for command in merge_gate.get("commands") or []), f"strict release command missing: {merge_gate}")
    require(localization_summary.get("artifacts_recorded") == 4, f"localization artifacts not recorded: {localization_summary}")
    require(localization_summary.get("raw_content_omitted") is True, f"raw content omission proof missing: {localization_summary}")
    require(safe.get("raw_source_stored") is False, f"safe defaults should omit raw source: {safe}")
    require(safe.get("live_execution_performed") is False, f"safe defaults should not run live runtime: {safe}")
    for item in packages:
        localization = item.get("localization_artifact") or {}
        repo_map = item.get("repo_map_localization") or {}
        commands = item.get("verification_commands") or []
        require(localization.get("artifact_type") == "commander_repo_map_localization", f"missing localization artifact: {item}")
        require(str(localization.get("uri") or "").startswith("repo-map://"), f"bad localization URI: {localization}")
        require(repo_map.get("raw_content_omitted") is True and repo_map.get("snippets_omitted") is True, f"repo-map should omit raw content: {repo_map}")
        require(commands, f"coding work package lacks verification commands: {item}")
    joined_commands = "\n".join(command for item in packages for command in (item.get("verification_commands") or []))
    require("git diff --check" in joined_commands, f"patch verifier command missing: {joined_commands}")
    require("release_evidence_packet_smoke.py" in joined_commands, f"release evidence command missing: {joined_commands}")


def assert_coding_evidence_payload(payload: dict, *, expected_task_id: str, expected_run_id: str | None = None) -> None:
    gate = ((payload.get("work_package") or {}).get("coding_evidence_gate") or {})
    safety = payload.get("safety") or {}
    require(payload.get("ok") is True, f"coding evidence not ok: {payload}")
    require(payload.get("operation") == "coding_evidence_record", f"wrong evidence operation: {payload}")
    require(payload.get("task_id") == expected_task_id, f"wrong evidence task: {payload}")
    if expected_run_id:
        require(payload.get("run_id") == expected_run_id, f"wrong evidence run: {payload}")
    require(payload.get("dry_run") is False, f"coding evidence should be recorded: {payload}")
    require(len(payload.get("artifact_ids") or []) == 5, f"expected five coding evidence artifacts: {payload}")
    require((payload.get("evaluation") or {}).get("pass_fail") == "pass", f"coding evidence eval should pass: {payload}")
    require(gate.get("status") == "recorded", f"coding evidence gate not recorded: {gate}")
    require(safety.get("ledger_mutated") is True, f"coding evidence should mutate ledger: {safety}")
    require(safety.get("live_execution_performed") is False, f"coding evidence must not run live runtime: {safety}")
    require(safety.get("raw_source_omitted") is True and safety.get("raw_patch_omitted") is True, f"raw source/patch omission missing: {safety}")


def main() -> int:
    suffix = stamp()
    project_id = f"proj_local_code_template_{suffix}"
    plan_id = f"cmdplan_local_code_template_{suffix}"
    transcripts: list[str] = []
    failures: list[str] = []
    try:
        status, listed = http_json("GET", "/api/workflows/customer-task-templates")
        transcripts.append(json.dumps(listed, ensure_ascii=False))
        require(status == 200, f"template list failed: {status} {listed}")
        templates = listed.get("templates") or []
        template_ids = {item.get("template_id") for item in templates}
        require("tpl_local_coding_project" in template_ids, f"local coding template missing: {template_ids}")
        local_template = next(item for item in templates if item.get("template_id") == "tpl_local_coding_project")
        require((local_template.get("safe_defaults") or {}).get("raw_source_stored") is False, f"template should omit raw source: {local_template}")

        status, api_payload = http_json("POST", "/api/workflows/customer-task-templates/run", {
            "template_id": "tpl_local_coding_project",
            "project_id": project_id,
            "plan_id": plan_id,
            "title": "Local coding project template smoke",
            "description": "Use AgentOps MIS to split a small local code change into safe Commander packages.",
        }, timeout=180)
        transcripts.append(json.dumps(api_payload, ensure_ascii=False))
        require(status == 201, f"template run failed: {status} {api_payload}")
        assert_local_coding_payload(api_payload, expected_project_id=project_id)
        task_ids = api_payload.get("created_task_ids") or [item.get("task_id") for item in api_payload.get("work_packages") or []]
        require(task_ids, f"created task ids missing: {api_payload}")
        api_task_id = task_ids[0]

        dispatch_status, dispatch_payload = http_json("POST", f"/api/commander/work-packages/{api_task_id}/dispatch", {
            "adapter": "mock",
        }, timeout=180)
        transcripts.append(json.dumps(dispatch_payload, ensure_ascii=False))
        require(dispatch_status == 201, f"Commander dispatch failed: {dispatch_status} {dispatch_payload}")
        api_run_id = dispatch_payload.get("run_id")
        require(api_run_id, f"Commander dispatch missing run id: {dispatch_payload}")

        workspace_status, workspace_preview = http_json("POST", f"/api/commander/work-packages/{api_task_id}/coding-workspace", {}, timeout=120)
        transcripts.append(json.dumps(workspace_preview, ensure_ascii=False))
        require(workspace_status == 200 and workspace_preview.get("dry_run") is True, f"coding workspace preview failed: {workspace_status} {workspace_preview}")
        require((workspace_preview.get("safety") or {}).get("worktree_created") is False, f"workspace preview created worktree: {workspace_preview}")
        require((workspace_preview.get("safety") or {}).get("ledger_mutated") is False, f"workspace preview mutated ledger: {workspace_preview}")

        cleanup_status, cleanup_preview = http_json("POST", f"/api/commander/work-packages/{api_task_id}/coding-workspace/cleanup", {}, timeout=120)
        transcripts.append(json.dumps(cleanup_preview, ensure_ascii=False))
        require(cleanup_status == 200 and cleanup_preview.get("dry_run") is True, f"coding workspace cleanup preview failed: {cleanup_status} {cleanup_preview}")
        require((cleanup_preview.get("safety") or {}).get("worktree_removed") is False, f"cleanup preview removed worktree: {cleanup_preview}")

        preview_status, preview_payload = http_json("POST", f"/api/commander/work-packages/{api_task_id}/coding-evidence", {
            "run_id": api_run_id,
            "patch_summary": "Smoke patch manifest: summary/hash only.",
            "test_summary": "Smoke verification: syntax and diff hygiene commands passed.",
            "verifier_summary": "Smoke independent verifier accepted the evidence packet.",
            "changed_files": ["server.py", "agentops_mis_cli/agentops.py"],
            "verification_commands": ["python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py", "git diff --check"],
        }, timeout=120)
        transcripts.append(json.dumps(preview_payload, ensure_ascii=False))
        require(preview_status == 200 and preview_payload.get("dry_run") is True, f"coding evidence preview should be dry-run: {preview_status} {preview_payload}")
        require((preview_payload.get("safety") or {}).get("ledger_mutated") is False, f"preview mutated ledger: {preview_payload}")

        evidence_status, evidence_payload = http_json("POST", f"/api/commander/work-packages/{api_task_id}/coding-evidence", {
            "run_id": api_run_id,
            "confirm_record": True,
            "patch_summary": "Smoke patch manifest: summary/hash only.",
            "test_summary": "Smoke verification: syntax and diff hygiene commands passed.",
            "verifier_summary": "Smoke independent verifier accepted the evidence packet.",
            "merge_summary": "Merge remains gated by human approval plus strict release checks.",
            "changed_files": ["server.py", "agentops_mis_cli/agentops.py", "scripts/local_coding_project_template_smoke.py"],
            "verification_commands": ["python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py", "git diff --check"],
        }, timeout=120)
        transcripts.append(json.dumps(evidence_payload, ensure_ascii=False))
        require(evidence_status == 201, f"coding evidence record failed: {evidence_status} {evidence_payload}")
        assert_coding_evidence_payload(evidence_payload, expected_task_id=api_task_id, expected_run_id=api_run_id)

        read_status, readback = http_json("GET", f"/api/commander/work-packages?project_id={project_id}&limit=10")
        transcripts.append(json.dumps(readback, ensure_ascii=False))
        require(read_status == 200, f"Commander readback failed: {read_status} {readback}")
        require((readback.get("summary") or {}).get("total") == 4, f"wrong readback total: {readback}")
        require((readback.get("summary", {}).get("localization") or {}).get("coverage_percent") == 100.0, f"localization coverage wrong: {readback}")
        readback_packages = {item.get("task_id"): item for item in readback.get("work_packages") or []}
        first_readback = readback_packages.get(api_task_id) or {}
        require((first_readback.get("coding_evidence_gate") or {}).get("status") == "recorded", f"readback coding evidence gate missing: {first_readback}")
        require((first_readback.get("evidence_counts") or {}).get("artifacts", 0) >= 5, f"coding evidence artifacts not counted: {first_readback}")

        cli = run_cli([
            "workflow",
            "run-template",
            "--template-id",
            "tpl_local_coding_project",
            "--title",
            "Local coding project template CLI smoke",
            "--description",
            "Create a CLI-driven coding project plan with Commander work packages.",
        ], timeout=180)
        transcripts.extend([cli.stdout, cli.stderr])
        cli_payload = load_json(cli)
        require(cli.returncode == 0, f"CLI template run failed: {cli.stderr or cli.stdout}")
        assert_local_coding_payload(cli_payload)
        cli_task_ids = cli_payload.get("created_task_ids") or [item.get("task_id") for item in cli_payload.get("work_packages") or []]
        require(cli_task_ids, f"CLI template did not create task ids: {cli_payload}")
        cli_task_id = cli_task_ids[0]

        cli_workspace = run_cli(["commander", "coding-workspace", "--task-id", cli_task_id], timeout=120)
        transcripts.extend([cli_workspace.stdout, cli_workspace.stderr])
        cli_workspace_payload = load_json(cli_workspace)
        require(cli_workspace.returncode == 0, f"CLI coding workspace preview failed: {cli_workspace.stderr or cli_workspace.stdout}")
        require(cli_workspace_payload.get("dry_run") is True and (cli_workspace_payload.get("safety") or {}).get("worktree_created") is False, f"CLI workspace preview should not create worktree: {cli_workspace_payload}")

        cli_dispatch = run_cli(["commander", "dispatch-package", "--task-id", cli_task_id, "--adapter", "mock"], timeout=180)
        transcripts.extend([cli_dispatch.stdout, cli_dispatch.stderr])
        cli_dispatch_payload = load_json(cli_dispatch)
        require(cli_dispatch.returncode == 0, f"CLI commander dispatch failed: {cli_dispatch.stderr or cli_dispatch.stdout}")
        cli_run_id = cli_dispatch_payload.get("run_id")
        require(cli_run_id, f"CLI commander dispatch missing run id: {cli_dispatch_payload}")

        cli_evidence = run_cli([
            "commander",
            "coding-evidence",
            "--task-id",
            cli_task_id,
            "--run-id",
            cli_run_id,
            "--changed-file",
            "server.py",
            "--changed-file",
            "agentops_mis_cli/agentops.py",
            "--verification-command",
            "git diff --check",
            "--verification-command",
            "python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py",
            "--confirm-record",
        ], timeout=120)
        transcripts.extend([cli_evidence.stdout, cli_evidence.stderr])
        cli_evidence_payload = load_json(cli_evidence)
        require(cli_evidence.returncode == 0, f"CLI coding evidence failed: {cli_evidence.stderr or cli_evidence.stdout}")
        assert_coding_evidence_payload(cli_evidence_payload, expected_task_id=cli_task_id, expected_run_id=cli_run_id)

        require(not leaked_secret("\n".join(transcripts)), "local coding template output leaked token-like material")
    except Exception as exc:
        failures.append(str(exc))

    output = {
        "ok": not failures,
        "project_id": project_id,
        "plan_id": plan_id,
        "template_id": "tpl_local_coding_project",
        "secret_leaked": leaked_secret("\n".join(transcripts)),
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
