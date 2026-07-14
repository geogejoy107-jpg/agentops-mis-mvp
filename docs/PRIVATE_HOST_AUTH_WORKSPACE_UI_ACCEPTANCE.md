# Private Host Auth Workspace UI Acceptance

## Scope

This slice integrates Private Host human authentication into the existing
AgentOps MIS application shell. Authentication is a locked workspace state of
`AppShell`, not a separate page, standalone layout, or second application.

The locked state keeps the product frame recognizable while preventing access
to workspace navigation and authenticated actions. Once the human session is
ready, `AuthGate` returns the existing workspace unchanged.

## Changed Files

- `ui/start-building-app/src/app/components/auth/AuthGate.tsx`
- `ui/start-building-app/src/app/components/layout/AppShell.tsx`
- `ui/start-building-app/src/app/components/layout/Sidebar.tsx`
- `ui/start-building-app/src/app/components/layout/Topbar.tsx`
- `ui/start-building-app/src/app/data/liveApi.ts`
- `agentops_mis_cli/host.py`
- `packaging/macos/install-private-host.sh`
- `scripts/private_host_auth_workspace_ui_smoke.py`
- `scripts/private_host_owner_browser_handoff_smoke.py`
- `.github/workflows/ci.yml`
- `docs/PRIVATE_HOST_AUTH_WORKSPACE_UI_ACCEPTANCE.md`

## UI Contract

### Visual Integration

- `AuthGate` renders the authentication entry inside `AppShell` with
  `locked={true}` and exposes `human-auth-workspace-gate` for bounded UI
  verification.
- The existing Sidebar, Topbar, theme variables, typography, borders, and
  workspace frame remain visible during connection, Owner bootstrap, login,
  and unavailable states.
- Locked and authenticated routes use the same `p-4 lg:p-5` main-content
  spacing. The auth state is laid out as a normal MIS page with a compact page
  header, a primary access panel, and a secondary host-status panel; it is not
  a centered landing-page hero or a separate authentication product.
- Form density, heading scale, panel radius, and status rows match the existing
  Workspace and Admin surfaces. The first-Owner and sign-in flows retain their
  distinct operational copy without decorative marketing content.
- Locked Sidebar items render as disabled non-link rows. They do not navigate
  to workspace or Admin routes before authentication.
- The Topbar communicates the locked state while keeping theme and language
  controls available. Search, workspace switching, notifications, and logout
  are unavailable while locked.

### Responsive Behavior

- The authentication content uses the existing full-height application shell
  on desktop and mobile viewports.
- The main authentication form and local-host boundary content remain a single
  flow at narrower widths and become a two-column layout at the existing `xl`
  breakpoint.
- Form controls use bounded widths and the shell main area remains scrollable,
  so bootstrap and login content do not require a separate responsive page.

### Bilingual And Theme Behavior

- Connection, unavailable, Owner initialization, login, field, validation,
  action, and local-host boundary copy is available in English and Chinese.
- Owner bootstrap and sign-in remain distinct states in both locales.
- Password confirmation is required for Owner bootstrap, and both new-password
  fields preserve the 12-character minimum.
- The language control remains usable while locked, so a user can choose a
  locale before bootstrap or login.
- The theme control remains usable while locked and continues to use the
  existing `enterprise`, `ops`, and `workforce` theme modes.

### Browser-first Owner Setup

- The server continues to require the one-time setup code for the first Owner.
- The managed macOS installer/launcher passes that code to the literal-loopback
  browser in a fragment. Fragments are not included in HTTP requests, and the
  page removes it with `history.replaceState` before the first API request.
- The setup-code field is hidden only when a bounded handoff value was received;
  invalid handoff values are cleared and the manual recovery field returns.
- A same-document `hashchange` is consumed and scrubbed as well as first page
  load, so macOS may safely reuse an already-open Console tab.
- The legacy setup-code API and `agentops host bootstrap-owner --confirm`
  remain available as recovery and headless-host paths.
- The macOS installer prints the local Console URL and opens it after a
  confirmed `--start` installation when a graphical macOS session is
  available. `AGENTOPS_NO_AUTO_OPEN=1` disables that convenience.

## Safety Boundary

- Human browser authentication remains separate from Agent machine
  authentication.
- No-code Owner bootstrap remains rejected even from loopback. A local process
  cannot become Owner merely by reaching the Host port.
