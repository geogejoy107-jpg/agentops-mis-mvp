# Research external acceptance gates

Status as of 2026-08-12: `BLOCKED_EXTERNALLY` for release-level Research
acceptance; internal implementation and reference tests continue independently.

| Gate | Current state | Required receipt |
|---|---|---|
| openJiuwen Research Agent workflow | NOT_AVAILABLE | pinned upstream version, structured flow and MIS-linked runtime receipt |
| Real SSH GPU target | NOT_AVAILABLE | authorized secret references, host-key and compute-target snapshot receipt |
| Long-running task | NOT_RUN | heartbeat plus actual worker restart and readback |
| Disconnect/preemption | NOT_RUN | remote/scheduler reconcile receipt without duplicate execution |
| Checkpoint/resume | NOT_RUN_EXTERNALLY | real PyTorch checkpoint hash, compatibility and resumed attempt receipt |
| Metric/Artifact transfer | NOT_RUN_EXTERNALLY | log cursor, transfer checksum, Core Artifact IDs and readback |
| Real Claim Gate | NOT_RUN_EXTERNALLY | complete multi-seed evidence graph and independent reviewer Evaluation |
| Slurm | BOUNDARY_UNKNOWN | real Slurm receipt if target uses it, otherwise approved exclusion ADR |

Fixtures and local tests are labeled reference-only and cannot satisfy these
gates. No GPU/SSH credentials were requested, read or written by C1.
