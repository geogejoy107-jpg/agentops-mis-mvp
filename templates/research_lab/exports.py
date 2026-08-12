"""Reproducibility, manuscript and Research Receipt export builders."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import re
from typing import Any, Protocol, runtime_checkable

from .contracts import ResearchError, canonical_hash
from .trust import CoreTrustStore, reject_untrusted_payload, require_core_receipt


@runtime_checkable
class ExportEvidencePort(Protocol):
    def verify_export_evidence(self, *, export_kind: str, references: Mapping[str, Sequence[str]]) -> Mapping[str, Any]: ...


def _verified_export(port: ExportEvidencePort, kind: str, references: Mapping[str, Sequence[str]], trust: CoreTrustStore) -> str:
    if not isinstance(port, ExportEvidencePort):
        raise ResearchError("research.export_core_readback_missing", "export requires a MIS Core evidence readback port")
    normalized = {key: list(map(str, value)) for key, value in sorted(references.items())}
    reject_untrusted_payload(normalized, path=f"export.{kind}.references")
    expected_reference_hash = canonical_hash({"export_kind": kind, "references": normalized})
    receipt = require_core_receipt(port.verify_export_evidence(export_kind=kind, references=references), trust=trust, purpose="research.export-evidence/v1", bindings={"verified": True, "export_kind": kind, "reference_hash": expected_reference_hash})
    return str(receipt["receipt_hash"])


def reproducibility_bundle(*, protocol: Mapping[str, Any], attempts: Sequence[Mapping[str, Any]], metrics: Sequence[Mapping[str, Any]], artifacts: Sequence[Mapping[str, Any]], claims: Sequence[Mapping[str, Any]], evidence_port: ExportEvidencePort, trust: CoreTrustStore) -> Mapping[str, Any]:
    required_protocol = {"protocol_hash", "code_commit", "dataset_version", "environment_lock_hash", "seeds"}
    missing = sorted(required_protocol - protocol.keys())
    if missing:
        raise ResearchError("research.reproducibility_incomplete", "protocol missing: " + ", ".join(missing))
    for artifact in artifacts:
        if not artifact.get("sha256") or not artifact.get("artifact_id"):
            raise ResearchError("research.artifact_integrity_missing", "every artifact requires Core ID and sha256")
    readback_hash = _verified_export(evidence_port, "reproducibility", {"protocol_hashes": [str(protocol.get("protocol_hash") or "")], "code_commits": [str(protocol.get("code_commit") or "")], "dataset_versions": [str(protocol.get("dataset_version") or "")], "environment_lock_hashes": [str(protocol.get("environment_lock_hash") or "")], "attempt_ids": [str(item.get("job_attempt_id") or "") for item in attempts], "metric_ids": [str(item.get("metric_snapshot_id") or "") for item in metrics], "artifact_ids": [str(item.get("artifact_id") or "") for item in artifacts], "artifact_sha256s": [str(item.get("sha256") or "") for item in artifacts], "claim_ids": [str(item.get("research_claim_id") or "") for item in claims], "evaluation_ids": [str(item.get("evaluation_id") or "") for item in claims], "reviewer_ids": [str(item.get("reviewer_id") or "") for item in claims]}, trust)
    manifest = {
        "schema_version": "research-reproducibility-bundle/v1",
        "protocol": dict(protocol),
        "attempt_refs": [item.get("job_attempt_id") for item in attempts],
        "metric_refs": [item.get("metric_snapshot_id") for item in metrics],
        "artifacts": [{"artifact_id": item.get("artifact_id"), "sha256": item.get("sha256"), "media_type": item.get("media_type")} for item in artifacts],
        "claim_refs": [item.get("research_claim_id") for item in claims],
        "contains_raw_prompts_or_secrets": False,
        "core_readback_receipt_hash": readback_hash,
    }
    return {**manifest, "bundle_hash": canonical_hash(manifest)}


def manuscript_section(*, section: str, content_artifact_id: str, claim_ids: Sequence[str], figure_artifact_ids: Sequence[str], table_artifact_ids: Sequence[str], citations: Sequence[Mapping[str, str]], evidence_port: ExportEvidencePort, trust: CoreTrustStore) -> Mapping[str, Any]:
    if section not in {"abstract", "introduction", "related_work", "method", "experiments", "results", "limitations", "conclusion"}:
        raise ResearchError("research.invalid_manuscript_section", "unsupported manuscript section")
    if section in {"method", "experiments", "results"} and not claim_ids:
        raise ResearchError("research.unsupported_manuscript", "evidence-bearing sections require claim references")
    if any(not item.get("literature_id") or not item.get("locator") for item in citations):
        raise ResearchError("research.citation_locator_missing", "citations require source and locator")
    readback_hash = _verified_export(evidence_port, "manuscript", {"artifact_ids": [content_artifact_id, *figure_artifact_ids, *table_artifact_ids], "claim_ids": list(claim_ids), "literature_ids": [str(item.get("literature_id") or "") for item in citations], "citation_locators": [str(item.get("locator") or "") for item in citations], "source_excerpt_hashes": [str(item.get("source_excerpt_hash") or "") for item in citations]}, trust)
    value = {"section": section, "content_artifact_id": content_artifact_id, "claim_ids": list(claim_ids), "figure_artifact_ids": list(figure_artifact_ids), "table_artifact_ids": list(table_artifact_ids), "citations": [dict(item) for item in citations], "core_readback_receipt_hash": readback_hash}
    return {**value, "section_hash": canonical_hash(value)}


def research_receipt(*, core_refs: Mapping[str, str], protocol_hash: str, experiment_id: str, trial_ids: Sequence[str], attempt_ids: Sequence[str], artifact_ids: Sequence[str], evaluation_ids: Sequence[str], claim_ids: Sequence[str], reviewer_ids: Sequence[str], external_integrations: Sequence[Mapping[str, Any]], evidence_port: ExportEvidencePort, trust: CoreTrustStore) -> Mapping[str, Any]:
    required_core = {"workspace_id", "project_id", "task_id", "plan_id", "run_id", "audit_id"}
    if sorted(required_core - core_refs.keys()):
        raise ResearchError("research.receipt_core_refs_missing", "Research Receipt must bind MIS Core authority")
    references = {"workspace_ids": [core_refs["workspace_id"]], "project_ids": [core_refs["project_id"]], "task_ids": [core_refs["task_id"]], "plan_ids": [core_refs["plan_id"]], "run_ids": [core_refs["run_id"]], "audit_ids": [core_refs["audit_id"]], "protocol_hashes": [protocol_hash], "experiment_ids": [experiment_id], "trial_ids": list(trial_ids), "attempt_ids": list(attempt_ids), "artifact_ids": list(artifact_ids), "evaluation_ids": list(evaluation_ids), "claim_ids": list(claim_ids), "reviewer_ids": list(reviewer_ids), "external_integrations_hashes": [canonical_hash([dict(item) for item in external_integrations])]}
    readback_hash = _verified_export(evidence_port, "research_receipt", references, trust)
    value = {
        "schema_version": "research-receipt/v1",
        "template_version": "1.0.0",
        "core_refs": dict(core_refs),
        "protocol_hash": protocol_hash,
        "experiment_id": experiment_id,
        "trial_ids": list(trial_ids),
        "job_attempt_ids": list(attempt_ids),
        "artifact_ids": list(artifact_ids),
        "evaluation_ids": list(evaluation_ids),
        "claim_ids": list(claim_ids),
        "reviewer_ids": list(reviewer_ids),
        "external_integrations": [dict(item) for item in external_integrations],
        "canonical": False,
        "core_readback_receipt_hash": readback_hash,
    }
    return {**value, "receipt_hash": canonical_hash(value)}


@runtime_checkable
class SubmissionEvidencePort(Protocol):
    def verify_submission_evidence(self, *, references: Mapping[str, Sequence[str]]) -> Mapping[str, Any]: ...


def bdci_evaluation_script(*, input_schema: Mapping[str, Any], output_schema: Mapping[str, Any], metric: str) -> str:
    if not input_schema or not output_schema or not metric.strip():
        raise ResearchError("research.bdci_evaluation_invalid", "BDCI evaluation requires input/output schemas and metric")
    configuration = json.dumps({"input_schema": dict(input_schema), "output_schema": dict(output_schema), "metric": metric}, sort_keys=True, separators=(",", ":"))
    return "\n".join((
        "#!/usr/bin/env python3", "import json,sys", f"CONFIG={configuration!r}", "cfg=json.loads(CONFIG)", "payload=json.load(sys.stdin)",
        "if not isinstance(payload,dict) or not isinstance(payload.get('input'),dict) or not isinstance(payload.get('output'),dict): raise SystemExit('input/output objects required')",
        "def validate(obj,schema):",
        "  for key,kind in schema.items():",
        "    if key not in obj: raise SystemExit('missing field: '+key)",
        "    types={'number':(int,float),'integer':int,'string':str,'array':list,'object':dict,'boolean':bool}",
        "    if isinstance(kind,str) and kind in types and (isinstance(obj[key],bool) if kind in ('number','integer') else False): raise SystemExit('invalid field: '+key)",
        "    if isinstance(kind,str) and kind in types and not isinstance(obj[key],types[kind]): raise SystemExit('invalid field: '+key)",
        "validate(payload['input'],cfg['input_schema']); validate(payload['output'],cfg['output_schema'])",
        "pred=payload.get('predictions'); truth=payload.get('targets')",
        "if cfg['metric']=='accuracy':",
        "  if not isinstance(pred,list) or not isinstance(truth,list) or not pred or len(pred)!=len(truth): raise SystemExit('accuracy requires equal non-empty predictions/targets')",
        "  score=sum(a==b for a,b in zip(pred,truth))/len(truth)",
        "else: raise SystemExit('unsupported metric')",
        "json.dump({'metric':cfg['metric'],'score':score,'accepted':True},sys.stdout,sort_keys=True)", ""))


def bdci_submission_package(*, short_paper: str, iclr_export: str, reproducibility: Mapping[str, Any], input_output_manifest: Mapping[str, Any], evaluation_script: str, claims: Sequence[Mapping[str, Any]], evidence_port: SubmissionEvidencePort, trust: CoreTrustStore) -> Mapping[str, Any]:
    reject_untrusted_payload({"input_output_manifest": input_output_manifest, "claims": claims}, path="bdci_submission")
    if not short_paper.strip() or not iclr_export.strip() or not evaluation_script.startswith("#!/usr/bin/env python3"):
        raise ResearchError("research.bdci_submission_incomplete", "short paper, ICLR export and executable evaluation script are required")
    if not reproducibility.get("bundle_hash") or not input_output_manifest.get("input_schema") or not input_output_manifest.get("output_schema"):
        raise ResearchError("research.bdci_submission_incomplete", "reproducibility and input/output manifests are required")
    if any(item.get("status") != "supported" or not item.get("evaluation_id") for item in claims):
        raise ResearchError("research.bdci_unsupported_claim", "submission contains a Claim without passed Core Evaluation")
    if not isinstance(evidence_port, SubmissionEvidencePort):
        raise ResearchError("research.bdci_core_readback_missing", "submission requires a MIS Core evidence readback port")
    claim_ids = [str(item.get("research_claim_id") or "") for item in claims]
    references = {
        "claim_ids": claim_ids,
        "evaluation_ids": [str(item.get("evaluation_id") or "") for item in claims],
        "reproducibility_bundle_hashes": [str(reproducibility["bundle_hash"])],
        "input_output_manifest_hashes": [canonical_hash(dict(input_output_manifest))],
        "evaluation_script_hashes": [hashlib.sha256(evaluation_script.encode("utf-8")).hexdigest()],
        "short_paper_hashes": [hashlib.sha256(short_paper.encode("utf-8")).hexdigest()],
        "iclr_export_hashes": [hashlib.sha256(iclr_export.encode("utf-8")).hexdigest()],
    }
    expected_reference_hash = canonical_hash({"submission_kind": "bdci_2026", "references": {key: list(value) for key, value in sorted(references.items())}})
    readback = require_core_receipt(evidence_port.verify_submission_evidence(references=references), trust=trust, purpose="research.bdci-submission-evidence/v1", bindings={"verified": True, "reference_hash": expected_reference_hash})
    if sorted(readback.get("claim_ids") or ()) != sorted(claim_ids):
        raise ResearchError("research.bdci_core_readback_invalid", "submission Claims, Evaluations and Artifacts did not pass MIS Core readback")
    supplied_hash = str(readback["receipt_hash"])
    files = {
        "paper/short-paper.md": short_paper,
        "paper/iclr-export.tex": iclr_export,
        "evaluation/evaluate.py": evaluation_script,
        "submission/input-output-manifest.json": json.dumps(dict(input_output_manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "submission/reproducibility.json": json.dumps(dict(reproducibility), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "submission/claims.json": json.dumps([dict(item) for item in claims], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    }
    entries = [{"path": path, "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(), "size_bytes": len(content.encode("utf-8"))} for path, content in sorted(files.items())]
    package_manifest = {"schema_version": "bdci-2026-submission/v1", "entries": entries, "required_outputs": ["short_paper", "iclr_export", "reproducibility_bundle", "evaluation_script", "input_output_manifest", "submission_package"], "core_readback_receipt_hash": supplied_hash, "contains_raw_prompts_or_secrets": False}
    return {"manifest": package_manifest, "files": files, "package_hash": canonical_hash(package_manifest)}
