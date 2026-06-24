# Agent Plan — Dual Agent Art Assets v0

- Plan ID: `plan-dual-agent-art-assets-v0-2026-06-24`
- Repository: `geogejoy107-jpg/agentops-mis-mvp`
- Development branch verified: `codex/agent-gateway-kb-demo`
- Development commit verified: `896ee1aa288f2733aa9c147ced6a9c2d5c8622d0`
- Execution branch: `design/spatial-research-district-art-v1`
- Starting execution commit: `33fccf0f799383eafcb1b195af2886319cd61935`
- Risk level: `low`
- Approval required: `false`
- Human direction: stop overlaying the compact glyph on top of a different character. Prototype two genuinely separate Agent art systems: a cozy life-sim character and a compact industrial unit inspired by open-source production methods.

## Current milestone and scope boundary

The canonical development line remains `READY_TO_MERGE`. This is isolated P2 visual research and does not displace P0 keep-green gates or P1 module/knowledge work. It changes no backend, database, auth, approval, runtime, redaction, external-write, or audit semantics.

## Problem statement

The previous Advanced prototype mixed two incompatible representations:

1. a full-body pixel person;
2. a small geometric identity crest drawn above or beside that person.

That made the crest look like a task/status badge rather than a complete Agent art style. The two prototype tracks must now be independent:

- **Cozy Life-Sim Agent** — the Agent is a full character. Identity is embedded in silhouette, hair, clothing, carried tool, and animation. No detached identity badge is drawn on the character.
- **Industrial Unit Agent** — the Agent is the compact machine/glyph itself. The whole unit silhouette communicates identity; it is not attached to a human sprite.

Status and risk remain separate operational channels in both tracks.

## Open-source reference study

### Cozy character pipeline

Reference: `BenCreating/LPC-Spritesheet-Generator`.

Borrowed methods only:

- split spritesheets by animation (`walk`, `idle`, `cast`, etc.);
- compose body, clothing, hair, and equipment as ordered layers;
- use named palette ramps rather than arbitrary recoloring;
- retain per-layer authorship, license, and source metadata;
- use compatibility tags and exclusions for modular parts.

The repository code is MIT, while individual art layers have varying CC-BY-SA, OGA-BY, GPL, or more permissive licenses. No LPC image is copied into AgentOps MIS. The output assets in this plan are new project-authored pixels.

### Industrial compact unit pipeline

Reference: `Anuken/Mindustry`.

Borrowed methods only:

- semantic asset directories and modular layers;
- source sprites transformed into runtime/UI variants by a packer;
- outline generation and controlled padding;
- palette-indexed team/accent regions;
- separate chassis, cell/core, heat/effect, leg/tread/tool regions;
- one content identity mapped to one stable generated UI icon.

Mindustry is GPL-3.0. No Mindustry code or image is copied into AgentOps MIS. This plan implements original geometry and project-owned assets from the observed production principles only.

## Relationship classification

- `updates`: Spatial Agent Identity v0 and Spatial Research District Art v1
- `supersedes`: full-body character plus detached crest overlay
- `duplicate_of`: none
- `conflicts_with`: none confirmed

## Deliverables

1. `cozy-research-agent-v0.png` — transparent 32×48-frame spritesheet with four directions and four walk/idle phases.
2. `industrial-agent-units-v0.png` — transparent atlas of six original 32×32 compact unit Agents.
3. Enlarged contact-sheet previews for visual review.
4. Machine-readable manifests with frame geometry, palette, role mapping, provenance, and license.
5. A deterministic generator script that reproduces both assets without external images.
6. A smoke test that verifies dimensions, transparency, unique silhouettes, no badge overlay, and project-owned provenance.
7. A design note recording what was learned and what was deliberately not copied.

## Acceptance criteria

- The cozy character has no crest/badge hovering above, beside, or on the upper-right corner.
- Cozy identity is recognizable through body silhouette, hair, coat/scarf colors, satchel/notebook, and movement frames.
- The industrial track contains no human body; each complete machine silhouette is itself an Agent.
- At least six industrial role silhouettes are visibly distinct at 32×32.
- Both assets use integer pixel grids, nearest-neighbor previews, transparent backgrounds, and no anti-aliasing.
- All production assets are generated from repository-owned geometry and palettes.
- Manifests explicitly state `PROJECT_OWNED` and `first_party` provenance.
- No remote image URL, Stardew Valley asset, Mindustry asset, LPC image, proprietary logo, or marketplace sprite is included.

## Verification plan

- Run the deterministic asset generator twice and compare SHA-256 hashes.
- Verify image dimensions, alpha channel, frame count, palette count, and role coverage.
- Verify the industrial silhouettes are unique.
- Verify cozy frames contain no detached pixels in the badge zone above/right of the body bounding box.
- Run existing Spatial Agent identity and Spatial OS manifest smokes after integration.
- Create real PNG evidence and visually inspect enlarged nearest-neighbor previews.

## Rollback

Delete the two asset folders, generator, manifests, and smoke. The existing Basic/Lite and current shared identity contracts remain unchanged.

## Plan verification

Verified before asset generation:

- exact repository, current development commit, feature branch, and starting feature commit were read from GitHub;
- current Project State, Decision Log, Backlog, Handoff, AGENTS, Project Spec, Agent Workflow, and Base Index were reviewed;
- official Mindustry repository, sprite directory structure, GPL-3.0 license, image packer, generated outline/team/UI-icon workflow, and unit layer naming were inspected;
- LPC generator README and body definition were inspected for animation splitting, layer ordering, palettes, compatibility metadata, and per-item licensing;
- the plan is first-party visual-method adoption only and creates no new MIS authority subsystem.

Plan status: `verified`.
