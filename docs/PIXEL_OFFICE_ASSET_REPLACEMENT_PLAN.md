# Pixel Office Asset Replacement Plan

## Goal

Before any public commercial release, replace temporary Star-Office-UI demo art with an original AgentOps MIS Pixel Office asset pack.

The product should keep the useful interaction pattern:

- visual AI workforce floor
- runtime status map
- task zones
- approval gate
- audit vault
- connector dock

But the commercial asset pack must be original.

## Original Asset Pack Scope

### Agent Roles

- Research Agent
- Coding Agent
- Reviewer Agent
- Ops Agent
- Memory Curator
- Connector Bot
- Audit Bot

### Work Areas

- Control Tower
- Agent Registry Desk
- Task Board Zone
- Runtime Lab
- Tool Room
- Approval Gate
- Memory Library
- Evaluation Room
- Audit Vault
- External Base Dock

### State Animations

- idle
- planning
- researching
- writing
- coding
- executing
- waiting_approval
- evaluating
- syncing
- auditing
- error

### Connector Icons

- OpenClaw
- Hermes
- Agnesfallback
- Notion
- W&B
- Plane
- Docmost
- Mattermost
- n8n

## Suggested Art Direction

- 32px or 48px tile grid.
- Isometric or top-down pixel office, but choose one perspective and keep it consistent.
- Limited palette with clear status colors:
  - green: healthy/running
  - yellow: waiting approval
  - blue: syncing/evaluating
  - red: error
  - gray: idle
- Each agent role should have a distinct silhouette, not only a color swap.
- Status animation should be readable even when compressed in a video.

## Directory Proposal

```text
assets/pixel-office/
  README.md
  LICENSE.md
  sprites/
    agents/
    states/
    connectors/
  tiles/
    floors/
    desks/
    rooms/
  scenes/
    control-tower.json
    workforce-floor.json
  figma/
    export-notes.md
```

## Figma / Generation Prompt Starter

```text
Create an original pixel art office asset pack for an AI workforce management system named AgentOps MIS.
Style: clean 32px tile pixel art, consistent top-down office perspective, no copied third-party assets.
Rooms: Control Tower, Agent Registry Desk, Task Board Zone, Runtime Lab, Tool Room, Approval Gate, Memory Library, Evaluation Room, Audit Vault, External Base Dock.
Characters: Research Agent, Coding Agent, Reviewer Agent, Ops Agent, Memory Curator, Connector Bot, Audit Bot.
States: idle, researching, writing, coding, executing, waiting_approval, evaluating, syncing, auditing, error.
Export transparent PNG sprites and Figma components with clear naming.
```

## Replacement Milestones

1. Demo adapter works with Star-Office-UI in local non-commercial mode.
2. Freeze the AgentOps MIS state vocabulary and scene layout.
3. Create original Figma components for rooms, agents, states and connector icons.
4. Export sprites and scene JSON into `assets/pixel-office`.
5. Replace Star-Office-UI assets in any public-facing build.
6. Add original asset license and attribution.

## Release Gate

Public commercial release is blocked until:

- no Star-Office-UI art asset remains in product bundles
- no LimeZu-derived art asset remains unless its commercial license is explicitly satisfied
- `assets/pixel-office/LICENSE.md` states original ownership/licensing
- product README and marketing pages no longer imply Star-Office assets are ours
