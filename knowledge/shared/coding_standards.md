# Coding Standards

- Match the existing zero-dependency Python server style unless a feature already uses another stack.
- Use focused smoke scripts for API/CLI behavior.
- Keep CLI output machine-readable JSON.
- Keep redaction and `token_omitted=true` proofs on agent-facing commands.
- Do not commit generated databases or raw runtime logs.
