# Agent Task Harness Research Constraints Acceptance

## Scope

This acceptance note records the 2026-07-04 harness engineering research and
constraint pass for AgentOps MIS.

The slice updates the existing Agent Task Harness engineering spec. It does not
execute Hermes/OpenClaw, mutate the ledger, add a provider dependency, vendor an
external harness, change schema, or change browser UI.

## Research Inputs

Sources reviewed for the spec update:

- Promptfoo coding-agent evaluation guide:
  `https://www.promptfoo.dev/docs/guides/evaluate-coding-agents/`
- Harness-Bench paper:
  `https://arxiv.org/html/2605.27922v1`
- LangChain harness engineering case study:
  `https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering`
- Code as Agent Harness survey:
  `https://arxiv.org/html/2605.18747v1`
- Arize traces/evals harness article:
  `https://arize.com/blog/improve-ai-agents-traces-evals-harness/`
- OpenAI Evals API guide:
  `https://developers.openai.com/api/docs/guides/evals`

## Product Translation

The spec now treats harness engineering as the product layer that turns a
customer task into governed work:

```text
work packet
-> scoped runtime adapter
-> approval checkpoint when needed
-> execution trace summaries and hashes
-> evaluation
-> artifact/report
-> memory candidate
-> audit receipt
```

The added product constraint register requires:

- MIS authority remains the source of truth.
- Agents use CLI/API/MCP work packets, not browser scraping.
- Real Hermes/OpenClaw proof needs ledger readback, not just terminal success.
- Mock proof is CI/offline fallback only.
- Approval Wall requires prepared action hash, checkpoint, approval and exact
  once resume for high-risk actions.
- Summaries, hashes, ids and safe metadata are stored; raw prompts, raw
  responses, credentials, private messages and full transcripts are forbidden.
- Product reports must label evidence as real runtime, ledger readback, dry-run,
  mock fallback or pending approval.

## Verification

Command:

```bash
python3 scripts/agent_task_harness_engineering_spec_smoke.py
```

Expected result:

- The smoke validates the research-source markers.
- The smoke validates work-packet fields, phase model and scorecard fields.
- The smoke validates the new product constraint markers.
- The smoke checks for secret-like markers and forbidden harness claims.

## Known Limits

- This is a spec/constraint hardening slice, not a live-runtime execution slice.
- It does not prove a fresh Hermes/OpenClaw customer task.
- It does not install Promptfoo, Inspect AI, SWE-bench, LangSmith, Phoenix,
  Harness or any other third-party harness.
- It does not replace the existing Agent Gateway/worker path.

## Next Slice

Surface the `local_harness_proof_readiness` payload in the Worker Console so a
human operator can see which adapters have fresh real-runtime or mock-fallback
proof before launching customer work.
