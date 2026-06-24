# AgentOps Research Lab — Standalone v0.3

A path-isolated, local-first prototype for **asynchronous parallel experiments, remote SSH execution, and scientific-integrity gates**.

The module is deliberately independent from the AgentOps MIS release line. It has its own Python package, CLI, SQLite WAL ledger, workspaces, tests, reports, and event export. It does **not** modify `agentops_mis.db`, `server.py`, the MIS schema, or the current MIS UI.

## v0.3 capability baseline

- Immutable Experiment Protocol and SHA-256 identity.
- Explicit experiment stages: `smoke`, `pilot`, `search`, `confirmatory`, `ablation`, `robustness`, `reproduction`.
- Parameter-matrix expansion into independent scientific Trials.
- Bounded asynchronous execution and per-server concurrency caps.
- Strict separation of scientific `Trial` and retryable infrastructure `JobAttempt`.
- Local executor plus a guarded OpenSSH executor adapter.
- Safe source staging: explicit paths, deterministic archive, size limit, traversal/link/secret-file rejection.
- Non-secret server registry with stable public profile snapshots and profile-drift blocking.
- Remote stdout/stderr, metrics, actuals, artifacts, runtime status, and remote job reference collection.
- Fail-closed remote recovery: interrupted remote jobs become `remote_unknown` / `blocked`, not automatic retries.
- Runtime `actuals.json`, Protocol-to-Run deviations, and a separate Scientific Claim Gate.
- Read-only local website, standalone HTML report, and redacted JSONL event export.
- Python standard library only at runtime.

## Install

```bash
python -m venv .venv
. .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -e .
```

Python 3.11 or newer is required. Real SSH execution also requires a system OpenSSH client and key/agent-based authentication.

## Local execution

```bash
research-lab init --db .research-lab/lab.db --workspace .research-lab/workspace
research-lab validate-spec --spec examples/confirmatory_experiment.json
research-lab submit \
  --db .research-lab/lab.db \
  --workspace .research-lab/workspace \
  --spec examples/confirmatory_experiment.json
research-lab run \
  --db .research-lab/lab.db \
  --workspace .research-lab/workspace \
  --experiment-id <ID>
```

## SSH server registry

Copy and edit the safe example. Never place passwords, tokens, private-key material, or secret environment values in this file.

```bash
cp examples/servers.example.json servers.local.json
research-lab server-list --servers servers.local.json
research-lab server-probe --servers servers.local.json --profile lab-gpu-01
```

A profile stores connection metadata and optional **local file references** only. The stable public snapshot is frozen into the experiment protocol. Changing host, remote root, concurrency, Python executable, or host-key policy after submission blocks execution and requires a new Protocol version.

## Submit an SSH experiment

```bash
research-lab validate-spec \
  --spec examples/ssh_experiment.json \
  --servers servers.local.json

research-lab submit \
  --db .research-lab/lab.db \
  --workspace .research-lab/workspace \
  --spec examples/ssh_experiment.json \
  --servers servers.local.json

research-lab run \
  --db .research-lab/lab.db \
  --workspace .research-lab/workspace \
  --experiment-id <ID> \
  --servers servers.local.json
```

SSH v0.3 is intentionally conservative:

- non-interactive `BatchMode=yes`;
- strict or `accept-new` host-key policy;
- no password field;
- no arbitrary environment-value forwarding;
- no absolute or parent-relative local command paths;
- explicit staging allowlist;
- deterministic staged-content hash;
- remote transport failure becomes `remote_unknown`, never silent retry.

## Scientific integrity

Technical success, protocol fidelity, and scientific claim eligibility are evaluated separately. Smoke, pilot, and search stages cannot silently become final scientific evidence.

## Verification

```bash
python -m compileall -q research_lab examples tests
python -m unittest discover -s tests -v
```

v0.3 has 21 deterministic tests, including bounded loopback-SSH execution, profile drift, deterministic staging, traversal rejection, secret-file rejection, and fail-closed remote interruption. A real SSH target is still required for infrastructure dogfood.

## Repository strategy

```text
agentops-mis-mvp
└── incubator/research-lab/   # standalone package; no production MIS import
```

The development branch is `incubator/research-lab-ssh-v0-3`. After v1.5 merge and real-server verification, the module can remain a professional MIS template or be history-preservingly extracted into a separate repository.

## Next lanes

1. One authorized SSH/GPU server dogfood and cancellation/remote reconciliation.
2. Slurm/Submitit executor.
3. MLflow tracker adapter; DVC/Hydra provenance adapters.
4. Paper Claim Ledger and Paper-to-Protocol / Run-to-Claim consistency.
5. Research UI and idempotent AgentOps MIS import adapter.
