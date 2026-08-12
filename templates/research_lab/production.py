"""Fail-closed Research production composition over C0 runtime exports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from . import startup
from .contracts import ResearchError
from .manifest import build_manifest
from .trust import CoreReceiptVerifier, build_production_core_receipt_verifier


_STARTUP_HANDLERS = {
    "workflows": startup.workflow_entrypoint,
    "agents": startup.agent_entrypoint,
    "skills": startup.skill_entrypoint,
    "tools": startup.tool_entrypoint,
    "policies": startup.policy_entrypoint,
    "evaluators": startup.evaluator_entrypoint,
    "ui_extensions": startup.ui_extension_entrypoint,
    "reports": startup.report_entrypoint,
    "api_routes": startup.api_route_entrypoint,
    "cli_commands": startup.cli_command_entrypoint,
    "fixtures": startup.fixture_entrypoint,
    "testing_hooks": startup.testing_hook_entrypoint,
    "exports": startup.export_entrypoint,
    "permissions": startup.permission_entrypoint,
    "migrations": startup.migration_entrypoint,
}


@dataclass(frozen=True)
class ResearchProductionComposition:
    receipt_verifier: CoreReceiptVerifier
    entrypoints: Any
    mount: Mapping[str, Any]


def build_research_production_composition() -> ResearchProductionComposition:
    """Build the production verifier and execute C0's real startup mount."""
    try:
        from template_runtime.sdk import TemplateEntrypointRegistry
    except (ImportError, ModuleNotFoundError) as exc:
        raise ResearchError("research.core_entrypoint_registry_unavailable", "C0 TemplateEntrypointRegistry is unavailable") from exc

    verifier = build_production_core_receipt_verifier()
    registry = TemplateEntrypointRegistry()
    manifest = build_manifest()
    for field, handler in _STARTUP_HANDLERS.items():
        for entrypoint in {str(item["entrypoint"]) for item in manifest[field]}:
            registry.register(entrypoint, field, handler)
    mount = registry.mount_manifest(manifest)
    return ResearchProductionComposition(verifier, registry, mount)
