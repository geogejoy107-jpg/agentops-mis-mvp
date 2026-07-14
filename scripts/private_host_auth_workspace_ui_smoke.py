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
ACCOUNT_SECURITY = UI_COMPONENTS / "pages" / "AccountSecurity.tsx"
WORKSPACE_SETTINGS = UI_COMPONENTS / "shared" / "WorkspaceSettings.tsx"
PREFERENCES = ROOT / "ui" / "start-building-app" / "src" / "app" / "context" / "PreferencesContext.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"
FILES = (AUTH_GATE, APP_SHELL, SIDEBAR, TOPBAR, ACCOUNT_SECURITY, WORKSPACE_SETTINGS, PREFERENCES, LIVE_API)


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
    account_security = sources[ACCOUNT_SECURITY]
    workspace_settings = sources[WORKSPACE_SETTINGS]
    preferences = sources[PREFERENCES]
    live_api = sources[LIVE_API]
    checks: dict[str, bool] = {}

    record(checks, "auth_gate_reuses_locked_app_shell", '<AppShell locked lockLabel={lockLabel}>' in auth_gate)
    record(checks, "human_auth_workspace_gate_present", 'testId="human-auth-workspace-gate"' in auth_gate)
    record(checks, "auth_gate_uses_workspace_settings_layout", 'testId="human-auth-settings-layout"' in auth_gate)
    record(checks, "auth_gate_uses_workspace_access_panel", 'data-testid="human-auth-access-panel"' in auth_gate)
    record(checks, "auth_gate_uses_workspace_form", 'data-testid="human-auth-workspace-form"' in auth_gate)
    record(checks, "auth_gate_uses_compact_host_boundary", 'data-testid="human-auth-host-boundary"' in auth_gate)
    record(checks, "auth_gate_has_no_standalone_status_panel", 'data-testid="human-auth-host-boundary-panel"' not in auth_gate)
    record(
        checks,
        "auth_gate_has_no_standalone_card_shell",
        'className="overflow-hidden rounded-lg"' not in auth_gate,
    )
    record(
        checks,
        "auth_gate_uses_existing_settings_grid",
        'lg:grid-cols-[220px_minmax(0,680px)]' in workspace_settings,
    )
    record(
        checks,
        "auth_and_account_share_workspace_settings_components",
        "WorkspaceSettingsPage" in auth_gate
        and "WorkspaceSettingsSection" in auth_gate
        and "WorkspaceSettingsPage" in account_security
        and "WorkspaceSettingsSection" in account_security,
    )
    record(
        checks,
        "account_route_is_visible_in_existing_sidebar",
        'path: "/workspace/account"' in sidebar
        and 'account: "Account and access"' in sidebar
        and 'account: "账户与访问"' in sidebar,
    )
    record(
        checks,
        "locked_sidebar_marks_account_as_current",
        'item.path === "/workspace/account"' in sidebar
        and 'aria-current={isActive ? "page" : undefined}' in sidebar,
    )
    locked_sidebar_footer = slice_between(sidebar, "{locked ? (\n          <>", "\n        ) : (")
    record(
        checks,
        "locked_sidebar_omits_demo_identity",
        "copy.productMode" in locked_sidebar_footer
        and "copy.account" in locked_sidebar_footer
        and "jiwu@agentops.dev" not in locked_sidebar_footer,
    )
    record(
        checks,
        "authenticated_shell_uses_real_account_identity",
        "useHumanAuth" in sidebar
        and "user?.workspace_id" in sidebar
        and "user?.display_name" in sidebar
        and "user?.username" in sidebar,
    )
    record(
        checks,
        "mobile_topbar_keeps_product_identity",
        "md:hidden" in topbar and "AgentOps MIS" in topbar and "<Zap" in topbar,
    )
    record(
        checks,
        "fresh_install_defaults_to_enterprise_theme",
        'if (stored === "dark" || stored === "ops") return "ops";' in preferences
        and 'if (stored === "workforce") return "workforce";' in preferences
        and 'return "enterprise";' in preferences,
    )
    record(checks, "locked_shell_uses_workspace_content_spacing", 'className="app-main flex-1 overflow-y-auto p-4 lg:p-5"' in app_shell)
    record(
        checks,
        "auth_form_uses_compact_workspace_rows",
        'grid gap-1.5 py-3 text-xs sm:grid-cols-[160px_minmax(0,1fr)]' in auth_gate
        and 'background: "var(--mis-surface)"' in auth_gate,
    )
    record(
        checks,
        "auth_gate_uses_single_lock_status",
        "status={(" not in auth_gate
        and "<Topbar locked={locked} lockLabel={lockLabel} />" in app_shell,
    )
    record(
        checks,
        "owner_bootstrap_copy_bilingual",
        all(
            marker in auth_gate
            for marker in (
                'zh: isBootstrap ? "\u9996\u4f4d\u6240\u6709\u8005"',
                'en: isBootstrap ? "First owner"',
                'zh: isBootstrap ? "\u521b\u5efa\u6240\u6709\u8005\u5e76\u8fdb\u5165"',
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
                ': "\u5de5\u4f5c\u533a\u767b\u5f55"',
                ': "Workspace sign-in"',
                ': "\u767b\u5f55\u5de5\u4f5c\u53f0"',
                ': "Enter workspace"',
            )
        ),
    )

    confirm_password = slice_between(
        auth_gate,
        'label={pick(locale, { zh: "\u786e\u8ba4\u5bc6\u7801", en: "Confirm password" })}',
        "                    )}",
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
        "bootstrap_password_live_validation",
        all(
            marker in auth_gate
            for marker in (
                "const passwordReady = password.length >= 12;",
                "const passwordsMatch = confirmPassword.length > 0 && password === confirmPassword;",
                "const bootstrapFormReady = Boolean(setupCode.trim()) && usernameReady && passwordReady && passwordsMatch;",
                "disabled={submitting || (isBootstrap && !bootstrapFormReady)}",
            )
        ),
    )
    record(
        checks,
        "bootstrap_password_guidance_bilingual",
        all(
            marker in auth_gate
            for marker in (
                'zh: "已满足 12 个字符", en: "12-character minimum met"',
                'zh: "两次输入一致", en: "Passwords match"',
                'zh: "两次输入不一致", en: "Passwords do not match"',
            )
        ),
    )
    record(
        checks,
        "password_visibility_controls_are_accessible_icons",
        "Eye," in auth_gate
        and "EyeOff," in auth_gate
        and "aria-label={revealControl.label}" in auth_gate
        and "aria-pressed={revealControl.visible}" in auth_gate
        and 'type="button"' in auth_gate
        and "togglePasswordLabel" in auth_gate
        and "toggleConfirmPasswordLabel" in auth_gate,
    )
    record(
        checks,
        "password_visibility_resets_across_auth_boundaries",
        auth_gate.count("setShowPassword(false);") >= 3
        and auth_gate.count("setShowConfirmPassword(false);") >= 3,
    )
    record(
        checks,
        "auth_fields_keep_explicit_label_binding",
        "const inputId = useId();" in auth_gate
        and "<label htmlFor={inputId}" in auth_gate
        and "id={inputId}" in auth_gate,
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

    sidebar_locked_render = slice_between(sidebar, "{locked ? (\n          <div>", ") : navGroups.map")
    sidebar_unlocked_render = slice_between(sidebar, ") : (\n                          <NavLink", "</NavLink>")
    record(
        checks,
        "locked_sidebar_renders_single_current_item",
        'aria-current="page"' in sidebar_locked_render
        and "copy.setupGroup" in sidebar_locked_render
        and "copy.account" in sidebar_locked_render,
    )
    record(checks, "locked_sidebar_item_is_not_link", "NavLink" not in sidebar_locked_render)
    record(
        checks,
        "locked_sidebar_omits_disabled_menu_wall",
        "navGroups.map" not in sidebar_locked_render
        and 'aria-disabled="true"' not in sidebar_locked_render,
    )
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
    record(
        checks,
        "locked_topbar_hides_placeholder_avatar",
        ") : !locked ? (" in topbar
        and "title={displayName}" in topbar,
    )
    record(
        checks,
        "locked_topbar_uses_private_host_workspace",
        "const workspaceName = locked ? copy.privateHost" in topbar
        and "{workspaceName}" in topbar,
    )
    record(
        checks,
        "locked_topbar_omits_fake_search",
        "{locked ? (\n        <div className=\"hidden flex-1 md:block\" />" in topbar
        and "searchLocked" not in topbar,
    )

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
