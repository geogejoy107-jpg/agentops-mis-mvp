# Pixel Office UI Brainstorm, Agent Run Report

Date: 2026-06-15

Scope: use the current local AgentOps MIS and connected local agents to brainstorm how the Pixel Office page should become a useful AgentOps front stage instead of a decorative agent room.

## Runtime Status

Verified local services:

- AgentOps MIS API: `http://127.0.0.1:8787`
- Pixel Office room: `http://127.0.0.1:19000/workspace`
- MIS React workbench: `http://127.0.0.1:19001/workspace`

Verified MIS runtime health:

- OpenClaw: ready
- Hermes default gateway on `8642`: unavailable
- Agnesfallback local runtime: available as a Hermes-compatible local probe path
- Notion: dry-run only in current service environment

Verified MIS metrics snapshot:

- Agents total: 28
- OpenClaw cron runs imported: 6010
- Pending approvals: 4
- Running tasks in status distribution: 13
- Waiting approval tasks in status distribution: 12
- Failed quality gates: 3688

## Agents Used

OpenClaw agents were invoked with a structured UI brainstorming prompt. The prompt excluded credentials, private messages, and full transcripts.

- OpenClaw `main`: completed successfully. Run id: `93b00fa1-bbcc-49b8-b81e-32348d2652be`
- OpenClaw `builder`: completed successfully. Run id: `7db7982c-9a7b-4c2b-be73-54506c9cf869`
- OpenClaw `orchestrator`: started DOM/API-oriented analysis but timed out before final recommendations. Run id: `a96c26e0-8883-48c9-abea-caef8550f407`
- Agnesfallback local runtime: completed a Hermes-compatible synthesis pass with explicit local `--yolo` for this manual task only. This does not change safe demo defaults.

## Consensus

The agents converged on one main product direction:

Pixel Office should not be an agent name-card wall. It should be the live front-stage command room for AgentOps work. The backend MIS remains the detailed ledger, configuration, audit, and analysis console.

## P0 Product Changes

1. Replace agent cards with room/work cards.
   Each room should represent a work container: task title, bound agent, state, current action summary, quality gate, and quick actions.

2. Group rooms by operational state.
   Suggested groups: executing, waiting approval, blocked/error, idle. The demo should make active and blocked work visible within seconds.

3. Add a right-side room detail panel.
   Clicking a room should open task context, recent run events, output preview, quality gate result, and approval actions.

4. Bring approvals into the front stage.
   Pending approvals should be visible in the room and in a bottom status bar. Approve/reject should be possible without jumping into the full admin console.

5. Add a bottom operations bar.
   Show pending approvals, runtime health, newest alerts, and current active agent count. This makes the page feel alive and useful during recording.

6. Keep full history and configuration in the backend.
   Full run ledger, cron management, model/provider settings, memory review, audit log search, Notion export, and business analysis should remain in the MIS admin workbench.

## Which Agents Should Continue Running

For this UI optimization task:

- Continue with OpenClaw `main` for product framing, demo story, and classroom presentation value.
- Continue with OpenClaw `builder` for concrete frontend component and data-flow implementation advice.
- Retry OpenClaw `orchestrator` only with a shorter prompt when architecture routing or multi-agent coordination is the question.
- Use Agnesfallback as the Hermes-compatible local reviewer/summarizer while the default Hermes gateway remains unavailable.

For the product UI itself:

- Prioritize agents with running work, pending approvals, or recent failures.
- De-emphasize idle agents with no recent runs.
- Highlight agents with low success rate or high recent failure count.
- Surface approval-required agents because they are the clearest human-in-the-loop demo.

## Frontend and Backend Boundary

Pixel Office front stage should answer:

- What is happening now?
- Which agent is doing it?
- Is it stuck, waiting approval, or failing?
- What can I approve, inspect, retry, or stop immediately?

MIS backend should answer:

- What happened historically?
- Which runs, tool calls, evaluations, and audits prove it?
- How are agents, cron jobs, connectors, memory, and exports configured?
- What should be exported to Notion or reported in the final presentation?

## Demo Shots

1. Multi-agent overview.
   Open `19000/workspace`, show executing, waiting approval, and error rooms. Explain that the pixel office is not decoration: it is reading MIS state and showing active work.

2. Approval flow.
   Click a waiting-approval room, open the detail panel, show task context and approval controls, then approve/reject. The key line: human-in-the-loop control happens in the work room.

3. Failure to ledger.
   Click a failed room, show error summary and quality gate, then jump to the MIS admin run ledger for the full audit trail. The key line: the front stage is for action, the backend is for proof.

## Implementation Slice

Smallest useful next slice:

1. Add a room grouping model on top of the existing live `/agents` data from Star Office.
2. Render `RoomCard` states with task title, agent, status badge, run count, success rate, and failure count.
3. Add a right-side `RoomDetailPanel` populated from MIS agent performance and recent run data.
4. Add a bottom status bar using `/api/dashboard/metrics`.
5. Make admin links open the matching MIS detail pages for deep audit.

This gives a real demo without redesigning the entire visual system.
