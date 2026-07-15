# Private Host Release Candidate Acceptance

Status: preview.31 published and installed; exact-package Hermes/OpenClaw service-Worker tasks completed with verified evidence, while Owner review and physical-device gates remain open

This matrix is the requirement-by-requirement completion record for
`LOCAL_HOST_REMOTE_CONSOLE_SPEC.md`. A deterministic smoke proves only the
bounded behavior it names. Cross-device and real-runtime rows require fresh
physical evidence and cannot be closed by mock output.

## Functional Acceptance Matrix

| # | Requirement | Current evidence | Status |
|---|---|---|---|
| 1 | Clean Host installs from a versioned asset without cloning | GitHub prerelease `v1.6.0-private-host-preview.31` publishes a no-repository bootstrap plus archive/checksum assets from exact commit `fed1b2410d6725a217c9727dba570db62cc46963`. Candidate, Draft and public assets were byte-equal; clean-HOME install/start/status/stop and preview.30-to-preview.31 upgrade passed. A receipt from another physical Mac remains missing. | Passed locally; external evidence required |
| 2 | `agentops host start` serves production UI/API/ledger/knowledge and actionable worker state | `PRIVATE_HOST_LIFECYCLE_ACCEPTANCE.md`, `PRIVATE_HOST_AUTH_WORKSPACE_UI_ACCEPTANCE.md`, `PRIVATE_HOST_SERVICE_WORKER_PRESENCE_ACCEPTANCE.md` and bundle smoke cover installed CLI, production UI, browser-first Owner setup inside the existing React Workspace, init, doctor, start/status/stop, Runtime readiness and fail-closed Worker ownership. Installed preview.31 serves that integrated UI and reports the existing Owner login ready. | Passed locally |
| 3 | Dependency-free second computer opens private HTTPS console and authenticates | preview.31 is live through private Tailscale HTTPS on port 8443, Funnel is disabled, and the Workspace is ready. The existing first Owner remains present and login-ready; a fresh Human Session could not be opened during this receipt because the workstation was locked. Physical second-device browser login remains a human gate. | Host side passed; external evidence required |
| 4 | Unauthenticated UI/API data fails closed | `human_browser_auth_smoke.py`, `private_host_owner_browser_handoff_smoke.py`, artifact-download smoke and lifecycle acceptance cover anonymous denial, setup-code authority, role/session separation and CSRF/Origin checks. | Passed locally |
| 5 | Remote task, observation, approval, evaluation/audit review and approved artifact download | Customer dispatch and ledger views exist; Audit and Memory use live APIs; memory decisions write through the approver route; approved artifact download is Session/workspace/approval checked and audited. preview.31 created two reviewable memory candidates and two safely paused false-positive prepared actions; Owner review and second-device end-to-end receipts remain open. | Partial |
| 6 | Explicitly confirmed Hermes/OpenClaw task writes complete bounded evidence | Installed preview.31 service Workers completed OpenClaw run `run_gw_612fb884979c` and Hermes run `run_gw_9767258929f0`. Each has a completed task/run, tool call, runtime summary event, passing evaluation, artifact, memory candidate, audit chain and verified plan-evidence manifest. | Passed on current package; Owner review pending |
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

## Superseded Preview 19

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

The installed macOS app was also launched through `open` and opened the same
production Workspace in Chrome while preserving the existing Host, Hermes and
OpenClaw PIDs. The managed Host-only LaunchAgent plist was staged through its
dry-run and explicit install gates with exact definition, `0600` mode and no
credential material, but it remains unloaded. Logout/reboot persistence is not
claimed.

preview.20 supersedes this package with the compact locked Workspace shell and
responsive account form. The preview.19 release and installation evidence above
remains historical evidence only.

## Superseded Preview 20

