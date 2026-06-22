# Agent Plan — Pixel Office Style Packs and Screenshot Evidence

- Plan ID: `plan-pixel-office-template-cycle-3-2026-06-22`
- Repository: `geogejoy107-jpg/agentops-mis-mvp`
- Development head observed before work: `3fe3c6376f914ecd275786978d8d1e6df3037f98`
- Starting feature branch: `design/pixel-office-template-foundation`
- Starting feature commit: `ebdf8aebd2a0d39eff10e2fcd67be0eb074ddd83`
- Risk level: `low`
- Approval required: `false`
- Human direction: continue the office-only branch, add distinct visual templates, produce real screenshots, and synchronize GitHub plus Notion.

## Task understanding

Extend the reusable Pixel Office foundation without creating a second state system:

1. add two visually distinct original style packs;
2. improve the template selector for five or more styles and keyboard use;
3. add deterministic browser screenshot capture;
4. publish screenshot evidence through GitHub Actions and store durable copies in the repository;
5. update the existing Notion Proposal and Handoff rather than create duplicate project-memory entries.

## Referenced specs and evidence

- `docs/project/PROJECT_STATE.md`
- `docs/project/DECISIONS.md`, especially D-001 through D-006
- `docs/project/BACKLOG.md`
- `docs/project/HANDOFF.md`
- `AGENTS.md`
- `PROJECT_SPEC.md`
- `AGENT_WORKFLOW.md`
- `BASE_INDEX.md`
- `docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md`
- `docs/agent_plans/2026-06-22-pixel-office-template-foundation.md`
- `docs/design/PIXEL_OFFICE_TEMPLATE_FOUNDATION.md`
- Draft PR #13
- Notion Proposal `3876adfdd9208155b95de55becdce6d5`
- Notion Handoff `3876adfdd92081ecaa94d9126d11c8c6`

## Relationship classification

- `updates`: the existing Pixel Office template foundation, Draft PR #13, and the two existing Notion entries
- `duplicate_of`: none
- `supersedes`: none in this cycle
- `conflicts_with`: none confirmed; D-006 remains in force because work stays on the isolated P2 branch

## Proposed files to change

- `ui/start-building-app/src/app/components/pixel/pixelOfficeTheme.ts`
- `ui/start-building-app/src/app/components/pixel/PixelOfficeThemeSelector.tsx`
- `ui/start-building-app/src/app/components/pages/PixelOffice.tsx`
- `ui/start-building-app/scripts/capture-pixel-office-screenshots.mjs`
- `.github/workflows/pixel-office-screenshots.yml`
- `docs/screenshots/pixel-office/*`
- `docs/project/PIXEL_OFFICE_TEMPLATE_HANDOFF_R3_2026-06-22.md`
- Draft PR #13 description
- existing Notion Proposal and Handoff

## Execution steps

1. Add original `harvest-commons` and `orbital-deck` theme packs using only semantic theme tokens and existing first-party CSS renderers.
2. Improve the selector with a responsive grid, roving tab focus, arrow/Home/End keyboard navigation, and style-specific selection accents.
3. Add stable test IDs around the selector and showcase surface.
4. Add a Playwright-based screenshot script and GitHub Actions workflow that starts the local MIS server and Vite UI, captures Chinese-language screenshots, and uploads them as a workflow artifact.
5. Download the generated artifact, inspect screenshots, and commit approved PNG evidence to `docs/screenshots/pixel-office/`.
6. Run required CI on the exact feature head and update PR/Notion evidence.

## Open-source adoption record

- Reference: Playwright
- Borrowed idea: deterministic browser rendering and screenshot capture
- First-party MIS module touched: optional Pixel Office UI and CI evidence only
- Authority boundary preserved: Playwright does not own or mutate workspace, task, run, approval, memory, audit, or delivery state
- Verification: screenshots are generated against the local AgentOps MIS server and checked by GitHub Actions; production code remains React/CSS and first-party MIS data remains authoritative

## Verification plan

- `UI build` must pass on the exact branch head.
- `Backend deterministic smokes` must remain green.
- Screenshot workflow must produce PNG artifacts for the gallery and both new themes.
- Screenshots must visibly differ in palette/shape while preserving the same rooms, agents, metrics, and route controls.
- No backend, database, auth, approval, runtime, redaction, or audit files may change.
- Keyboard selector behavior must compile and expose correct `radiogroup` semantics.
- Branch drift and PR mergeability must be re-read before handoff.

## Rollback plan

Revert the Cycle 3 commits or close Draft PR #13. The development branch remains untouched. Screenshot artifacts and evidence PNGs can be removed independently without changing MIS behavior.

## Plan verification

Verified before implementation against the exact feature head and current development head. Required governance files, the existing theme registry, selector, CI workflow, open-source boundary, and prior Agent Plan were inspected.

Status: `verified`.