# Approval Semantics Boundary

## Contract

AgentOps MIS has two approval semantics. They share the `approvals` ledger table
but do not mean the same operational thing.

## Ledger / Delivery / Review Approval

Most approvals are governance records. They mean a human/admin reviewer made a
decision about a task, delivery, enrollment request, memory promotion, agent
plan, Commander synthesis, or other review item.

This approval type:

- records `approved` or `rejected` in the MIS ledger;
- writes audit/runtime evidence;
- may unblock delivery, token issuance, plan status, or review progression;
- does not by itself prove that an exact provider side effect executed;
- must not be described as exact tool-action resume.

## Prepared-Action Approval

Prepared-action approval is stricter. It exists only when a
`prepared_actions` row is created before the side effect.

This approval type must include:

- normalized action arguments;
- target resource;
- policy version;
- checkpoint;
- idempotency key;
- immutable `action_hash`.

Approving this gate authorizes a later exact resume. Approval still does not
perform the side effect directly from the decision itself. Execution evidence
is valid only after the prepared action is resumed exactly once and the ledger
records `consumed_at` plus the provider side-effect id or equivalent proof.

## UI Wording Rule

Browser UI may say `Approve`, `Reject`, `Approval`, `Decision`, `Ledger
approval`, or `Delivery approval`.

Browser UI must not imply that a generic approval button performs or resumes an
exact tool action. Phrases such as `exact resume`, `resume exact action`,
`execute once`, or `perform provider side effect` are allowed only when the
screen is explicitly showing a prepared action, action hash, checkpoint, and
resume contract.

## Product Claim Rule

Safe v1.5 claim:

> High-risk external side effects are routed through prepared actions. Generic
> approvals remain ledger, delivery, enrollment, review, or plan decisions.

Unsafe claim:

> Every approval in the UI resumes the exact tool action.

The unsafe claim is not true and must not appear in public demo, README, UI, or
release notes.
