# Asynchronous execution contract — v0.3

Each scientific Trial runs in an independent bounded asynchronous lane. The effective SSH concurrency is the lower of the experiment limit and the selected server profile limit.

```text
ExperimentGroup
  +-- Trial 1 -> JobAttempt 1
  +-- Trial 2 -> JobAttempt 1
  +-- Trial 3 -> waits for a slot
```

A Trial is scientific identity; a JobAttempt is one infrastructure execution. Retries never increase the scientific Trial count.

Local interrupted attempts may retry when budget remains. Remote attempts with an unknown outcome become `remote_unknown`; their Trials become `blocked` until an operator reconciles the remote job. This prevents accidental duplicate GPU execution.

The target adapter lifecycle is `prepare -> start -> observe -> collect -> reconcile`. Explicit remote cancellation and checkpoint resume are reserved for the next real-server lane.
