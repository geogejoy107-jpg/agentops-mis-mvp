# Next.js/Postgres Memory Candidate Acceptance

## Ownership

Team and Enterprise direct mode owns `POST /api/mis/agent-gateway/memories/propose`
in Next.js/TypeScript with Postgres persistence. Free Local and an explicit
`proxy` rollback mode keep the Python/SQLite route; they are not the commercial
direct-write authority.

The Agent Gateway credential remains the execution contract. The route accepts
only `memories:propose`, enforces the credential workspace and Agent identity,
and permits task-bound candidates only for the task owner or a listed
collaborator. A task scope without a real task or run binding fails closed.

## Human Boundary

Agents may create immutable `candidate` rows only. They cannot assign a Human
owner, set a review decision, mutate a reviewed memory, or choose an arbitrary
memory ID. Exact `/api/mis/memories/:memory_id/approve|reject` routes now use
the fail-closed workspace-admin identity before any database query and transact
candidate review directly in Postgres with per-memory locking, immutable
terminal decisions, concurrent idempotency, and one audit/runtime transition.
That decision surface is source/typecheck ready but remains outside this
candidate-only receipt until the expanded no-Python Postgres smoke passes; it
must not be claimed from `nextjs_postgres_memory_propose_v1` alone.

## Evidence

`nextjs_postgres_memory_propose_v1` starts the real Next.js route against an
isolated Postgres database without starting the Python MIS API. It verifies:

- owner and collaborator authorization, plus unassigned and foreign-task denial;
- task-scope binding, workspace-bound IDs, and cross-workspace ID non-disclosure;
- independent-session concurrent retry with one memory/runtime/audit winner;
- distinct immutable candidates for separate runs of the same task;
- immutable candidate replay and Human review boundary enforcement;
- a 64 KiB request-body limit enforced before authentication and database work;
- PAT, JWT, private-key, Agent token, email, spaced-phone, and contiguous-phone
  omission from HTTP, Postgres, runtime-event, and audit evidence;
- the production Worker payload builder with `scope=task`, pre-transport secret
  omission, and Python rollback ID/default/immutable-replay parity.

Run the gate with:

```bash
python3 -B scripts/nextjs_postgres_memory_propose_smoke.py
```

The smoke does not execute a model adapter or a complete Worker process. It is
deterministic integration evidence only. Product-level acceptance additionally
requires a real Agent Gateway Worker run through Hermes or OpenClaw on the exact
committed head, with `dry_run=false` and raw prompt, raw response, credential,
and transcript omission.
