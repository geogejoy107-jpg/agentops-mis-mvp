# Security Rules

- Fail closed for live Hermes/OpenClaw execution unless explicit confirmation is present.
- Do not store raw secrets, bearer tokens, OAuth refresh tokens, or private transcripts.
- High-risk tool calls require approval.
- External uploads require approval.
- Memory candidates require review before becoming approved memory.
- Agent tokens must be scoped and workspace-bound where possible.
- Knowledge indexing must use redacted text and must not index raw secrets, prompts, responses, customer documents, or private transcripts by default.
