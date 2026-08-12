"""Machine-readable Research Lab Template v1 manifest builder."""

from __future__ import annotations

from typing import Any

from template_runtime.contracts import manifest_content_sha256, validate_template_manifest

from .migrations import migration_checksum
from .api import route_contracts
from .ui import extension_pages


def register_with_sdk(sdk: Any) -> None:
    """Register every concrete declaration through the frozen TemplateSDKPort."""
    manifest = build_manifest()
    routes = {
        "domain_objects": "register_domain_repository", "workflows": "register_workflow", "agents": "register_agent_team",
        "skills": "register_skill", "tools": "register_tool", "policies": "register_policy", "evaluators": "register_evaluator",
        "ui_extensions": "register_ui_extension", "reports": "register_report", "api_routes": "register_api_route",
        "cli_commands": "register_cli_command", "fixtures": "register_fixture",
        "testing_hooks": "register_testing_hook", "exports": "register_exporter",
    }
    for section, method in routes.items():
        registrar = getattr(sdk, method)
        if section == "api_routes":
            for index, route in enumerate(route_contracts()):
                registrar(_decl(f"api.route_{index + 1:02d}", "templates.research_lab.api:ResearchAPI.dispatch", contract_version="template-platform-api/v1", **dict(route)))
        else:
            for declaration in manifest[section]:
                registrar(declaration)
    sdk.register_memory_policy({"template_id": "research_lab", **manifest["memory"]})


def _decl(suffix: str, entrypoint: str, **extra: Any) -> dict[str, Any]:
    return {"id": f"research_lab.{suffix}", "version": "1.0.0", "contract_version": "template-sdk/v1", "entrypoint": entrypoint, **extra}


