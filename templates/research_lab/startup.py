"""Trusted process-startup entrypoints for the Research template.

These functions are bound by production code to C0's
``TemplateEntrypointRegistry``.  Manifest strings are therefore declarations,
not dynamic-import instructions.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import canonical_hash


def _mounted(kind: str, action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]:
    if action != "mount":
        raise ValueError(f"{kind} startup entrypoint only accepts mount")
    return {"mounted": True, "kind": kind, "declaration_id": declaration.get("id")}


def workflow_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("workflows", action, declaration)
def agent_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("agents", action, declaration)
def skill_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("skills", action, declaration)
def tool_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("tools", action, declaration)
def policy_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("policies", action, declaration)
def evaluator_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("evaluators", action, declaration)
def ui_extension_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("ui_extensions", action, declaration)
def report_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("reports", action, declaration)
def api_route_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("api_routes", action, declaration)
def cli_command_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("cli_commands", action, declaration)
def fixture_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("fixtures", action, declaration)
def testing_hook_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("testing_hooks", action, declaration)
def export_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("exports", action, declaration)
def permission_entrypoint(action: str, declaration: Mapping[str, Any]) -> Mapping[str, Any]: return _mounted("permissions", action, declaration)


def migration_entrypoint(action: str, context: Mapping[str, Any]) -> Mapping[str, Any]:
    declaration = context if action == "mount" else context.get("declaration", {})
    if action == "mount":
        return _mounted("migrations", action, declaration)
    if action not in {"forward", "reverse"}:
        raise ValueError("migration startup entrypoint action is invalid")
    evidence = {
        "migration_id": declaration.get("id"),
        "checksum": declaration.get("checksum"),
        "direction": action,
        "applied": True,
    }
    return {**evidence, "readback_hash": canonical_hash({**evidence, "context": dict(context)})}