- Tag: `v1.6.0-private-host-preview.20`
- Exact commit: `3b6518f3870c0e299e74f757da41623e8c14f526`
- Push CI: passed at the exact commit (`29316887569`)
- Pull-request CI: passed at the exact commit (`29316891385`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.20`
- SHA-256 manifest: `b8c0c4f38d4764705185469cd5c96da045658779cc79dd90f0b44b17e8470e23`
- Tar archive: `8ca2e218f178756d1c2773a722d15086078f9158a47a513ea8d15425a81cfe8e`
- Zip archive: `ab961783542137cb6b7940a2ce1dac2ea575bbe29ff0da2faad6af5bda542a19`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.20 keeps Owner setup and sign-in inside the existing React Workspace,
but removes the locked navigation wall and inactive Topbar controls. Before
authentication, the Sidebar exposes only the current account-and-access step;
the account form uses compact settings rows on desktop and label-over-input
rows on narrow screens. The package introduces no second frontend, standalone
auth card, marketing surface or third-party UI asset.

Both published archives, the checksum document and bootstrap were downloaded
from GitHub and compared byte-for-byte with the locally built release assets.
The archive policy scan found no unsafe names or forbidden payload members. The
public bootstrap then installed preview.20 at the exact release commit in a
fresh temporary HOME without a repository, without creating a Host Owner and
without starting a Runtime.

The real Host upgraded from preview.19 after a verified operator backup; the
installer also created and verified its automatic pre-update backup. It
preserved the ledger, installed the managed UI and restored one explicitly
confirmed Hermes Worker plus one explicitly confirmed OpenClaw Worker. The
installed HTML, CSS and JavaScript matched the source release build
byte-for-byte. Browser review of the installed `18878` Workspace at 1280x720
reported HTTP 200, zero console errors and the compact setup-only shell.

Opening the installed macOS application after the upgrade reused the running
Host and both Workers: the Host, server, Hermes and OpenClaw PIDs remained
unchanged. Private Tailscale HTTPS stayed ready with Funnel disabled. No Owner
was created and no live Runtime task was executed during this package upgrade.
Owner creation, current-package approved Runtime completion, physical
second-device workflow and disconnect evidence, another-Mac clean install and
logout/reboot service proof remain open. This is a prerelease, not the final RC.

preview.21 supersedes this package with self-validating first-Owner password
setup. The preview.20 evidence above remains historical evidence only.

## Superseded Preview 21

- Tag: `v1.6.0-private-host-preview.21`
- Exact commit: `c29addf2fb1155e6046432007c7d6282ac6d1754`
- Push CI: passed at the exact commit (`29320749703`)
- Pull-request CI: passed at the exact commit (`29320753831`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.21`
- SHA-256 manifest: `3e65fdd90bb0cd5ae319f0f1d8378f3308caca617b95400db329459663bec50e`
- Tar archive: `ea58166117135a9b63978992d2979d19a0f60b28aed71d4a7e0c7378bd573973`
- Zip archive: `1055ff68d2b7568ab988dde079000dcfe65cd595c84d98d3715cc2ed74baccb3`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.21 keeps the same React Workspace and adds compact live validation to
the first-Owner form: the password row reports the 12-character minimum, the
confirmation row reports match/mismatch, and the create action stays disabled
until setup code, username and both password gates are locally valid. Password
visibility uses accessible eye-icon controls and resets after authentication,
logout or Session expiry. Server-side setup-code, password, Session, CSRF,
Origin and role enforcement are unchanged.

Both exact-head CI runs passed. The four Draft assets were downloaded and
matched the local candidate byte-for-byte before a clean temporary HOME
installed, started, reported `bootstrap_required`, and stopped on an isolated
port. After publication, the same four public assets again matched
byte-for-byte and a second fresh HOME installed from the public bootstrap,
served the Workspace over HTTP 200 and stopped cleanly. Neither consumer had a
repository, Owner account or live Runtime execution.

The real Host then created a verified operator backup and the installer created
its own pre-update backup before moving from preview.20 to preview.21. Ledger
integrity and user data were preserved. The installed UI matched the source
release build byte-for-byte; private HTTPS remained ready with Funnel disabled.
An installed-product browser pass loaded `/workspace` at 1280 x 720, rendered
the Chinese account setup inside the existing Workspace shell, kept the create
action disabled before valid input, and reported zero browser console errors.
One explicitly confirmed Hermes Worker and one explicitly confirmed OpenClaw
Worker resumed with fresh heartbeats and zero processed tasks in this upgrade
window. No Owner was created and `live_execution_performed` remained false.

Owner creation, current-package approved Runtime completion, physical
second-device workflow and disconnect evidence, another-Mac clean install and
logout/reboot service proof remain open. This is a prerelease, not the final RC.

preview.22 supersedes this package with a visual consistency correction inside
the same React Workspace. The preview.21 evidence above remains historical
evidence only.

## Superseded Preview 22

- Tag: `v1.6.0-private-host-preview.22`
- Exact commit: `b3bff2784d9f1036f28250caae5922e450d8e4ce`
- Push CI: passed at the exact commit (`29324928569`)
- Pull-request CI: passed at the exact commit (`29324931086`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.22`
- SHA-256 manifest: `fdba696511b1b8b02aede06b956ac935796f06b83810eb8be67a89e580c662f0`
- Tar archive: `f4716f6a0dcc424cb034c5b79df34b85c8e247e818036064f2931970159418d7`
- Zip archive: `22cde6d06bee91f29229502a62be67ac639abe0a36c8702b3f4519ec75462396`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.22 keeps Owner creation inside the existing React `AppShell` and
Workspace route. It removes decorative gradients, fluorescent locked-state
accents, oversized generated-sounding copy and the fixed-width settings track;
the account form now uses the same restrained spacing, typography, primary
color, language control and light/dark theme system as the rest of the product.
No separate setup frontend or replacement authority surface was introduced.

Both exact-head CI runs passed. Draft and public Release assets matched the
local candidate byte-for-byte. Fresh temporary HOME installations from the
candidate and public bootstrap each started and stopped on isolated ports with
no repository, Owner account or live Runtime execution. The public package
served the integrated production Workspace and reported `bootstrap_required`.

The real Host created a verified operator backup and the installer created its
own pre-update backup before moving from preview.21 to preview.22. The installed
CLI, `host status` and `host doctor` passed; the Host serves the preview.22 UI at
`127.0.0.1:18878`, private Tailscale HTTPS is ready on port 8443, and Funnel is
disabled. Browser readback rendered the Chinese Owner form inside the existing
Workspace shell. One explicitly confirmed Hermes Worker and one explicitly
confirmed OpenClaw Worker are running. Opening the installed macOS application
reused the existing Host PID instead of creating a duplicate process tree. No
Owner was created and no Runtime task was dispatched during the upgrade.

Owner creation, current-package approved Runtime completion, physical
second-device workflow and disconnect evidence, another-Mac clean install and
logout/reboot service proof remain open. This is a prerelease, not the final RC.

preview.23 supersedes this package with Host-managed Worker process
normalization, safe lifecycle ownership and deduplicated Fleet capacity. The
preview.22 visual-consistency evidence above remains historical evidence only.

## Superseded Preview 23

- Tag: `v1.6.0-private-host-preview.23`
- Exact commit: `24d0791bbd1848c275e72b9c7baafcb6c28be1ce`
- Push CI: passed at the exact commit (`29328017966`)
- Pull-request CI: passed at the exact commit (`29328021107`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.23`
- SHA-256 manifest: `921a450ea279a741affc1297506b53e2b493bdd45a9c65fb7eb4fb78ce991668`
- Tar archive: `e3cac3ec7c82b710001040f869b9f2379f28cd5155c11711a0b1b1e9eef8e67d`
- Zip archive: `b53f3e10b6f1887603833b1da7c1089687c91a043127b4cce0144df015200b0e`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.23 keeps the existing React Workspace and account surface from
preview.22. It normalizes the Private Host child Worker state into Worker Status
and Fleet with `management_mode:host_stack`, rejects child stop/restart through
the Worker API, disables those controls in the existing UI, and deduplicates a
process from its matching Agent row. API-managed daemons remain independently
controllable under `management_mode:daemon_api`.

Both exact-head CI runs passed. Local bundle, release-consumer and macOS
launcher smokes passed. Draft and public Release assets matched the local
candidate byte-for-byte. Fresh temporary HOME installations from the Draft and
the public GitHub bootstrap each started and stopped on isolated ports with no
repository, Owner account or live Runtime execution.

The real Host created and verified an operator backup before stopping
preview.22; the public bootstrap then completed its pre-update backup and
installed preview.23 with preview.22 retained as the previous version. The Host
is ready at `127.0.0.1:18878`, private Tailscale HTTPS remains ready on port
8443, and Funnel remains disabled. Browser readback rendered the Chinese Owner
form inside the existing Workspace with zero console errors.

One explicitly confirmed Hermes Worker and one explicitly confirmed OpenClaw
Worker are running. Worker Status reports both as `host_stack`,
`control_allowed:false`, and `process_source:worker_state`; Fleet reports two
running local daemons, two Host-managed Workers, zero API-managed daemons and
`running_workers:2`. No task was dispatched during the upgrade.

Owner creation, current-package approved Runtime completion, physical
second-device workflow and disconnect evidence, another-Mac clean install and
logout/reboot service proof remain open. This is a prerelease, not the final RC.

preview.24 supersedes this package with fail-closed Worker process identity
verification. The preview.23 Host ownership and Fleet normalization evidence
above remains historical evidence only.

## Superseded Preview 24

- Tag: `v1.6.0-private-host-preview.24`
- Exact commit: `d52415f7d838c584faa61204fe27fafb4c622324`
- Push CI: passed at the exact commit (`29331012829`)
- Pull-request CI: passed at the exact commit (`29331015928`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.24`
- SHA-256 manifest: `4eca6f47451fb6522e65cdca72e80e5201630649e7851781e86d5e5abb4622c2`
- Tar archive: `6069d4a6f84318a21aecb9d8169478a88f48c00a031b7406e3f02233b2cf9e6a`
- Zip archive: `6cb6a182feca600d1016b732c71884bcfd958ac82b670f0147e9c3c247d92e1d`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.24 keeps the existing React Workspace and Host-owned Worker topology.
Every new Worker state now carries a bounded SHA-256 process identity derived
from its OS start record, command record and process group. Status recomputes
that identity before accepting the PID. A stale, replaced or tampered claim is
reported as `identity_unverified`, removed from running capacity, blocked from
start/stop/restart, and retained as a warning without exposing the process
command, environment, prompt, response or credentials.

Both exact-head CI runs passed. The local candidate passed process-identity
tamper, normal Host stack, API-managed daemon, Worker UI contract, production
UI build, bundle, release-consumer, backup/restore and secret-scan gates. All
four Draft assets matched the local candidate byte-for-byte; a clean temporary
HOME installed, initialized, started, reported `bootstrap_required`, and
stopped without a repository or live Runtime execution. The published assets
again matched byte-for-byte, and a second clean HOME completed the same public
bootstrap roundtrip.

The real Host created a verified operator backup, and the public installer
created a second verified pre-update backup before upgrading from preview.23 to
preview.24. User data was preserved. The installed Host is ready at
`127.0.0.1:18878`; private HTTPS remains ready on port 8443 and Funnel remains
disabled. Read-only browser QA rendered the Chinese first-Owner form inside the
existing Workspace shell with no horizontal overflow; no credential was entered
and no Owner was created.

One explicitly confirmed Hermes Worker and one explicitly confirmed OpenClaw
Worker are running. Both report `management_mode:host_stack`,
`process_source:worker_state`, `process_identity_verified:true`, and
`control_allowed:false`. Fleet reports two running local daemons, two
Host-managed Workers, zero API-managed daemons, zero unverified process claims
and `running_workers:2`. No task was dispatched during the upgrade.

Owner creation, current-package approved Runtime completion, physical
second-device workflow and disconnect evidence, another-Mac clean install and
logout/reboot service proof remain open. This is a prerelease, not the final RC.

preview.25 supersedes this package only to remove the original Figma starter
identity from the browser metadata. The preview.24 Worker identity hardening
and installed evidence above remain historical evidence.

## Superseded Preview 25

- Tag: `v1.6.0-private-host-preview.25`
- Exact commit: `2baa5aecf8dc5a9f6754ef8adb4bc34bdb5a4a3b`
- Push CI: passed at the exact commit (`29334397505`)
- Pull-request CI: passed at the exact commit (`29334401556`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.25`
- SHA-256 manifest: `b95a64dbf4fe7433822c08db0e52790bb7b65873b80799e31001e10c0e42a2e3`
- Tar archive: `aa1978cba1c7b76f054c902990923991c01e024615e5980a05ce58f4ba53e187`
- Zip archive: `74a62ec7c72d39c84062ee9b85700ba2595216bb183d7497b099a3cb3da8fa70`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.25 changes no route, layout, authority boundary or Runtime behavior. It
keeps the existing React `AppShell`, account settings surface, bilingual copy,
theme system and Worker controls. The browser title is now `AgentOps MIS`, and
the description names the concrete local task, approval, run, evaluation,
memory and audit surfaces instead of the original generic starter text. The
existing auth Workspace smoke now fails if the starter identity returns.

Both exact-head CI runs passed. Production UI build, auth Workspace contract,
bundle, release-consumer and release-evidence gates passed. The four Draft
assets matched the local candidate byte-for-byte. Candidate and Draft-download
archives each installed and started in clean temporary HOMEs without a
repository. After publication, all four assets again matched byte-for-byte and
the public bootstrap completed a third clean-HOME install/start/stop roundtrip.
Each installed production page returned the AgentOps MIS title and concrete
description; no Owner or live Runtime task was created.

The real Host created and verified an operator backup, and the public installer
created a separate pre-update backup before upgrading from preview.24 to
preview.25. User data was preserved and preview.24 remains available as the
previous version. The Host is ready at `127.0.0.1:18878`; private HTTPS remains
ready with Funnel disabled. Installed-product browser QA rendered the Chinese
first-Owner form inside the existing Workspace shell with no horizontal
overflow and no credential input.

One explicitly confirmed Hermes Worker and one explicitly confirmed OpenClaw
Worker are running. Both remain `host_stack`, process-verified, sleeping and
blocked from child-level control; Fleet reports two running local daemons, two
Host-managed Workers, zero API-managed daemons and zero unverified process
claims. No task was dispatched during this upgrade.

Owner creation, current-package approved Runtime completion, physical
second-device workflow and disconnect evidence, another-Mac clean install and
logout/reboot service proof remain open. This is a prerelease, not the final RC.

preview.26 supersedes this package by keeping first-Owner setup and sign-in
inside the complete existing Workspace navigation instead of a setup-only
shell.

## Superseded Preview 26

- Tag: `v1.6.0-private-host-preview.26`
- Exact commit: `5fadf74bb281a028f5d4698dbb84fa703c6fc6a6`
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.26`
- SHA-256 manifest: `2caf260a646b4f8ad5b8a2dc23b8a0c23a1e63232db9e5153b40175e3fe9b58a`
- Tar archive: `a17c0555a4a738c9d849f869823c19c3e7303f06b323960a52bc88873838af6a`
- Zip archive: `13929505ae37717f37d96dccc2411fecd714a8bdda5be5fc07a2be6bff46e850`

preview.26 retained the existing React AppShell, complete front-office/admin
Sidebar, account settings surface, theme and locale controls for first-Owner
setup. Its clean-HOME install exposed a packaging defect: the installed bundle
did not provide the consumer-facing `agentops-worker` shim. preview.27 is the
corrective package and preview.26 must not be used to install Worker services.

## Superseded Preview 27

- Tag: `v1.6.0-private-host-preview.27`
- Exact commit: `44d0c4ea1e58d30a91a0cb69baa85457030ca32c`
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.27`
- SHA-256 manifest: `e4b0c9dc871030b0b13186ebd0796d6d9ac57ccfe3360153f676879b6d84febe`
- Tar archive: `9381066e0efc9546472f640edf8f809d078b4a9a6de3376d72027be5028b6e98`
- Zip archive: `3742f7119adb5e71f592b7e35c76fbc95ec3a3a9247cabfc499e5969425cfccc`

preview.27 fixes installer, upgrade and uninstall ownership for both `agentops`
and `agentops-worker`, and its clean consumer gate executes both installed
commands. The real Host was upgraded with its Host-only LaunchAgent and two
independently service-managed adapter Workers preserved. Its old Worker Console
still reported zero Host-observed processes because service heartbeat presence
was not yet projected as execution capacity; preview.28 fixes that read model
without inventing process verification.

## Superseded Preview 28

- Tag: `v1.6.0-private-host-preview.28`
- Exact commit: `f627e83aae357ce4733123208a9d41c037803434`
- Push CI: passed at the exact commit (`29348330871`)
- Pull-request CI: passed at the exact commit (`29348334213`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.28`
- SHA-256 manifest: `12553ad8ca9df7dc66c79999899535b444d5636189412d24af756b67d1aeae6f`
- Tar archive: `ddc48c498766566f87ea9bb7f5af996699938e694f99661703f893209e800439`
- Zip archive: `6fd4e6e4ce8b6715a31c12a1997f1bd79c47b84c042d22d07e626a5ecac73340`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.28 keeps the complete existing React Workspace and adds a bounded
service-presence projection to the existing Worker Console. An external-service
Worker contributes execution capacity only when both its short-lived Agent
Gateway Session is active and its `agent.heartbeat` is fresh. It remains
`management_mode:external_service` and `process_state_verified:false`; the
browser/server does not execute shell or infer launchd ownership.

Exact-head CI, production UI, clean-clone RC, bundle lifecycle, clean-HOME
consumer install, both installed CLI shims, public-asset hash equality, secret
scan and strict release evidence passed. The real Host created an operator
backup and the installer created a separate pre-update backup before upgrading
from preview.27. User data was preserved, private HTTPS remained ready and
Funnel remained disabled.

The installed Host now reports two fresh service Workers and two execution
capacity lanes while correctly keeping Host-observed `running_workers=0`.
Launching the installed `AgentOps MIS.app` again kept the Host PID and both
independent service Worker PIDs unchanged, opened the existing Workspace with
the setup fragment scrubbed, omitted the manual setup-code input and performed
no Runtime task. A subsequent preview-first then explicitly confirmed Host
LaunchAgent restart replaced only the Host process, returned the same exact
preview.28 release commit, restored loopback/private-HTTPS readiness and left
the independent Hermes/OpenClaw services running; the receipt reported no
Worker action or live Runtime execution. Owner creation, current-package
approved Runtime completion,
physical second-device workflow/disconnect evidence, another-Mac clean install
and logout/reboot service proof remain open. This is a prerelease, not the final
RC.

The installed preview.28 CLI also created and verified a fresh online backup
while the Host remained ready. Manifest, hash, size, schema, SQLite integrity
and foreign-key checks passed; the secret store was excluded and no raw ledger
rows or token values were printed. The user's live ledger was not restored;
confirmed restore and access-revocation behavior remain proven against isolated
state.

## Superseded Preview 29

- Tag: `v1.6.0-private-host-preview.29`
- Exact commit: `574c735541d95b70180254235a385ff764f8c45c`
- Push CI: passed at the exact commit (`29362408547`)
- Pull-request CI: passed at the exact commit (`29362410590`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.29`
- SHA-256 manifest: `937529610b6d724698e64db4847251aa5a49bd26dcda05b2a10669ea00b9939c`
- Tar archive: `373dabd9e1b9fe94d89db769ac33725b84b1f4110ec280b4b94eab3fa75a1dfb`
- Zip archive: `cfd07bc0b4e8c235746648242b12e11fedcc10144def075f2b7427933abd14e8`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.29 was published as a GitHub prerelease through the manual prerelease path.
The Private Host Preview Release workflow did not run. Candidate and
public clean-HOME install/start/status/stop passed, and every public asset was
byte-equal to its candidate counterpart.

The real Host upgraded from preview.28 by explicitly unloading its Host
LaunchAgent, installing preview.29, and loading the Host service again. Upgrade
readback reported `previous_version=.28`. The Host and independent
Hermes/OpenClaw Worker PIDs were preserved where expected, and opening the
installed app reused the existing Host and Worker processes. No model task was
executed in this acceptance cycle.

The existing first Owner passed local login, logout and Workspace readback.
Password recovery reported available and local-only; a remote Origin and a
request without app authority both failed closed. The installed HTML, CSS and
JavaScript were byte-equal to the exact preview.29 build.

The installed online-backup receipt hash is
`c8bb0335d0602bec5c3588cd9a7ee013fc71d697ee440c645310508cfc2a3031`.
Manifest, file hash, size, schema, SQLite integrity and foreign-key checks all
passed. The secret store was excluded and raw ledger rows were omitted.

Physical second-computer acceptance, another-Mac installation, real network
disconnect, physical logout/reboot, and an exact-package approved Runtime task
remain open. No external evidence is synthesized or inferred from same-Mac,
loopback, CI, or prior-preview receipts. This is a prerelease, not the final RC.

## Superseded Preview 30

- Tag: `v1.6.0-private-host-preview.30`
- Exact commit: `519eb2057f54de387df24a0d57beef2d8eca130b`
- Push CI: passed at the exact commit (`29391096530`)
- Pull-request CI: passed at the exact commit (`29391098474`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.30`
- SHA-256 manifest: `e100a458a8e65d75051c82678a6fa5025cb34e2c4cae7da3babdf7334e034946`
- Tar archive: `81eb636f2da3317331ea241e81b0d3262da41202cb2309b2ba7bb259196ba30f`
- Zip archive: `ba01016966c35895e0f0bb2016ff37432cccfffec6b86b2aee2839ca977d0631`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.30 fixed long-running Worker idle-backoff overflow. Its real in-place
installation then exposed that both CLI shims were rewritten on their existing
inodes while LaunchAgents used those executable paths. Direct shim execution
ended with exit 137 and both Workers recorded `-9`; the versioned payload,
Host data and pre-update backup remained valid. The Host was recovered through
the installed module entry point and byte-identical shims on new inodes.
preview.30 is immutable and must not be used for another in-place upgrade.

## Current Preview 31

- Tag: `v1.6.0-private-host-preview.31`
- Exact commit: `fed1b2410d6725a217c9727dba570db62cc46963`
- Push CI: passed at the exact commit (`29391744378`)
- Pull-request CI: passed at the exact commit (`29391746311`)
- Release: `https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/v1.6.0-private-host-preview.31`
- SHA-256 manifest: `030cc85cf277255f6195c66933fe8251dbc1b6195368ae03e3fa820fe541e90a`
- Tar archive: `07e1c94740424a3a8a4d3cab90cb513e06b0a5ddd62c372eafe27b2ec4770aab`
- Zip archive: `b27e0d3e53b51cf9d015e2ffc2e042efd4621232a3f4f5fc0d7b48628a63745d`
- Release-consumer bootstrap: `6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f`

preview.31 was published through the manual Draft-to-prerelease path because
the Private Host Preview Release workflow was not available on the default
branch. Candidate, Draft and public assets were byte-equal. Public clean-HOME
download/install, both CLI entry points, Host init/start/status/stop and a
preview.30-to-preview.31 isolated upgrade passed.

The real Host upgrade created and later verified a pre-update backup, preserved
user data, atomically replaced both CLI shim inodes and reported
`previous_version=1.6.0-private-host-preview.30`. The independent Worker
processes survived installation without exit 137 or `-9`; explicit restarts
then ran Hermes and OpenClaw from the preview.31 `current` directory. Host
health, Owner login readiness and private HTTPS returned ready, with Funnel
still disabled.

Installed service Workers completed tasks
`tsk_preview31_openclaw_readonly_20260715T055005Z` and
`tsk_preview31_hermes_readonly_20260715T055005Z`. Their runs
`run_gw_612fb884979c` and `run_gw_9767258929f0` completed without an error type,
each producing one tool call, passing evaluation, artifact, reviewable memory
candidate and a verified plan-evidence manifest. Two earlier tasks containing
negated external-action wording remain safely paused behind prepared-action
approval; no Runtime was called for those rows.

Owner review closure, physical second-device login/disconnect, another-Mac
clean install, current-package app-open receipt and logout/reboot service proof
remain open. The Mac was locked during Human Session follow-up, so no Keychain
authority was bypassed and no external evidence is synthesized. This is a
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
