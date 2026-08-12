"""Reference-only deterministic workload. It never satisfies real GPU gates."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import canonical_hash


def reference_workload() -> Mapping[str, Any]:
    value = {
        "fixture": "research_lab.reference_e2e/v1",
        "mode": "reference_fixture_only",
        "stage": "confirmatory",
        "seeds": [7, 11],
        "matrix": [{"role": "baseline", "seed": 7}, {"role": "baseline", "seed": 11}, {"role": "candidate", "seed": 7}, {"role": "candidate", "seed": 11}],
        "external_acceptance": False,
        "limitations": ["not_openjiuwen_acceptance", "not_gpu_acceptance", "not_ssh_acceptance", "not_slurm_acceptance"],
    }
    return {**value, "fixture_hash": canonical_hash(value)}
