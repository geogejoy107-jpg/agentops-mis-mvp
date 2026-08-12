# Research Lab security model

- Default deny for local/remote compute; remote compute is critical risk.
- External effects require Core PreparedAction/Approval and execute-once
  receipts.
- Core authority is accepted only from purpose-separated HMAC-SHA256 receipts
  with a trusted, revocable key ID, Audit ID, canonical envelope and exact
  field/document bindings. HMAC is the initial private-host verifier; the fixed
  test key is fixture-only. Production C0 owns protected verifier configuration,
  signing separation and key rotation.
- Local tools require a governed workspace root, executable/tool allowlists and
  Core PreparedAction/Approval execute-once readback. Shell trampolines,
  dynamic-loader environment overrides and untrusted interpreter snippets fail closed.
- SSH target fields, remote roots, Slurm IDs/arrays and URLs are allowlisted;
  private SSH targets require an exact signed registration snapshot. Slurm
  terminal state is parsed from one strict `sacct` row and never by substring.
- Secret literals in argv/environment are rejected; SSH references are resolved
  only into the child environment, request JSON uses stdin, and nested logs plus
  configured output literals are redacted before hashing receipts.
- Artifact and checkpoint files are content hashed; symlinks/path traversal are
  forbidden. PyTorch zip validation performs no pickle deserialization.
- Research records are always workspace scoped. Cross-template access is
  delegated to explicit shared-memory policy and is denied by default.
- Literature uses public HTTPS plus DOI/arXiv identity; Claim citations require
  a locator and excerpt hash to detect unsupported or hallucinated citations.
- Raw prompts, responses, private transcripts and checkpoint bytes are not
  committed or placed in MIS evidence.
