"""Domain CLI hooks registered beneath the shared ``agentops template`` CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from template_runtime.contracts import validate_template_manifest

from .checkpoints import PyTorchCheckpointAdapter
from .api import route_contracts
from .exports import SubmissionEvidencePort, bdci_evaluation_script, bdci_submission_package
from .manifest import build_manifest
from .migrations import dry_run_legacy
from .contracts import CoreRefs
from .operations import ResearchOperationsAdapter
from .trust import CoreTrustStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentops template research-lab")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-manifest")
    migration = sub.add_parser("migration-dry-run")
    migration.add_argument("records")
    checkpoint = sub.add_parser("checkpoint-validate")
    checkpoint.add_argument("path")
    sub.add_parser("api-contracts")
    bdci = sub.add_parser("bdci-build")
    bdci.add_argument("spec")
    operation = sub.add_parser("operation")
    operation.add_argument("name")
    operation.add_argument("refs")
    operation.add_argument("body")
    return parser


def main(argv: Sequence[str] | None = None, *, evidence_port: SubmissionEvidencePort | None = None, operations: ResearchOperationsAdapter | None = None, trust: CoreTrustStore | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate-manifest":
        payload = {"valid": True, "manifest": validate_template_manifest(build_manifest())}
    elif args.command == "migration-dry-run":
        records = json.loads(Path(args.records).read_text(encoding="utf-8"))
        payload = dry_run_legacy(records)
    elif args.command == "checkpoint-validate":
        payload = PyTorchCheckpointAdapter.validate_container(Path(args.path).resolve())
    elif args.command == "api-contracts":
        payload = {"api_version": "template-platform-api/v1", "routes": list(route_contracts())}
    elif args.command == "bdci-build":
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        evaluation_script = bdci_evaluation_script(input_schema=spec["input_output_manifest"]["input_schema"], output_schema=spec["input_output_manifest"]["output_schema"], metric=spec["metric"])
        if evidence_port is None or trust is None:
            raise RuntimeError("bdci-build requires the host-injected MIS Core evidence port")
        payload = bdci_submission_package(short_paper=spec["short_paper"], iclr_export=spec["iclr_export"], reproducibility=spec["reproducibility"], input_output_manifest=spec["input_output_manifest"], evaluation_script=evaluation_script, claims=spec["claims"], evidence_port=evidence_port, trust=trust)
    else:
        if operations is None:
            raise RuntimeError("operation requires the host-injected governed Research operations adapter")
        refs_value = json.loads(Path(args.refs).read_text(encoding="utf-8"))
        body = json.loads(Path(args.body).read_text(encoding="utf-8"))
        refs = CoreRefs(**refs_value)
        payload = operations.execute(operation=args.name, body=body, refs=refs)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
