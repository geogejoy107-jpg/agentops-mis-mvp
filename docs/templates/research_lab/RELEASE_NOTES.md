# Research Lab Template 1.0.0 Candidate

Introduces a Core-backed production Research domain with immutable protocols,
Trial/JobAttempt separation, Local/SSH/Slurm contracts, framework-neutral and
PyTorch checkpoints, event-driven openJiuwen team registration, verified
literature, Evidence graph/Claim Gate, reproducibility and Research Receipt
exports, migration, two product profiles and complete API/UI extension
declarations.

The candidate now uses cryptographic, revocable Core receipt verification with
exact per-record, execution, runtime, migration, citation and export bindings;
strict scheduler-state parsing; signed private SSH target registration;
restart-safe migration coordination; and individual registration of 41 API
method/path declarations. The runtime dependency is exactly pinned to 0.1.16.

Production trust now uses C0's Ed25519 public-key-only opaque verifier; HMAC and
domain-side signing were removed. Strict SDK registration mounts only 16
template-owned domain objects, uses `research_lab.memory_policy.default`, and
registers exactly the 41 manifest-declared routes. SSH execution fsyncs a
launch fence before launch and cannot start a second process after the
fence/launch/receipt crash windows.

The Research production composition now builds C0's exported
`TrustedCoreReceiptVerifier`, constructs the exported
`TemplateEntrypointRegistry`, registers fixed process-startup handlers and
executes the real C0 manifest mount. C0 tests consume immutable `git archive`
source from implementation commit `aa667fcc012a5eed4a6e823741d8867f750417a1`;
the distinct contract base remains `1bce8f9e0312df9a29635a6988b62cd297b1ab14`.

This build is Candidate and `canonical=false`. Release-level real openJiuwen,
SSH GPU, restart/disconnect, checkpoint/resume, transfer and Claim receipts are
not available in this environment. Slurm remains required if the selected
target infrastructure uses it.
