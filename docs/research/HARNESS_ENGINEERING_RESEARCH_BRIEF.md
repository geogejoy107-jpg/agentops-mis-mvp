# Harness Engineering Research Brief

## Research Object

"Harness engineering" can mean two related things:

1. Harness the company/product family: an AI-native software delivery platform
   with CI/CD, approvals, policy, environments, connectors, developer tooling,
   and open-source developer-platform components.
2. The broader engineering pattern: building a governed delivery harness around
   fast-moving AI/software agents so they can plan, execute, verify, approve,
   and ship without raw, unsafe tool access.

This brief studies both meanings and translates them into AgentOps MIS product
constraints.

## Sources Checked

- Harness Open Source GitHub repository:
  `https://github.com/harness/harness`
- Harness Open Source landing page:
  `https://www.harness.io/open-source`
- Harness Policy As Code docs:
  `https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/`
- Harness blog/product posts about AI-native delivery, Cursor, VS Code, MCP,
  Software Delivery Knowledge Graph, and approvals:
  `https://www.harness.io/blog`
- Harness June 30, 2026 press release for Autonomous Worker Agents:
  `https://www.harness.io/press-and-news/harness-launches-autonomous-worker-agents-for-software-delivery`
- OpenAI February 11, 2026 article on harness engineering with Codex:
  `https://openai.com/index/harness-engineering/`
- Hacker News launch discussion for Harness Open Source:
  `https://news.ycombinator.com/item?id=41647665`
- DevOps.com June 30, 2026 coverage of Harness autonomous AI agents:
  `https://devops.com/harness-adds-autonomous-ai-agents-to-automate-devops-workflows/`

## Findings

### 1. Harness Open Source Is A Developer Platform, Not Just CI

Harness describes its open-source project as an end-to-end developer platform
covering source control, CI/CD pipelines, hosted developer environments, and
artifact registries. The public open-source page emphasizes build/test/deploy,
integrations, migration from existing code hosts and CI tools, and artifact
management.

Implication for MIS:

AgentOps MIS should treat "developer platform" as a compound product surface,
not a single dashboard. Our local MVP needs:

- code/worktree context,
- task/work package context,
- pipeline/smoke context,
- artifact/report context,
- approval/audit context,
- runtime/agent context.

These should be connected by MIS IDs and evidence hashes, not stitched by UI
copy alone.

### 2. Harness Uses Governance And Policy As Platform Primitives

Harness Policy As Code uses OPA/Rego to enforce governance across platform
entities and processes. The key product lesson is not "use OPA immediately";
it is that policy must be a first-class gate in the delivery system.

Implication for MIS:

AgentOps MIS should keep policy checks first-party for v1.x, but structure
them like a policy system:

- policy id/version,
- target entity,
- normalized action arguments,
- decision,
- evidence refs,
- enforcement point,
- audit output.

OPA/Cedar/Rego can remain future adapter references, not local MVP dependencies.

### 3. Harness Is Moving AI From Coding Into Delivery

Harness positions AI delivery around CI/CD execution, security validation,
approvals, deployments, and operational insight. Its editor integrations and
MCP messaging emphasize that agents need delivery context, not just code.

Implication for MIS:

The MIS agent interface should not be "browser UI for bots." Agents need:

- `agentops operator loop-supervision --work-packet`,
- task-bound knowledge evidence packets,
- Agent Plan and plan-evidence manifests,
- scoped Agent Gateway tokens,
- runtime trust/readiness gates,
- approval/prepared-action walls,
- evidence reports and action receipts.

This supports the existing Agent Gateway / CLI / MCP direction.

### 4. The Knowledge Graph Idea Maps Strongly To MIS

Harness says its Software Delivery Knowledge Graph connects pipelines, services,
deployments, approvals, scans, environment states, feature flags, infrastructure
changes, cost signals, and rollbacks as typed, relationship-aware context for
agents.

Implication for MIS:

AgentOps MIS should build a local "work delivery graph" from existing authority
objects:

```text
workspace -> agent -> task -> agent_plan -> run -> tool_call
        -> runtime_event -> evaluation -> artifact -> approval -> audit
```

The graph should be a read model over MIS ledgers, not a new authority store.
For v1.x, SQLite read models and explicit JSON packets are enough.

### 5. Raw API Access Is Not Enough For Agents

Harness argues that raw API/MCP access makes agents infer endpoint order and
entity relationships, which creates reliability risk. The remedy is a typed
delivery context and action/workflow abstractions.

Implication for MIS:

Do not expose only raw CRUD endpoints to Hermes/OpenClaw/Dify agents. Prefer:

