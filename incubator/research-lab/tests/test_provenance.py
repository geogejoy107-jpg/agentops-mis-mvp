from __future__ import annotations

import unittest

from research_lab.protocol import ExperimentSpec, SpecError
from research_lab.provenance import ProvenanceError, ProvenanceSpec


GOOD_PROVENANCE = {
    "code": {
        "repository": "https://example.invalid/project.git",
        "revision": "abc123",
        "dirty": False,
    },
    "datasets": [
        {
            "name": "train",
            "uri": "dvc://dataset/train",
            "version": "data-v1",
        }
    ],
    "models": [],
    "resolved_config": {"optimizer": {"name": "adamw", "lr": 0.001}},
}


class ProvenanceTests(unittest.TestCase):
    def test_hash_is_stable_under_key_reordering(self) -> None:
        one = ProvenanceSpec.from_dict(GOOD_PROVENANCE)
        two = ProvenanceSpec.from_dict(
            {
                "resolved_config": {"optimizer": {"lr": 0.001, "name": "adamw"}},
                "models": [],
                "datasets": [
                    {
                        "version": "data-v1",
                        "uri": "dvc://dataset/train",
                        "name": "train",
                    }
                ],
                "code": {
                    "dirty": False,
                    "revision": "abc123",
                    "repository": "https://example.invalid/project.git",
                },
            }
        )
        self.assertEqual(one.provenance_hash, two.provenance_hash)
        self.assertEqual(one.resolved_config_hash, two.resolved_config_hash)

    def test_reference_uri_rejects_unstable_query_data(self) -> None:
        bad = dict(GOOD_PROVENANCE)
        bad["datasets"] = [
            {
                "name": "train",
                "uri": "https://example.invalid/data?temporary=1",
                "version": "v1",
            }
        ]
        with self.assertRaises(ProvenanceError):
            ProvenanceSpec.from_dict(bad)

    def test_confirmatory_requires_clean_code_dataset_and_config(self) -> None:
        with self.assertRaises(SpecError):
            ExperimentSpec.from_dict(
                {
                    "name": "missing-lineage",
                    "stage": "confirmatory",
                    "command": ["python", "train.py"],
                    "matrix": {"seed": [1, 2]},
                    "protocol": {
                        "research_question": "q",
                        "primary_metric": "score",
                        "initialization_mode": "from_scratch",
                        "training_scope": "full_model",
                    },
                }
            )

    def test_checkpoint_initialization_requires_model_reference(self) -> None:
        with self.assertRaises(SpecError):
            ExperimentSpec.from_dict(
                {
                    "name": "checkpoint-without-model-ref",
                    "stage": "confirmatory",
                    "command": ["python", "train.py"],
                    "matrix": {"seed": [1, 2]},
                    "protocol": {
                        "research_question": "q",
                        "primary_metric": "score",
                        "initialization_mode": "official_checkpoint",
                        "training_scope": "full_model",
                    },
                    "provenance": GOOD_PROVENANCE,
                }
            )


if __name__ == "__main__":
    unittest.main()
