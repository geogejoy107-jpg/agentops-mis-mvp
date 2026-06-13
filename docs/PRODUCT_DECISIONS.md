# Product Decisions

## Decision 1: MVP uses mock runtime first

Reason: Real runtimes create engineering noise early: Docker sandbox failures, OAuth, API keys, callback URLs, plugin marketplaces and CLI permissions. The control plane should be validated before runtime adapter integration.

## Decision 2: Run Ledger is a first-class module

Reason: Existing observability tools are useful for traces, tokens and costs, but Agent-MIS needs delegated execution records: who authorized what, which tool produced what side effect, which approval was attached, and which task/agent was accountable.

## Decision 3: Memory is structured, not pure RAG

Reason: Agent-MIS memory must store decisions, commitments, SOPs, risks, failure cases and project context with evidence, confidence, TTL, ACL and review status. A vector store alone cannot support governance.

## Decision 4: High-risk tool calls fail closed

Reason: Tool calls like shell, email, database write and GitHub push can create external side effects. They must request approval before completion.

## Decision 5: No hidden telemetry

Reason: The control plane must be trusted. Any future telemetry must be explicit, documented, scoped, maskable and opt-in.

## Decision 6: Vendor-neutral adapter architecture

Reason: AgentHub, Mission Control, OneManCompany, Paperclip, OpenHands, CrewAI and LangGraph each own different execution patterns. The product moat is not another runtime; it is a common management object model.
