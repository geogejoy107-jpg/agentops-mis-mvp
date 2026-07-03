# Open Source Adoption Packet Spec

## Purpose

This spec turns the open-source adoption boundary into a concrete intake packet.
It is for GitHub branches, downloaded local experiments, UI bases, runtime
adapters, research-lab tools, and Harness-style engineering references that may
help AgentOps MIS but must not become the MIS authority system.

The packet is intentionally small: it should let Codex, Hermes, OpenClaw, or a
remote worker decide whether a branch can be tested locally, kept in an
incubator, wrapped as an adapter/read model, reimplemented first-party, or
rejected.

## Source Inputs

- `docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md`
- `docs/OPEN_SOURCE_MAINLINE_GOVERNANCE_SPEC.md`
- `docs/HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md`
- `docs/HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md`
- `docs/HARNESS_STYLE_AGENTOPS_OPERATING_SPEC.md`
- `docs/research/HARNESS_ENGINEERING_RESEARCH_BRIEF.md`

## Packet Shape

Every adoption packet must include:

- `packet_id`
- `packet_version`
- `source_name`
- `source_url_or_branch`
- `source_kind`
- `license_summary`
- `owner_lane`
- `mis_authority_objects_touched`
- `intake_lane`
- `allowed_operations`
- `forbidden_operations`
- `raw_data_omissions`
- `runtime_requirements`
- `verification_commands`
- `product_claim_limit`
- `merge_decision`
- `rollback_plan`
- `evidence_refs`

`intake_lane` must be one of:

- `research_packet`
- `incubator`
- `adapter`
- `read_model`
- `first_party_migration`
- `reject`

## Required Decisions

Before any branch or base is merged, the packet must answer:

| Decision | Required answer |
| --- | --- |
| Authority impact | Which MIS objects can this influence: workspace, agent, task, run, approval, memory, audit, artifact, report, connector, runtime event, evaluation. |
| Adoption mode | Research only, isolated incubator, adapter, read model, first-party migration, or reject. |
| Runtime proof | Offline smoke, local live Hermes/OpenClaw, local app boot, external service, or no runtime needed. |
| Data boundary | Raw prompts, raw responses, credentials, private messages, full transcripts, local DBs, generated exports, and customer raw documents are omitted. |
| Verification | Exact command(s) that prove the boundary. |
| Product claim | The strongest safe claim allowed after merge. |
| Rollback | How to remove or disable the integration without corrupting MIS ledger state. |

## Harness-Informed Constraints

Harness-style engineering is useful because it separates worker agents, MCP,
policy, services, environments, scorecards, and approvals. AgentOps MIS should
borrow that separation, not the authority.

Required constraints:

- Browser UI is for humans; agents use CLI/API/MCP packets.
- Agents receive typed work/adoption packets, not raw dashboard instructions.
- Policy decisions have an enforcement point and evidence refs.
- Scorecards can grade readiness, but the MIS ledger remains the source of truth.
- Services/environments/connectors are context objects; tasks/runs/approvals are
  MIS authority objects.
- External tools may produce summaries, IDs, hashes, counters, and provenance;
  raw external state is not canonical.

## Merge Gates

A branch or open-source base is not merge-ready until:

- the adoption packet exists in docs, issue, PR body, or ledger artifact;
- the packet names the intake lane;
- the packet declares the MIS authority objects touched;
- unsafe raw-data categories are explicitly omitted;
- verification commands pass locally or the blocker is recorded;
- high-risk external writes are approval-gated or excluded;
- third-party assets/code have license and provenance notes;
- product claim limits are stated in the PR or acceptance record.

## Rejection Conditions

Reject or keep in incubator when:

- it would own workspace/task/run/approval/memory/audit authority;
- it requires committing DBs, tokens, `.env`, generated exports, raw prompts, raw
  responses, private messages, full transcripts, `node_modules`, or `dist`;
- it depends on third-party commercial assets without replacement plan;
- it requires live external services for default local demo;
- it cannot be verified without credentials the user has not explicitly
  authorized;
- it makes product-readiness claims from mock-only evidence.

## Example Packet

```json
{
  "packet_id": "ospkt_star_office_pixel_base_v1",
  "packet_version": "1",
  "source_name": "Star Office UI visual base",
  "source_url_or_branch": "local:Star-Office-UI",
  "source_kind": "ui_reference",
  "license_summary": "demo-only until reviewed and replaced",
  "owner_lane": "pixel_office_visualizer",
  "mis_authority_objects_touched": ["task", "run", "agent"],
  "intake_lane": "read_model",
  "allowed_operations": ["render MIS state", "link to formal MIS pages"],
  "forbidden_operations": ["own task state", "commit third-party art assets"],
  "raw_data_omissions": ["raw prompts", "raw responses", "tokens", "local DB"],
  "runtime_requirements": ["local UI build"],
  "verification_commands": ["python3 scripts/local_open_source_experiment_base_smoke.py"],
  "product_claim_limit": "local demo read model only",
  "merge_decision": "incubate until original assets replace third-party art",
  "rollback_plan": "disable route/link and keep MIS authority pages intact",
  "evidence_refs": ["docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md"]
}
```

## Acceptance

This spec is accepted when:

- `scripts/open_source_adoption_packet_spec_smoke.py` passes;
- the smoke is wired into CI;
- the smoke is listed in the release evidence packet;
- no DB, token, `.env`, cache, `node_modules`, `dist`, generated export, raw
  prompt, raw response, private message, or full transcript is committed.