def build_manifest() -> dict[str, Any]:
    domain_names = (
        "ResearchProject", "ResearchContract", "ResearchQuestion", "LiteratureEvidence",
        "Experiment", "ProtocolVersion", "Trial", "JobAttempt", "ComputeTarget",
        "Checkpoint", "MetricSnapshot", "ResearchArtifact", "ResearchClaim",
        "ClaimEvidence", "Manuscript", "ResearchReceipt",
    )
    manifest: dict[str, Any] = {
        "schema_version": "template-manifest/v1",
        "id": "research_lab",
        "name": "Research Lab",
        "version": "1.0.0",
        "category": "research",
        "description": "Governed literature-to-experiment-to-evidence research production line backed exclusively by MIS Core authority.",
        "publisher": "agentops-mis",
        "license": "Proprietary",
        "min_mis_version": "1.6.0",
        "runtime_dependencies": [
            {"id": "openjiuwen-runtime", "kind": "runtime", "version": "==0.1.16", "optional": False},
            {"id": "pytorch", "kind": "python", "version": ">=2.6.0,<3.0.0", "optional": True},
            {"id": "openssh", "kind": "service", "version": ">=9.0.0,<10.0.0", "optional": True},
            {"id": "slurm", "kind": "service", "version": ">=23.0.0,<26.0.0", "optional": True},
        ],
        "capabilities": [
            "research.literature", "research.protocol", "research.local_execution",
            "research.ssh_execution", "research.slurm_execution", "research.checkpoint",
            "research.claim_gate", "research.manuscript", "research.reproducibility",
        ],
        "domain_objects": [],
        "workflows": [_decl("workflow.production", "templates.research_lab.runtime_team")],
        "agents": [_decl(f"agent.{role}", "templates.research_lab.runtime_team") for role in (
            "research_lead", "literature_researcher", "protocol_planner", "experiment_planner", "training_operator", "failure_diagnoser", "metrics_analyst", "evidence_reviewer", "paper_writer", "memory_curator"
        )],
        "skills": [
            _decl("skill.literature_verify", "templates.research_lab.literature:verify_citation_claims"),
            _decl("skill.protocol_freeze", "templates.research_lab.service"),
            _decl("skill.claim_gate", "templates.research_lab.evidence:evaluate_claim"),
            _decl("skill.reproducibility_export", "templates.research_lab.exports:reproducibility_bundle"),
        ],
        "tools": [
            _decl("tool.deep_search", "templates.research_lab.literature:normalize_source_url", risk="medium", side_effect="external_write", approval="always"),
            _decl("tool.local_execute", "templates.research_lab.executors", risk="high", side_effect="internal_write", approval="policy"),
            _decl("tool.ssh_execute", "templates.research_lab.executors", risk="critical", side_effect="external_write", approval="always"),
            _decl("tool.slurm_execute", "templates.research_lab.executors", risk="critical", side_effect="external_write", approval="always"),
        ],
        "policies": [
            _decl("policy.read_only", "templates.research_lab.runtime_team"),
            _decl("policy.deep_search", "templates.research_lab.runtime_team"),
            _decl("policy.no_external_write", "templates.research_lab.runtime_team"),
            _decl("policy.compute", "templates.research_lab.budgets"),
            _decl("policy.diagnostics", "templates.research_lab.runtime_team"),
            _decl("policy.memory_candidate", "templates.research_lab.runtime_team"),
            _decl("policy.claim_gate", "templates.research_lab.evidence:evaluate_claim"),
        ],
        "evaluators": [
            _decl("evaluator.claim_integrity", "templates.research_lab.evidence:evaluate_claim"),
            _decl("evaluator.citation_integrity", "templates.research_lab.literature:verify_citation_claims"),
            _decl("evaluator.migration_readback", "templates.research_lab.migrations:verify_migration"),
        ],
        "memory": {"candidate_only": True, "source_refs_required": True, "shared_memory": "deny_by_default", "conflict_policy": "stale_or_superseded"},
        "ui_extensions": [_decl("ui.product", "templates.research_lab.ui:app_shell_extension", route="/solutions/research_lab/home", nav_label="Research Lab", permission="research_lab.permission.read", metadata={"component": "templates/research_lab/ui/ResearchLabExtension.tsx", "style": "templates/research_lab/ui/research-lab.css", "surfaces": len(extension_pages())})],
        "reports": [
            _decl("report.research_receipt", "templates.research_lab.exports:research_receipt"),
            _decl("report.iclr", "templates.research_lab.exports:manuscript_section"),
            _decl("report.research_report", "templates.research_lab.exports:manuscript_section"),
        ],
        "fixtures": [_decl("fixture.reference_e2e", "templates.research_lab.fixtures:reference_workload")],
        "migrations": [_decl("migration.0_1_0_to_1_0_0", "templates.research_lab.migrations:transform_legacy", from_version="0.1.0", to_version="1.0.0", checksum=migration_checksum(), reversible=True)],
        "permissions": [
            _decl("permission.read", "templates.research_lab.api", action="research_lab.permission.read", scope="template", risk="low", default="allow"),
            _decl("permission.experiment_write", "templates.research_lab.api", action="research_lab.permission.experiment.write", scope="project", risk="medium", default="ask"),
            _decl("permission.compute_local", "templates.research_lab.executors", action="research_lab.permission.compute.local", scope="run", risk="high", default="deny"),
            _decl("permission.compute_remote", "templates.research_lab.executors", action="research_lab.permission.compute.remote", scope="run", risk="critical", default="deny"),
            _decl("permission.claim_review", "templates.research_lab.evidence:evaluate_claim", action="research_lab.permission.claim.review", scope="project", risk="medium", default="ask"),
        ],
        "api_routes": [_decl("api.domain", "templates.research_lab.api:route_contracts", contract_version="template-platform-api/v1", configuration={"prefix": "/api/v1/templates/research_lab", "routes": [dict(route) for route in route_contracts()]})],
        "cli_commands": [
            _decl("cli.validate", "templates.research_lab.cli:main"),
            _decl("cli.migration_dry_run", "templates.research_lab.cli:main"),
            _decl("cli.checkpoint_validate", "templates.research_lab.cli:main"),
            _decl("cli.api_contracts", "templates.research_lab.cli:main"),
            _decl("cli.bdci_build", "templates.research_lab.cli:main"),
            _decl("cli.operation", "templates.research_lab.cli:main"),
        ],
        "testing_hooks": [
            _decl("testing.contract", "templates.research_lab.fixtures:reference_workload"),
            _decl("testing.reference_e2e", "templates.research_lab.fixtures:reference_workload"),
            _decl("testing.external_preflight", "templates.research_lab.observability:external_preflight"),
        ],
        "exports": [
            _decl("export.reproducibility", "templates.research_lab.exports:reproducibility_bundle"),
            _decl("export.bibtex", "templates.research_lab.literature:export_bibtex"),
            _decl("export.research_receipt", "templates.research_lab.exports:research_receipt"),
            _decl("export.bdci_submission", "templates.research_lab.exports:bdci_submission_package"),
        ],
        "upgrade_policy": {"preview_required": True, "approval_required": True, "backup_required": True, "rollback_required": True, "readback_required": True, "receipt_required": True, "compatibility": "explicit_matrix"},
        "uninstall_policy": {"preview_required": True, "approval_required": True, "readback_required": True, "receipt_required": True, "archive_history": True, "data_policy": "archive"},
        "provenance": {"source_repository": "geogejoy107-jpg/agentops-mis-mvp", "source_commit": "0000000000000000000000000000000000000000", "built_at": "2026-08-12T00:00:00+08:00"},
        "integrity": {"algorithm": "sha256", "content_sha256": "0" * 64, "signature": {"status": "unsigned_candidate"}},
    }
    domain_ids = {
        "ResearchProject": "research_project", "ResearchContract": "research_contract", "ResearchQuestion": "research_question", "LiteratureEvidence": "literature_evidence", "Experiment": "experiment", "ProtocolVersion": "protocol", "Trial": "trial", "JobAttempt": "job_attempt", "ComputeTarget": "compute_target", "Checkpoint": "checkpoint", "MetricSnapshot": "metric_snapshot", "ResearchArtifact": "research_artifact", "ResearchClaim": "research_claim", "ClaimEvidence": "claim_evidence", "Manuscript": "manuscript", "ResearchReceipt": "research_receipt",
    }
    manifest["domain_objects"] = [
        *({"id": f"research_lab.domain.{domain_ids[name]}", "name": name, "authority": "template_domain", "schema": {"version": "research-lab-domain/v1"}} for name in domain_names),
        *({"name": name, "authority": "mis_core_reference", "core_authority_id": authority_id} for name, authority_id in (
            ("Workspace", "mis_core.workspace"), ("Project", "mis_core.project"), ("Agent", "mis_core.agent"), ("Task", "mis_core.task"), ("Plan", "mis_core.plan"), ("Run", "mis_core.run"), ("ToolCall", "mis_core.tool_call"), ("PreparedAction", "mis_core.prepared_action"), ("Approval", "mis_core.approval"), ("Artifact", "mis_core.artifact"), ("Evaluation", "mis_core.evaluation"), ("MemoryReview", "mis_core.memory_review"), ("Audit", "mis_core.audit"), ("Evidence", "mis_core.evidence"), ("Identity", "mis_core.identity"), ("Permission", "mis_core.permission")
        )),
    ]
    manifest["integrity"]["content_sha256"] = manifest_content_sha256(manifest)
    return validate_template_manifest(manifest)
