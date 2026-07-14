# Private Host Release Candidate Acceptance

Status: preview.19 published and installed; the existing Workspace now owns browser-first account setup and Host identity, while Owner completion, current-package Runtime completion, and physical second-device gates remain open

This matrix is the requirement-by-requirement completion record for
`LOCAL_HOST_REMOTE_CONSOLE_SPEC.md`. A deterministic smoke proves only the
bounded behavior it names. Cross-device and real-runtime rows require fresh
physical evidence and cannot be closed by mock output.

## Functional Acceptance Matrix

| # | Requirement | Current evidence | Status |
|---|---|---|---|
| 1 | Clean Host installs from a versioned asset without cloning | GitHub prerelease `v1.6.0-private-host-preview.19` publishes a no-repository bootstrap plus archive/checksum assets from exact commit `ac69d8c`. Exact-head push/PR CI, bundle and release-consumer smokes, checksum verification and the same-Mac preview.18-to-preview.19 upgrade passed. A receipt from another physical Mac remains missing. | Passed locally; external evidence required |
| 2 | `agentops host start` serves production UI/API/ledger/knowledge and actionable worker state | `PRIVATE_HOST_LIFECYCLE_ACCEPTANCE.md`, `PRIVATE_HOST_AUTH_WORKSPACE_UI_ACCEPTANCE.md`, `PRIVATE_HOST_WORKER_OWNERSHIP_ACCEPTANCE.md` and bundle smoke cover installed CLI, production UI, browser-first Owner setup in the existing Workspace, init, doctor, start/status/stop, Runtime readiness and fail-closed duplicate Worker ownership. | Passed locally |
| 3 | Dependency-free second computer opens private HTTPS console and authenticates | preview.19 is live through private Tailscale HTTPS on port 8443, Funnel is disabled, and the Workspace is ready. The installed `open-console` can perform a scrubbed setup-code handoff without output disclosure. Host status remains `bootstrap_required`; Owner completion and physical second-device browser login remain human gates. | Host side passed; external evidence required |
| 4 | Unauthenticated UI/API data fails closed | `human_browser_auth_smoke.py`, `private_host_owner_browser_handoff_smoke.py`, artifact-download smoke and lifecycle acceptance cover anonymous denial, setup-code authority, role/session separation and CSRF/Origin checks. | Passed locally |
| 5 | Remote task, observation, approval, evaluation/audit review and approved artifact download | Customer dispatch and ledger views exist; Audit and Memory use live APIs; memory decisions write through the approver route; approved artifact download is Session/workspace/approval checked and audited. A second-device end-to-end receipt remains open. | Partial |
| 6 | Explicitly confirmed Hermes/OpenClaw task writes complete bounded evidence | `PRIVATE_HOST_REAL_RUNTIME_CLIENT_ACCEPTANCE.md` records completed Hermes and OpenClaw async runs from preview.4. preview.19 is running exactly one explicitly confirmed Worker for each adapter. Runs `run_gw_242eac97293e` and `run_gw_23bb6ba9f13e` remain approval-gated; no human Owner has approved current-package execution. | Passed previously; exact-current completion pending |
| 7 | Console disconnect does not stop Host Worker or lose task | `PRIVATE_HOST_CONSOLE_DISCONNECT_ACCEPTANCE.md` proves real Hermes/OpenClaw jobs completed after their first Host-local Session clients were discarded, then were read through fresh Owner Sessions. Physical browser/tailnet loss remains missing. | Passed on Host; external evidence required |
| 8 | Host restart preserves ledger and knowledge state | `PRIVATE_HOST_RESTART_PERSISTENCE_ACCEPTANCE.md` covers Session, task and a 194-document local Markdown/FTS index remaining searchable after managed restart. | Passed locally |
| 9 | Backup and restore pass on isolated database | `PRIVATE_HOST_BACKUP_RESTORE_ACCEPTANCE.md` covers strict manifest/hash/schema/integrity/foreign-key checks, atomic replacement and access revocation. | Passed locally |
| 10 | Release/Git contain no credentials, DB, raw prompt/response or generated dependencies | Bundle forbidden-member scan, clean-clone tracked-file selection, release-consumer smoke and secret boundaries pass. Sample exports, DB, `.env`, `node_modules`, caches and temporary browser fixtures were excluded from commits and Release assets. Git does not track `dist`; the Release intentionally packages only the prebuilt production UI so a customer Host needs no Node runtime. | Passed locally; repeat at RC |

