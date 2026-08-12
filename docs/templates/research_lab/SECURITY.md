# Research Lab security model

- Default deny for local/remote compute; remote compute is critical risk.
- External effects require Core PreparedAction/Approval and execute-once
  receipts.
- Core authority is accepted only from the opaque `payload + proof +
  receipt_hash` envelope through C0's receipt-verifier protocol. Production C0
  uses Ed25519 public keys, purpose allowlists, revocation state, canonical
  payload hashes and exact authority bindings. The Research domain contains no
  signing secret or signing function; test signing material is fixture-only.
- Local tools require a governed workspace root, executable/tool allowlists and
  Core PreparedAction/Approval execute-once readback. Shell trampolines,
  dynamic-loader environment overrides and untrusted interpreter snippets fail closed.
- SSH target fields, remote roots, Slurm IDs/arrays and URLs are allowlisted;
  private SSH targets require an exact signed registration snapshot. Slurm
  terminal state is parsed from one strict `sacct` row and never by substring.
- Secret literals in argv/environment are rejected; SSH references are resolved
  only into the child environment, request JSON uses stdin, and nested logs plus
  configured output literals are redacted before hashing receipts.
- The remote wrapper fsyncs its attempt directory and an immutable launch fence
  before starting a process. A retry with a fence but no launch receipt never
  launches again: it consults an authoritative attempt/request registry and
  otherwise reports `remote_unknown`. Receipt creation uses fsynced temporary
  files and atomic no-clobber links, so crashes cannot publish partial JSON.
  Reconciliation accepts only a C0 public-key-verified
  `research.remote-launch-reconciliation.v1` receipt with exact fence bindings;
  `authority`/`authoritative` booleans never establish remote registry truth.
- Artifact and checkpoint files are content hashed; symlinks/path traversal are
  forbidden. PyTorch zip validation performs no pickle deserialization.
- Research records are always workspace scoped. Cross-template access is
  delegated to explicit shared-memory policy and is denied by default.
- Literature uses public HTTPS plus DOI/arXiv identity; Claim citations require
  a locator and excerpt hash to detect unsupported or hallucinated citations.
- Raw prompts, responses, private transcripts and checkpoint bytes are not
  committed or placed in MIS evidence.
