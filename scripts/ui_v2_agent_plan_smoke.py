#!/usr/bin/env python3
"""Verify the bounded UI v2 implementation plan against an isolated MIS server."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def run(args: list[str], base_url: str, agent_id: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_AGENT_ID"] = agent_id
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def payload(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    base_url = os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787")
    suffix = stamp()
    agent_id = f"agt_ui_v2_{suffix}"
    task_id = f"tsk_ui_v2_{suffix}"

    index = run(["knowledge", "index", "--rebuild"], base_url, agent_id)
    require(index.returncode == 0, index.stderr or index.stdout)

    registered = run([
        "agent", "register", "--id", agent_id,
        "--name", "UI v2 Implementer",
        "--role", "Frontend implementation agent",
        "--runtime", "codex",
        "--permission-level", "standard",
        "--allowed-tools", "github.read,github.write,ui.build,ui.browser_smoke",
        "--description", "Implements an isolated Draft UI branch without changing backend governance semantics.",
    ], base_url, agent_id)
    require(registered.returncode == 0, registered.stderr or registered.stdout)

    task = run([
        "task", "create", "--task-id", task_id,
        "--title", "AgentOps MIS UI v2 Phase 0 and Mission Control",
        "--description", "Implement the reviewed UI v2 foundation and attention-first Mission Control on a Draft branch.",
        "--owner-agent-id", agent_id,
        "--requester-id", "usr_founder",
        "--acceptance", "Build passes; legacy routes remain; live data and honest error states are used; responsive screenshots are produced.",
        "--risk", "medium",
    ], base_url, agent_id)
    require(task.returncode == 0, task.stderr or task.stdout)

    plan = run([
        "agent-plan", "create",
        "--agent-id", agent_id,
        "--task-id", task_id,
        "--task-understanding", "Implement semantic tokens, AppShellV2, purpose navigation, context bar, command palette, shared feedback components and live Mission Control. Preserve backend execution, authentication, approval, worker, runtime, audit and redaction semantics. Replace the old hard-coded Workspace pixel preview with the real compact PixelOperatingMap.",
        "--referenced-specs", "docs/project/PROJECT_STATE.md,docs/project/DECISIONS.md,docs/project/BACKLOG.md,docs/project/HANDOFF.md,AGENTS.md,PROJECT_SPEC.md,AGENT_WORKFLOW.md,BASE_INDEX.md,docs/design/UI_BENCHMARK_RESEARCH_2026.md,docs/design/AGENTOPS_MIS_UI_UX_SPEC_V2.md,docs/design/GEMINI_UI_IMPLEMENTATION_HANDOFF.md",
        "--referenced-memories", "T-UI-20260621-01",
        "--referenced-bases", "base_local_tasks,base_local_memory,base_local_templates",
        "--proposed-files-to-change", "ui/start-building-app/src/styles/theme.css,ui/start-building-app/src/app/App.tsx,ui/start-building-app/src/app/shell,ui/start-building-app/src/app/design-system,ui/start-building-app/src/app/modules/mission-control,ui/start-building-app/src/app/components/pages/WorkspaceHome.tsx,.github/workflows/ui-v2-validation.yml",
        "--risk", "medium",
        "--execution-steps", "READ,PLAN,RETRIEVE,COMPARE,IMPLEMENT_TOKENS,IMPLEMENT_SHELL,IMPLEMENT_MISSION_CONTROL,INTEGRATE_PIXEL_PREVIEW,VERIFY,RECORD",
        "--verification-plan", "Run npm ci and npm run build; validate legacy and v2 routes, locale/theme, keyboard focus, reduced motion, backend-unavailable state and 1440x900, 1024x768 and 390x844 screenshots.",
        "--rollback-plan", "Disable VITE_UI_V2, restore the legacy AppShell and WorkspaceHome composition, and remove the new UI modules without backend changes.",
        "--status", "submitted",
    ], base_url, agent_id)
    plan_data = payload(plan)
    plan_id = (plan_data.get("agent_plan") or {}).get("plan_id")
    require(plan.returncode == 0, plan.stderr or plan.stdout)
    require(bool(plan_id), f"plan_id missing: {plan_data}")

    verified = run(["agent-plan", "verify", "--plan-id", str(plan_id)], base_url, agent_id)
    verified_data = payload(verified)
    verification = verified_data.get("verification") or {}
    require(verified.returncode == 0, verified.stderr or verified.stdout)
    require(verification.get("pass") is True, f"plan verification failed: {verified_data}")

    print(json.dumps({
        "ok": True,
        "task_id": task_id,
        "agent_id": agent_id,
        "plan_id": plan_id,
        "plan_verified": True,
        "risk_level": "medium",
        "approval_required": False,
        "live_execution_performed": False,
        "token_omitted": True,
        "verification": verification,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
