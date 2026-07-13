#!/usr/bin/env python3
"""Statically verify the Private Host auth workspace shell contract."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_COMPONENTS = ROOT / "ui" / "start-building-app" / "src" / "app" / "components"
AUTH_GATE = UI_COMPONENTS / "auth" / "AuthGate.tsx"
APP_SHELL = UI_COMPONENTS / "layout" / "AppShell.tsx"
SIDEBAR = UI_COMPONENTS / "layout" / "Sidebar.tsx"
TOPBAR = UI_COMPONENTS / "layout" / "Topbar.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"
FILES = (AUTH_GATE, APP_SHELL, SIDEBAR, TOPBAR, LIVE_API)


def load_source(path: Path, failures: list[str]) -> str:
    if not path.is_file():
        failures.append(f"file_exists:{path.name}")
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        failures.append(f"file_readable:{path.name}")
        return ""


def record(checks: dict[str, bool], name: str, condition: bool) -> None:
    checks[name] = bool(condition)


def slice_between(source: str, start: str, end: str) -> str:
    start_index = source.find(start)
    if start_index < 0:
        return ""
    end_index = source.find(end, start_index + len(start))
    if end_index < 0:
        return ""
    return source[start_index:end_index]


def main() -> int:
    failures: list[str] = []
    sources = {path: load_source(path, failures) for path in FILES}
    auth_gate = sources[AUTH_GATE]
    app_shell = sources[APP_SHELL]
    sidebar = sources[SIDEBAR]
    topbar = sources[TOPBAR]
    live_api = sources[LIVE_API]
    checks: dict[str, bool] = {}

    record(checks, "auth_gate_reuses_locked_app_shell", '<AppShell locked lockLabel={lockLabel}>' in auth_gate)
    record(checks, "human_auth_workspace_gate_present", 'data-testid="human-auth-workspace-gate"' in auth_gate)
    record(
        checks,
        "owner_bootstrap_copy_bilingual",
        all(
            marker in auth_gate
            for marker in (
                'zh: isBootstrap ? "\u521d\u59cb\u5316\u672c\u5730\u4e3b\u673a"',
                'en: isBootstrap ? "Initialize local host"',
                'zh: isBootstrap ? "\u521b\u5efa Owner \u5e76\u8fdb\u5165"',
                'en: isBootstrap ? "Create owner and continue"',
            )
        ),
    )
    record(
        checks,
        "owner_login_copy_bilingual",
        all(
            marker in auth_gate
            for marker in (
                ': "\u767b\u5f55 AgentOps MIS"',
                ': "Sign in to AgentOps MIS"',
                ': "\u767b\u5f55\u5de5\u4f5c\u53f0"',
                ': "Enter workspace"',
            )
        ),
    )

    confirm_password = slice_between(
        auth_gate,
        'label={pick(locale, { zh: "\u786e\u8ba4\u5bc6\u7801", en: "Confirm password" })}',
        "                      />",
    )
    record(
        checks,
        "confirm_password_copy_bilingual",
        'zh: "\u786e\u8ba4\u5bc6\u7801", en: "Confirm password"' in confirm_password,
    )
    record(checks, "confirm_password_min_length_12", "minLength={12}" in confirm_password)
    record(
        checks,
        "bootstrap_password_min_length_12",
        "minLength={isBootstrap ? 12 : undefined}" in auth_gate,
    )
    record(
        checks,
        "installer_handoff_hides_setup_code",
        "{isBootstrap && !hasInstallerHandoff && (" in auth_gate,
    )
    record(
        checks,
        "installer_handoff_fragment_scrubbed",
        'params.get("agentops-owner-setup")' in auth_gate and "window.history.replaceState" in auth_gate,
    )
    record(
        checks,
        "setup_code_remains_required_authority",
        "setup_code: string;" in live_api,
    )

    record(checks, "app_shell_accepts_locked", "locked?: boolean;" in app_shell)
    record(checks, "app_shell_locks_sidebar", "<Sidebar locked={locked} />" in app_shell)
    record(
        checks,
        "app_shell_locks_topbar",
        "<Topbar locked={locked} lockLabel={lockLabel} />" in app_shell,
    )

    sidebar_locked_render = slice_between(sidebar, "{locked ? (", ") : (")
    sidebar_unlocked_render = slice_between(sidebar, ") : (\n                          <NavLink", "</NavLink>")
    record(
        checks,
        "locked_sidebar_renders_disabled_item",
        'aria-disabled="true"' in sidebar_locked_render and "<div" in sidebar_locked_render,
    )
    record(checks, "locked_sidebar_item_is_not_link", "NavLink" not in sidebar_locked_render)
    record(checks, "unlocked_sidebar_keeps_navigation", "<NavLink" in sidebar_unlocked_render)

    topbar_persistent_controls = slice_between(topbar, "{/* Right */}", "{/* Notifications */}")
    record(
        checks,
        "locked_topbar_keeps_theme_control",
        "onClick={cycleTheme}" in topbar_persistent_controls
        and "title={copy.switchTheme}" in topbar_persistent_controls,
    )
    record(
        checks,
        "locked_topbar_keeps_language_control",
        'onClick={() => setLocale(locale === "en" ? "zh" : "en")}' in topbar_persistent_controls
        and "title={copy.switchLanguage}" in topbar_persistent_controls,
    )
    logout_control = slice_between(topbar, "{humanAuthRequired && !locked && (", "\n        )}")
    record(checks, "locked_topbar_hides_logout", "logout()" in logout_control and "<LogOut" in logout_control)

    failures.extend(name for name, passed in checks.items() if not passed)
    output = {
        "operation": "private_host_auth_workspace_ui_smoke",
        "ok": not failures,
        "files": [str(path.relative_to(ROOT)) for path in FILES],
        "checks": checks,
        "failure_count": len(failures),
        "failures": failures,
        "safety": {
            "static_only": True,
            "read_only": True,
            "secret_data_inspected": False,
            "secret_data_output": False,
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