## Superseded Preview

- Tag: `v1.6.0-private-host-preview.1`
- Exact commit: `5fdd5b59508bca567b7a7df4678de9114f25aca2`
- Push and pull-request CI: passed at the exact commit
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.1`
- SHA-256 manifest: `a7889a858801b4ef0fc4579d0f9e796b4b597395536417c2a9ac32497cd344ad`
- Tar archive: `e68bfae7e29a4f7356db4b162a965d29579ccaf2c9fc2a5ba3584c7440966e0a`
- Zip archive: `624e4ec9cb954bcf208ebf5840d535b07142a1557ba61be649de25f22e97b43f`

This preview is not the final Release Candidate until the physical-device gates
below pass. It is also not the current install candidate after the source
shadowing defect was found. Corrected preview.2 repeats the exact-head build,
checksum, Release download, and clean-install gates below.

## Superseded Preview 2

- Tag: `v1.6.0-private-host-preview.2`
- Exact commit: `39cf68f3ea8799a6f1c154c64c4e0aaaa8ad0e49`
- Push CI: passed at the exact commit (`29191253174`)
- Pull-request CI: passed at the exact commit (`29191254687`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.2`
- SHA-256 manifest: `56e70c7f38d447ee5a60bed92a29ad7ebb7a7ba423b9239636ffed37f034a14a`
- Tar archive: `64840ffb75dab96ff24a0d8d5c565592d94eac26605286e2c6597eac1661795a`
- Zip archive: `380731159b45ea454d04a92933d5ebbcd608f668cc5fd3328bdab855873df714`

preview.2 passes the Release-download/install gate and adds the browser device
checklist plus Owner-only Host authority receipt. Exact-package Hermes/OpenClaw
dogfood then proved the Worker could claim tasks but could not pass Agent Plan
verification because four authority specs were absent from the archive. The
gate failed closed before model invocation. preview.2 is therefore superseded;
preview.3 provides both packaged Agent Plan verification and fresh real
Runtime execution before physical second-device acceptance proceeds.

## Superseded Preview 3

