# Pixel Office Screenshot Evidence

This directory indexes deterministic screenshot evidence for the reusable Pixel Office template foundation.

## Cycle 3

- Feature branch: `design/pixel-office-template-foundation`
- Screenshot code head: `9007684220ddc72383bef37e7ba64c6608bf792c`
- GitHub Actions workflow: `Pixel Office Screenshots`
- Workflow run: https://github.com/geogejoy107-jpg/agentops-mis-mvp/actions/runs/27958293187
- Artifact ID: `7794557026`
- Artifact name: `pixel-office-screenshots`
- Artifact digest: `sha256:7866e8b361c205542088e24dff346ea988d4bf2215a269c33bea4e6b0605979b`
- Retention: 90 days from 2026-06-22

## Captured files

| File | Evidence |
| --- | --- |
| `pixel-office-theme-gallery.png` | Five-template selector gallery in Chinese |
| `pixel-office-harvest-commons.png` | Full desktop Pixel Office using the bright rural `harvest-commons` pack |
| `pixel-office-orbital-deck.png` | Full desktop Pixel Office using the high-contrast `orbital-deck` pack |
| `manifest.json` | Route, capture time and captured-file list |

## Capture contract

The workflow:

1. checks out the pull-request source;
2. starts the local AgentOps MIS server with real external writes disabled;
3. starts the Vite UI;
4. opens `/workspace/pixel-office` with Chinese locale;
5. switches the registered theme through the real selector;
6. renders with reduced motion for deterministic output;
7. uploads PNG files as a GitHub Actions artifact.

Screenshots are presentation evidence, not an authority ledger. The same tasks, runs, approvals, memory, audit signals and formal route targets remain authoritative in AgentOps MIS.

## Remaining evidence

- compact/mobile screenshots;
- keyboard-navigation browser assertions;
- final-development-head synchronization and screenshot refresh before merge.
