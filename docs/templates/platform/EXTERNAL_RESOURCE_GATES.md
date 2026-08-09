# External resource gates

Status: Candidate / truthful preflight

Canonical: false

These gates do not pause independent implementation or local verification. They
also cannot be replaced by fixtures, historical receipts, or a successful mock.

| Gate | Current state | Evidence boundary | Resume action |
|---|---|---|---|
| Research SSH/GPU long-run | UNKNOWN | No Final Pack receipt bound to the contract SHA | Select an authorized target, record secret references only, then run disconnect/restart/checkpoint/resume acceptance |
| Slurm | UNKNOWN product boundary | No verified target-infrastructure ADR | Confirm whether target infrastructure uses Slurm; implement and run it, or record an approved exclusion ADR |
| Career official simulator | NOT_AVAILABLE | No simulator package/version/source found in current repository | Provide or locate the official target simulator and pin its version before real 48-month acceptance |
| Quant official/target data | NOT_AVAILABLE | No designated source, license, cutoff, or snapshot found in current repository | Provide or approve the target dataset/source and license, then create a hashed point-in-time snapshot |
| openJiuwen/JiuwenSwarm | NOT_INSTALLED | Python 3.11/3.14 import failed; existing branch is a fake compatibility spike | Pin an upstream release/commit and lockfile, install in a clean environment, then run real Agent and Swarm compatibility tests |
| Governed production deployment | AUTHORIZATION_CONDITIONAL | Final Pack permits only the existing governed release path after all gates | Prepare release action after exact-head gates; execute once only through repository protection and deployment controls |

Hermes and OpenClaw health/readiness are currently observable, but historical
or preflight evidence is not Final Pack real-integration acceptance. Raw prompts,
responses, private transcripts, credentials and checkpoint bytes must not enter
Git, MIS evidence, or project memory.