- Tag: `v1.6.0-private-host-preview.3`
- Exact commit: `642471f571d9943f9c4c217b3912e32f6728dfce`
- Push CI: passed at the exact commit (`29191745565`)
- Pull-request CI: passed at the exact commit (`29191747123`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.3`
- SHA-256 manifest: `2b0535427f14178a32c4bd66620da8c7dd9391cda32031134a15de5ce16909fc`
- Tar archive: `01a08c8c6ebf4d796b40003eb2deddfcf4f17b5ab439b762868a2bdfe1f2906d`
- Zip archive: `80b2898b665710771458cf33eead662d96c9a862f190ad4c9a3e24a8bbb50987`

preview.3 packages the four Agent Plan authority specs omitted from preview.2.
The installed-package smoke now starts an isolated Private Host and verifies
plan creation, plan verification, run start, evaluation, artifact and verified
plan-evidence manifest creation. A separate exact-package live pass completed
fresh Hermes and OpenClaw customer tasks and generated Owner-approved Host
authority receipts. GitHub download/checksum/install/start/route/stop passed in
an isolated directory. Physical tailnet, second-computer and another-Mac gates
remain open. preview.4 supersedes it with durable async disconnect and
idempotent launch acceptance.

## Superseded Preview 4

- Tag: `v1.6.0-private-host-preview.4`
- Exact commit: `1b8f2b9469105ce826e551b5e83fd9d5f0656bff`
- Push CI: passed at the exact commit (`29193325930`)
- Pull-request CI: passed at the exact commit (`29193327505`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.4`
- SHA-256 manifest: `84bf6ca00ffc9e5a45be2cc91d47ed6bbc147f6b05e20d49eb46b4df9f8ccc1b`
- Tar archive: `163c0fcb78e39072c20cb3053310a2087218ad01e6627e0e3678265bd947c953`
- Zip archive: `0e5321e9cad1b07c912e12c331144ec146f630fc35f2680c7fc08d423f1027b3`

preview.4 adds idempotent async customer-worker submission, SQLite
compare-and-swap launch leases, concurrent single-job/single-run proof,
durable queued-reservation recovery, and workspace-scoped job reads and
mutations. Exact-package Hermes and OpenClaw jobs completed after the first
Host-local Session clients were discarded; fresh Owner Sessions then approved
the deliveries and verified Host authority receipts. GitHub
download/checksum/install/start/route/stop also passed in an isolated directory.
Physical tailnet, second-computer, physical disconnect and another-Mac gates
remained open. preview.5 and preview.6 supersede this package.

## Superseded Preview 5

- Tag: `v1.6.0-private-host-preview.5`
- Exact commit: `d281adae3ef97229c1861b27f2e559bb7edd1fe3`
- Push CI: passed at the exact commit (`29194637789`)
- Pull-request CI: passed at the exact commit (`29194639170`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.5`

preview.5 hardened Tailscale URL readiness, Serve ownership, Funnel blocking,
DNS drift and graceful restart behavior. A real upgrade then found that the
persistent production UI path remained pinned to preview.4, so preview.6
supersedes it.

## Superseded Preview 6

- Tag: `v1.6.0-private-host-preview.6`
- Exact commit: `961740e6609d61fdd1ba2f7c551e34df714fdf32`
- Push CI: passed at the exact commit (`29195231194`)
- Pull-request CI: passed at the exact commit (`29195232345`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.6`
- SHA-256 manifest: `1542921dd18bfeeb8b07aef3fcc81157cd3cefcc9c1ccbdf03de165044f60f1d`
- Tar archive: `efa4596284160f961b3d5846a311236e23314a5e073131b509392e561b78da80`
- Zip archive: `e520ba624671f996bba9b2fe57d1f32427dd7223b4f6bc2e9c945a4fefdda770`

The Host downloaded and verified the GitHub assets, created a pre-update
ledger backup, upgraded from preview.5 with user data preserved, and started
real Hermes/OpenClaw Workers. Host status proves the managed UI now resolves to
preview.6, private HTTPS port 8443 is exclusively owned by MIS, Funnel is off,
and the existing port 443 target remains untouched. The private HTTPS Workspace
returned HTTP 200 and one physical Console peer was reachable over the tailnet.
No DNS name, IP, account, credential, setup code, Session or raw Runtime content
is retained here. Owner bootstrap, the physical browser workflow, physical
disconnect/reconnect, and another-Mac clean install remain open, so this is not
the final Release Candidate.

## Superseded Preview 7

- Tag: `v1.6.0-private-host-preview.7`
- Exact commit: `0d7634eabaa58196f433a61195d7b4c0d9ab761c`
- Push CI: passed at the exact commit (`29197215909`)
- Pull-request CI: passed at the exact commit (`29197217556`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.7`
- SHA-256 manifest: `9cdc3ccff8f4b00dd09d8aedec0ac285ea311fdb47838e17643867ca0f8a81ca`
- Tar archive: `6604c77dcd75818e1970ca577038828b9cc40f5a49a5434bc1ea1a914d803235`
- Zip archive: `ae3200c7d84f881a2e9b161ff78cf7f5447d8c451fea6613652dc67f5056f007`

preview.7 adds the Host-local `bootstrap-owner` command, serializes concurrent
first-Owner creation, bypasses environment proxies, rejects redirects and
password-style argv without echoing values, and separates Worker, CLI-helper
and npm/Vite environments through purpose-specific allowlists. GitHub download
and published checksums passed; upgrade from preview.6 created a verified
pre-update backup, preserved user data, and restarted real Hermes/OpenClaw
Workers. The managed UI resolves to preview.7 and private HTTPS Workspace
returned HTTP 200 with Funnel disabled. Operator Owner creation, physical
second-device workflow/disconnect receipt and another-Mac clean install remain
open, so this is not the final Release Candidate.

## Superseded Preview 8

- Tag: `v1.6.0-private-host-preview.8`
- Exact commit: `350b4d1966c74d80db8f58f0873562e018a714da`
- Push CI: passed at the exact commit (`29199084891`)
- Pull-request CI: passed at the exact commit (`29199086731`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.8`
- SHA-256 manifest: `251bbf675061114bcfc4ae81c5f2cd23b3da467e468a188f771d7e668371971a`
- Tar archive: `4d13fc2613ab03824957daa935164ff65d484ddcea2b8ba352480b12431fcc10`
- Zip archive: `eb46b3d27c4d75dde66641aac48be7125b4fe1e06d6a2c51a2d9cbf5bd9a2727`

preview.8 adds confirmation-gated `host configure-cli`, binds saved machine
credentials to their configured origin, and keeps browser Sessions separate
from Agent Gateway credentials. Shared CLI and Worker credential transport now
requires literal-loopback HTTP or HTTPS, bypasses environment proxies, rejects
redirects, and redacts known or Host-format keys from errors. Credentialed Host
commands additionally require a live managed Host PID; foreground and
background Host modes both maintain that record. Published checksums, same-Mac
upgrade with user-data preservation, private HTTPS Workspace readback, and
installed Hermes/OpenClaw adapter preflight passed. Both real Workers are
running, Funnel remains disabled, and the managed UI resolves to preview.8.
Operator Owner creation, an exact-preview.8 confirmed customer run, the
physical second-device workflow/disconnect receipt, and another-Mac clean
install remain open, so this is not the final Release Candidate.

## Superseded Preview 9

- Tag: `v1.6.0-private-host-preview.9`
- Exact commit: `3d04595d4247f12a1980ec32b2d0dafa6369f4e4`
- Push CI: passed at the exact commit (`29200621798`)
- Pull-request CI: passed at the exact commit (`29200623059`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.9`
- SHA-256 manifest: `04a7f3355b99d481196366ae0ecccd63016694144a10965420baeabfe7690981`
- Tar archive: `a842aeb177b0d12a283d2fd85e5a5398cc2d896aa4c6e9db402983ba24764ea9`
- Zip archive: `f44f8e2bbfea505ca82beebc44dfa0fd82f5e15451223122678a54547c75af43`
- Release-consumer bootstrap: `940fd3394d40ccf44f14cbb4a78f3dcbbfb7b632093d85e1b922073d41922a8c`

preview.9 adds the fixed-tag no-repository release consumer, programmatic
archive checksum verification, HTTPS-only redirects, bounded download sizes,
single-parser safe extraction, Python/macOS preflight, and installed provenance
readback. The release path stages a Draft, downloads and installs its assets in
a clean HOME, publishes only after that gate, then repeats through public
GitHub URLs; rejected releases are removed. Host `status` and `doctor` now
surface bounded human-login readiness without account data, and interrupted
bundle/Owner smokes clean only their registered fixture process groups.

The published four assets passed checksum verification. This Host upgraded
from preview.8 with a verified pre-update backup and user data preserved, then
started explicitly confirmed Hermes/OpenClaw Workers. Installed Gateway and
both adapter preflights passed without live execution; private HTTPS Workspace
returned HTTP 200 with Funnel disabled. Owner creation, an exact-preview.9
confirmed customer task, physical browser/disconnect acceptance and another-Mac
install remain open, so this is not the final Release Candidate.

## Superseded Preview 10

- Tag: `v1.6.0-private-host-preview.10`
- Exact commit: `d7c2ec3a49347ed6899aff3c3406f922a7690279`
- Push CI: passed at the exact commit (`29202421567`)
- Pull-request CI: passed at the exact commit (`29202423466`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.10`
- SHA-256 manifest: `47b98df3b23c50605e0d710b05ba0a36f965edd6cb231a775e46fd32d8af8caa`
- Tar archive: `2ea5bb666d5e1bc72b5ae643ea523498c845e522b012b0fc26c3f0962b799b24`
- Zip archive: `f19b5eb32c107c060c2bb0846249164d8c5564fb75684213a4d05be908875973`
- Release-consumer bootstrap: `940fd3394d40ccf44f14cbb4a78f3dcbbfb7b632093d85e1b922073d41922a8c`

preview.10 adds product/data ownership markers, strict legacy migration and
rollback, a shared no-symlink lifecycle lock, exact shim/path/PID guards, and
PID+PGID+stable process-identity binding before stop can signal a process. A
clean detached-tag build passed the full release gates. Draft-download and
public-GitHub clean-HOME installs both initialized, started, reported ready,
and stopped successfully.

The real Host upgraded from preview.9 after verified operator and automatic
pre-update backups. Ledger counts and user data were preserved; the production
UI follows preview.10, private HTTPS returns HTTP 200, Funnel is disabled, and
installed Hermes/OpenClaw preflight passes without executing a task. Two fresh
customer-style tasks reached `waiting_approval`, proving machine credentials
did not bypass the Human Approval Wall. Owner creation, approved completed
Runtime receipts, physical browser/disconnect acceptance, and another-Mac
install remain open, so this is not the final Release Candidate.

## Superseded Preview 11

- Tag: `v1.6.0-private-host-preview.11`
- Exact commit: `00ef8ea3babaec2ff141db19a48b0998496ececc`
- Push CI: passed at the exact commit (`29211371631`)
- Pull-request CI: passed at the exact commit (`29211372810`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.11`
- SHA-256 manifest: `125ecdb0064cb7f371c0273bf477e33636efa67b6e25460d84dd5c16e0151b7d`
- Tar archive: `ff36ff0f8d75ef7ad2128586a20c6187ea729a50d24b83f2d798929305d93079`
- Zip archive: `10465bfe13c46b5ba5eb0ca2f9fe52e1cd2c54fb947f9ad81c6a74afafacfabd`
- Release-consumer bootstrap: `940fd3394d40ccf44f14cbb4a78f3dcbbfb7b632093d85e1b922073d41922a8c`

preview.11 retains all preview.10 lifecycle hardening and adds bounded Owner
password guidance. `weak_password` now states the 12-character minimum through
a fixed local message while omitting password/setup-code values and refusing
to reflect arbitrary server text. The Owner bootstrap smoke, secret scan,
clean detached-tag release gates, Draft round-trip, and public clean-HOME
round-trip passed.

The real Host upgraded from preview.10 after verified operator and automatic
pre-update backups. Ledger state, the two pending approval runs, and user data
were preserved. Production UI, private HTTPS, Hermes/OpenClaw preflight, and an
installed-product weak-password check passed. Owner creation, approved
completed Runtime receipts, physical browser/disconnect acceptance, and
another-Mac install remain open, so this is not the final Release Candidate.

## Superseded Preview 12

- Tag: `v1.6.0-private-host-preview.12`
- Exact commit: `7def9ba9becf6dcf67606294ab6eed2e28b64c14`
- Push CI: passed at the exact commit (`29271946219`)
- Pull-request CI: passed at the exact commit (`29271949729`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.12`
- SHA-256 manifest: `4a600af2a01ac9b92a123193012e5256cba5ea0075adcd25881eb02b0e654b6e`
- Tar archive: `b13a27dde4b7ed49765cd663b1d84f8e82285a84f597edd51ad7a537858d2bcc`
- Zip archive: `fa539481c22e9c50c3ba447d2002d9c3dd3ec73c22333f9bf886651d07f072b4`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.12 replaces the standalone authentication card with a locked state of
the existing AgentOps MIS Workspace shell. The macOS installer and
`agentops host open-console` can hand the protected first-Owner setup authority
to the literal-loopback browser through a fragment that is immediately
scrubbed, never sent over HTTP, never printed, and never persisted. The server
still rejects no-code bootstrap. Same-document tab reuse, terminal-error
clearing, bilingual bootstrap/login, theme controls, locked navigation and CLI
headless recovery are covered by dedicated smokes and a temporary-browser
exercise.

The public Release assets were downloaded again and verified against their
manifest before the real Host upgraded from preview.11. The installer created
an automatic pre-update backup and reported user-data preservation. Installed
version/commit readback, production UI/API readiness, private HTTPS URL,
browser-first next actions and explicitly confirmed Hermes/OpenClaw Worker
restart passed. Owner creation, current-package approved Runtime completion,
physical second-device workflow/disconnect evidence, and another-Mac clean
install remain open, so this is still a preview rather than the final RC.

## Current Preview 19

- Tag: `v1.6.0-private-host-preview.19`
- Exact commit: `ac69d8c59dc8b7a9753f57f9bf1cb4a9fbc3f1a5`
- Push CI: passed at the exact commit (`29312495245`)
- Pull-request CI: passed at the exact commit (`29312498076`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.19`
- SHA-256 manifest: `696d18dd9983af11d6c1a069650247ef29db42ea6000e1d899236d27c4afe7bb`
- Tar archive: `def82d5ebbcca5e029419c61a470bb655f02d4f1ed1ec5711e8f3f1527775c42`
- Zip archive: `43906173569ddcdaff10c849441f3001830dc60535b1f9f4a8320698781fc3a3`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.19 keeps first-Owner setup, sign-in and account management inside the
existing React Workspace. Locked navigation, Topbar state and the account page
share the normal production shell; authenticated identity comes from the Human
Session instead of a demo account. The installed production HTML and JavaScript
were verified byte-for-byte against the packaged UI after the upgrade.

Host startup now also rejects an already-running same-adapter local Worker
before opening the backend port. The conflict response exposes only adapter and
PID metadata, never kills the existing process, and preserves the explicit
`--no-workers` external-ownership mode. Bundle, release-consumer and isolated
ownership smokes passed without executing a live Runtime task.

The published bootstrap was then executed from its public GitHub Release URL in
a fresh temporary HOME with no repository and no existing install. It fetched
the fixed tag, verified the published checksum, installed without initializing
an Owner or starting a Runtime, and read back preview.19 at the exact release
commit. This is a same-Mac clean consumer receipt; it does not replace the
required another-Mac receipt.

The real Host upgraded from preview.18 after an operator backup and the
installer's automatic pre-update backup. SQLite integrity, user-data
preservation, production UI/API readiness, private HTTPS, exact installed
version and one Hermes plus one OpenClaw Worker passed. Owner creation,
current-package approved Runtime completion, physical second-device workflow
and disconnect evidence, and another-Mac clean install remain open. This is a
prerelease, not the final RC.

## Release Gates

The RC may be declared only after all of the following are attached to one
exact commit and version tag:

- push and pull-request CI are green at the exact tag commit;
- `.zip`, `.tar.gz` and `.sha256.json` are attached to a GitHub prerelease;
- another Mac downloads, verifies and installs that exact asset without a
  repository, Node or Git;
- Host and console are connected through private HTTPS without replacing an
  unrelated Tailscale Serve target;
- the second computer completes login, task dispatch, observation, approval,
  evaluation/audit review and approved artifact download;
- closing the browser or disconnecting tailnet does not stop a fresh confirmed
  Hermes/OpenClaw task, and reconnect shows the same task/run evidence;
- backup/restore, restart/knowledge persistence, upgrade/rollback, secret scan,
  bundle scan and production UI build pass at the same commit.

## Evidence Rules

- Record bounded IDs, counts, statuses, exact commit, tag and checksums only.
- Do not record passwords, setup codes, Session/Agent tokens, raw prompts,
  raw responses, private messages, full transcripts, database files or Host
  paths from another user account.
- Label mock/loopback smokes as deterministic fallback; never use them as the
  physical second-device or real Runtime proof.
- A failed row remains open even when adjacent implementation tests pass.