- `agentops host open-console` reads the protected code locally, passes the
  handoff to macOS Launch Services over stdin rather than argv, and omits the
  code and full handoff URL from command output.
- Owner creation still uses `BEGIN IMMEDIATE`; concurrent first-owner requests
  produce one Owner Session and one fail-closed conflict.
- Terminal bootstrap failures clear the in-memory handoff. Only locally
  correctable username/password-strength errors retain it for the next submit.
- Locked navigation does not expose authenticated workspace routes through
  clickable Sidebar links, and the locked Topbar does not expose logout.
- The smoke is static and read-only. It does not start a Host, mutate a ledger,
  inspect or print credentials, read a database, or invoke Hermes, OpenClaw, or
  another runtime.
- No credential, setup code value, cookie, Session value, CSRF value, database,
  private message, full transcript, raw prompt, or raw response is recorded by
  this acceptance document or its smoke output.
- Backend Session, CSRF, Origin, role, and workspace enforcement remain the
  authoritative security boundary; the locked UI is defense in depth and user
  guidance, not a replacement for server enforcement.

## Verification

Commands run against the current worktree on 2026-07-14:

```bash
python3 scripts/private_host_auth_workspace_ui_smoke.py
python3 scripts/private_host_owner_browser_handoff_smoke.py
python3 scripts/human_browser_auth_smoke.py
python3 scripts/private_host_owner_bootstrap_cli_smoke.py
cd ui/start-building-app && npm run build
git diff --check
```

The static smoke passed all 22 checks and returned JSON with `ok: true`, no
failures, and exit code 0. It verifies locked-shell reuse, the authentication
gate marker, Workspace-style access and host-status panels, shared content
spacing, bilingual Owner bootstrap/login copy, password confirmation and minimum
length, locked non-link Sidebar items, persistent theme/language controls,
logout omission while locked, and the setup-code-authorized browser handoff
projection.

The browser-handoff integration smoke passed against a temporary Host and
database. It proved that no-code bootstrap is rejected, setup-code bootstrap
creates the Owner, audit metadata omits credentials, the CLI uses `osascript -`
stdin rather than argv, and the frontend scrubs and bounds the fragment. The
existing browser-auth and CLI bootstrap smokes also passed.

The Vite production build passed with 2,280 modules transformed. Vite reported
the existing large-chunk advisory for the main bundle; this is a performance
follow-up and did not fail this scoped acceptance. The final `git diff --check`
also passed.

An isolated production build was visually exercised at narrow and desktop
viewports in Chinese and English across `ops`, `workforce`, and `enterprise`
themes. A temporary browser completed Owner bootstrap, entered Workspace,
logged out, and signed in again without reading or changing the installed Host
database.

The final production build also exercised installer-style same-document
handoff against a fresh temporary Host: the Console first rendered its manual
setup-code field, then received the fragment on the already-mounted page,
scrubbed the address bar, hid the manual field, displayed the bounded pairing
receipt, created the Owner, and entered the existing Workspace. No installed
Host database or real credential was used.

## Security Review Closure

The final review found no Critical or High issue and no path for a process that
can merely reach the loopback port to create an Owner without the setup code.
It identified one medium issue in the initial implementation: a reused browser
tab could receive a same-document fragment after `AuthGate` had mounted. The
final implementation consumes and removes `hashchange` handoffs and the browser
exercise above covers that path. It also clears the in-memory handoff after
terminal request errors while retaining it only for locally correctable
username or password-strength input. A late handoff received after bootstrap
also gets scrubbed without being retained in login or ready state.

The same-Unix-user boundary remains explicit: a malicious process running as
the Host account may read files owned by that account despite `0600`. This is a
host trust assumption, not a browser bootstrap authority granted by the port.

## Known Limitations

- Owner bootstrap still depends on the protected one-time setup code. The
  graphical path removes manual copying; it does not weaken that authority.
- The real installed Private Host has not yet been upgraded to a build
  containing this worktree slice. Local static and production-build evidence is
  not installed-product evidence.
- Owner bootstrap/login and the real Hermes or OpenClaw runtime closure still
  require user input. No unattended automation or machine credential may
  substitute for those human actions.
- This acceptance does not claim a physical second-device browser pass,
  authenticated artifact download, disconnect/reconnect proof, logout-denial
  receipt, or completed Owner-approved real-runtime loop.