- work packets,
- phase commands,
- action plan,
- launch packet,
- readiness packet,
- evidence packet,
- approval/resume packet.

This directly supports finishing the OSBI loop/work-packet line before adding
more UI or commercial features.

### 6. Harness Open Source Can Inspire But Not Replace MIS

Harness Open Source can run on a small server/laptop and bundles repo hosting,
CI/CD, dev environments, and artifact registry. It is useful as a product
reference for "local/self-hostable delivery platform."

Do not replace MIS with it because:

- MIS authority objects are human-AI work objects, not only software-delivery
  pipeline objects.
- MIS needs memory governance, Agent Plan binding, Approval Wall exact resume,
  runtime connector trust, and customer delivery evidence.
- Harness/Gitness/CI can be a connector/runtime or reference platform, not the
  AgentOps MIS source of truth.

### 7. Harness Worker Agents Reinforce The Control-Plane Boundary

Harness announced Autonomous Worker Agents on June 30, 2026 as a software
delivery layer for work between code and production, with an agent marketplace
and bring-your-own-model support. Treat this as a market signal: customers will
expect AI workers to connect to existing delivery systems, policies and model
choices.

Implication for MIS:

AgentOps MIS should not hard-code one runtime or model path. The product needs
stable control-plane contracts:

- agent registration and scoped enrollment,
- task pull/claim/start/writeback,
- compact work packets for machine callers,
- prepared actions for write/external side effects,
- runtime trust/readiness gates,
- evidence/audit/report artifacts independent of the worker runtime.

This supports using Hermes, OpenClaw, Dify or a future Harness-like connector
as workers/adapters while keeping MIS task/run/approval/memory authority local.

### 8. Harness Engineering Is A Repository And Runtime Discipline

OpenAI's harness-engineering writeup frames the engineer's job as specifying
intent, building feedback loops, making repository knowledge legible, enforcing
architecture/taste and changing merge philosophy for high-throughput agent
work.

Implication for MIS:

The AgentOps MIS repo should keep treating specs, runbooks, smoke tests,
acceptance docs, release evidence packets and operator work packets as product
surface area. Agents should receive small, typed, verifiable packets instead of
long chat history or broad raw API access.

## Candidate Ideas To Borrow

| Harness pattern | AgentOps MIS adaptation | v1.x priority |
| --- | --- | --- |
| Software Delivery Knowledge Graph | Local work delivery graph/read model over MIS ledgers | High |
| AI editor/agent delivery context | `agentops operator ... --work-packet` plus MCP resources | High |
| Policy as Code | First-party policy decisions with policy id/version/evidence refs | Medium |
| Inline approvals | Approval Wall and action receipts on task/run surfaces | High |
| Autonomous worker agents | Agent Gateway worker loop plus adapter readiness/trust gates | High |
| BYO model/runtime | Runtime connector registry with scoped trust policy | High |
| Pipeline/entity status | Worker/run/eval/readiness cards in command center | High |
| Artifact registry | MIS artifact table with URI/hash/provenance, not raw blobs | Medium |
| Migration from existing tools | Connector import/export adapters, never authority replacement | Medium |
| Self-hostable developer platform | Local-first deployment profile and installer later | Medium |

## Anti-Patterns To Avoid

- Giving agents broad raw API access and asking them to infer workflow order.
- Letting a CI/CD platform own MIS task/run/approval truth.
- Treating a hosted delivery platform as the local MVP architecture.
- Equating "green CI" with product-useful real-agent operation.
- Exposing raw logs, prompts, responses, credentials, or customer documents as
  agent context.
- Replacing first-party Approval Wall semantics with generic approval buttons.

## Product Recommendation

The next AgentOps MIS slices should prioritize the OSBI loop/work-packet line:

1. Rebuild remaining `codex/osbi-v1-1-mainline` work-packet/decision/driver
   slices on latest main.
2. Add a local work-delivery graph read model only after existing packets are
   stable.
3. Expose Harness-style delivery context through CLI/API/MCP packets, not by
   adding a second dashboard authority.
4. Keep commercial hosted-stack work as future/reference until local-first
   AgentOps MIS can reliably run real Hermes/OpenClaw tasks end to end.

## Unknowns

- I did not run Harness Open Source locally in this slice.
- I did not verify Harness licensing terms beyond public repository/product
  pages.
- I did not test Harness MCP/VS Code/Cursor integrations.
- Some 2026 Harness AI-agent material is product/blog coverage rather than
  source-code evidence, so it should be treated as product-direction evidence,
  not proof of implementation detail.
