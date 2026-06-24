# Experiment protocol and anti-drift contract

Every submitted experiment freezes a canonical JSON document and SHA-256 hash.

Mandatory scientific fields:

```text
research_question
primary_metric
initialization_mode
training_scope
```

Real training should additionally declare dataset/split/preprocessing version, architecture, checkpoint source/hash, trainable and frozen modules, optimizer/scheduler, effective batch, budget, seed set, metric implementation, and checkpoint-selection rule.

The runtime writes `actuals.json`. Research Lab compares declared and actual conditions. Differences such as `official_checkpoint` versus `from_scratch`, or `full_model` versus `head_only`, are visible deviations and close the scientific claim gate.

Post-result explanations do not modify the original protocol. They become a new hypothesis and a new protocol version.
