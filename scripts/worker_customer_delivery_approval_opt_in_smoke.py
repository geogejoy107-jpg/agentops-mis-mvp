#!/usr/bin/env python3
"""Verify the Worker requests delivery review only through the TS/Postgres owner."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentops_mis_cli import worker  # noqa: E402


class FakeClient:
    workspace_id = "workspace_delivery_contract"
    agent_id = "agent_delivery_contract"

    def __init__(self, receipt: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.receipt = receipt or valid_receipt()

    def post(self, path: str, payload: dict) -> dict:
        self.calls.append((path, payload))
        return self.receipt


def valid_receipt() -> dict:
    return {
        "ok": True,
        "provider": "agentops-customer-delivery-approval",
        "control_plane": "typescript_postgres",
        "operation": "customer_delivery_approval_request",
        "outcome": "created",
        "approval": {
            "approval_id": "approval_delivery_contract",
            "approval_kind": "customer_delivery",
            "task_id": "task_delivery_contract",
            "run_id": "run_delivery_contract",
            "requested_by_agent_id": "agent_delivery_contract",
            "decision": "pending",
            "approver_user_id": None,
        },
        "plan_evidence": {
            "pass": True,
            "status": "verified",
        },
        "token_omitted": True,
    }


def args(
    *,
    request: bool,
    adapter: str = "hermes",
    confirm_run: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        adapter=adapter,
        confirm_run=confirm_run,
        request_customer_delivery_approval=request,
    )


def require_raises(message: str, call) -> None:
    try:
        call()
    except RuntimeError:
        return
    raise AssertionError(message)


def request(
    client: FakeClient,
    arguments: SimpleNamespace,
    *,
    run_succeeded: bool = True,
    manifest_passed: bool = True,
) -> dict:
    return worker.request_customer_delivery_approval(
        client,
        arguments,
        task_id="task_delivery_contract",
        run_id="run_delivery_contract",
        run_succeeded=run_succeeded,
        manifest_verification={"pass": manifest_passed},
    )


def main() -> int:
    parser = worker.build_parser()
    assert parser.parse_args([]).request_customer_delivery_approval is False
    assert parser.parse_args([
        "--adapter",
        "hermes",
        "--confirm-run",
        "--request-customer-delivery-approval",
    ]).request_customer_delivery_approval is True

    disabled_client = FakeClient()
    assert request(disabled_client, args(request=False)) == {}
    assert disabled_client.calls == []

    valid_client = FakeClient()
    receipt = request(valid_client, args(request=True))
    assert receipt["control_plane"] == "typescript_postgres"
    assert len(valid_client.calls) == 1
    path, payload = valid_client.calls[0]
    assert path == "/api/agent-gateway/approvals/request"
    assert payload == {
        "workspace_id": valid_client.workspace_id,
        "agent_id": valid_client.agent_id,
        "requested_by_agent_id": valid_client.agent_id,
        "task_id": "task_delivery_contract",
        "run_id": "run_delivery_contract",
        "approval_kind": "customer_delivery",
        "decision": "pending",
        "reason": "Customer delivery requires Human Owner review.",
    }

    for label, arguments, run_succeeded, manifest_passed in (
        ("mock_adapter", args(request=True, adapter="mock"), True, True),
        ("codex_adapter", args(request=True, adapter="codex"), True, True),
        ("unconfirmed", args(request=True, confirm_run=False), True, True),
        ("failed_run", args(request=True), False, True),
        ("blocked_manifest", args(request=True), True, False),
    ):
        client = FakeClient()
        require_raises(
            f"{label} unexpectedly requested delivery approval",
            lambda client=client, arguments=arguments, run_succeeded=run_succeeded,
            manifest_passed=manifest_passed: request(
                client,
                arguments,
                run_succeeded=run_succeeded,
                manifest_passed=manifest_passed,
            ),
        )
        assert client.calls == []

    invalid_receipts = (
        {"operation": "customer_delivery_approval_request"},
        {
            **valid_receipt(),
            "control_plane": "python",
        },
        {
            **valid_receipt(),
            "approval": {
                **valid_receipt()["approval"],
                "approver_user_id": "agent_must_not_approve",
            },
        },
        {
            **valid_receipt(),
            "plan_evidence": {"pass": False},
        },
        {
            **valid_receipt(),
            "approval": {
                **valid_receipt()["approval"],
                "run_id": "run_other",
            },
        },
    )
    for invalid_receipt in invalid_receipts:
        client = FakeClient(invalid_receipt)
        require_raises(
            "invalid owner receipt was accepted",
            lambda client=client: request(client, args(request=True)),
        )
        assert len(client.calls) == 1

    print(json.dumps({
        "contract": "worker_customer_delivery_approval_opt_in_v1",
        "ok": True,
        "default_opt_in": False,
        "allowed_adapters": ["hermes", "openclaw"],
        "confirmed_live_run_required": True,
        "verified_plan_evidence_required": True,
        "typescript_postgres_receipt_required": True,
        "task_run_requester_binding_required": True,
        "agent_self_approval_rejected": True,
        "python_api_started": False,
        "token_omitted": True,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
