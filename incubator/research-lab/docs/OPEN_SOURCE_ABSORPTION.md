# Open-source absorption map — Research Lab v0.3.1

> Verified: 2026-06-24  
> Mode: method adaptation and optional adapters; no authority transfer

## Rule

Research Lab may adopt execution, tracking, versioning, configuration, search, and scheduler patterns. The standalone ledger remains authoritative for Experiment Protocol, Trial identity, JobAttempt identity, protocol deviation, scientific claim eligibility, and exported evidence. External IDs are references, not replacements.

## MLflow 3

Borrowed ideas:

- separate experiment containers, execution runs, logged models, datasets, metrics, and artifacts;
- retain stable external model/run IDs;
- link checkpoint metrics to a model and dataset;
- support local-first tracking and a later remote tracking server.

Adaptation:

- Trial and JobAttempt remain distinct first-party objects;
- `provenance.models` and `provenance.datasets` retain stable external references;
- a future MLflow adapter maps an ExperimentGroup to an MLflow experiment and each JobAttempt to a run.

Not delegated: protocol approval, comparability, deviation review, claim eligibility, reviewed memory, or MIS audit.

Primary source: <https://mlflow.org/docs/latest/ml/tracking/>

## DVC

Borrowed ideas:

- version datasets, models, pipeline inputs/outputs, parameters, metrics, plots, and experiments;
- treat data/model revision and content digest as explicit experiment inputs.

Adaptation:

- `provenance.datasets`, `provenance.models`, and `provenance.environment` accept stable URI/version/digest references;
- these references are frozen into the protocol and `provenance_hash`.

Not delegated: Trial identity, scientific interpretation, or the claim gate.

Primary source: <https://dvc.org/doc/user-guide/experiment-management>

## Hydra

Borrowed ideas:

- compose a fully resolved configuration before dispatch;
- expand multi-run parameter combinations deterministically.

Adaptation:

- Research Lab expands an explicit parameter matrix;
- `provenance.resolved_config` is canonicalized and hashed before execution;
- runtime actuals must echo the resolved-config hash for strict stages.

Not delegated: Experiment Protocol authority or post-result mutation of the frozen configuration.

Primary source: <https://hydra.cc/docs/tutorials/basic/running_your_app/multi-run/>

## Slurm and Submitit

Borrowed ideas:

- scheduler job and array IDs, bounded resource allocation, logs, preemption, requeue, and checkpoint-aware recovery;
- one executor interface can target local execution or a Slurm cluster.

Adaptation:

- JobAttempt already stores an external remote job reference and executor metadata;
- unknown remote outcomes block automatic retry;
- the future scheduler adapter will preserve scheduler job ID, array index, reason code, preemption state, checkpoint reference, and requeue lineage.

Not delegated: scientific Trial count, protocol version, claim eligibility, or organizational audit.

Primary sources:

- <https://slurm.schedmd.com/job_array.html>
- <https://github.com/facebookincubator/submitit>

## Optuna

Borrowed ideas:

- decouple suggestion from execution using ask/tell;
- allow batch/distributed evaluation without giving the optimizer worker authority;
- record pruning as a distinct terminal state.

Planned adaptation:

- a future SearchController creates parameter suggestions and consumes normalized objective observations;
- suggested Trials remain `search` stage;
- pruned or early-stopped Trials cannot support a final claim;
- winning search configurations must be resubmitted as a complete `confirmatory` protocol.

Not delegated: Trial execution state, protocol deviation, final comparison, or publication claim.

Primary source: <https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/009_ask_and_tell.html>

## v0.3.1 implementation

The first absorbed implementation is a first-party `ProvenanceSpec`:

```text
Code revision
+ dataset references
+ initialization/model references
+ fully resolved configuration
+ environment reference
= provenance_hash
```

For confirmatory, robustness, and reproduction stages by default:

- code revision must be declared and clean;
- at least one dataset reference is required;
- the resolved configuration is required;
- checkpoint-based initialization requires a model reference;
- runtime actuals must echo provenance, config, and code revision hashes;
- mismatch closes the scientific claim gate even when the process exits successfully.
