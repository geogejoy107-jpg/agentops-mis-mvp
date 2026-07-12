# Human Browser Authentication Foundation Acceptance

## Scope

This Phase 2 slice creates a credential boundary between human browser users
and Agent Gateway machines before any private-network publication is enabled.

It adds:

- `human_accounts` with owner/operator/approver/viewer role values;
- scrypt password derivation with per-account random salt;
- hash-only, expiring and revocable human sessions;
- `HttpOnly`, `SameSite=Strict` browser cookie behavior;
- CSRF tokens for state-changing browser requests;
- Owner bootstrap, login, status and logout APIs;
- a bilingual React login/Owner initialization gate;
- anonymous workspace read denial in private/shared/production modes;
- continued separation of human sessions from Agent Gateway credentials;
- a minimal public `/health` response that omits workspace state.

Private-network publication, account invitation/device management, and a
packaged Host initializer remain subsequent slices.

## Route Boundary

| Route class | Credential | Examples |
|---|---|---|
| Public minimal health | none | `GET /health` |
| Human authentication | bootstrap code, password, or human session | `/api/human-auth/*` |
| Human workspace | human session; CSRF and role for writes | `/api/tasks`, `/api/runs`, `/api/approvals`, `/api/operator/*` |
| Machine Agent Gateway | API key, scoped Agent token, or Agent session | `/api/agent-gateway/*` |
| Host-sensitive | owner role now; stricter direct-host policy pending | local worker, runtime, integration, export, coding-workspace routes |

The human browser cookie is never accepted as a machine Gateway credential.
The browser does not receive the Agent Gateway API key or Admin key.

## Verification

```bash
python3 -m py_compile server.py agentops_mis_core/*.py scripts/*.py
python3 scripts/human_browser_auth_smoke.py
python3 scripts/run_local_stack_smoke.py
python3 scripts/production_ui_host_smoke.py
python3 scripts/startup_security_guard_smoke.py
python3 scripts/secret_scan_smoke.py
cd ui/start-building-app && npm run build
git diff --check
```

Verified behavior:

- anonymous human workspace read returned `401`;
- anonymous Agent Gateway read returned `401` when a machine key was set;
- the machine key authenticated Agent Gateway independently;
- invalid Owner setup code was rejected;
- valid bootstrap created an Owner and an HttpOnly/SameSite session;
- a human cookie was rejected by Agent Gateway;
- Owner could read normal and Operator workspace APIs;
- missing CSRF blocked a task write;
- valid CSRF allowed a bounded task write;
- logout revoked the session and subsequent workspace read returned `401`;
- no real runtime or external connector was called;
- all persistence used a temporary SQLite database;
- UI production build passed with 2,279 transformed modules;
- a headed Playwright browser opened the production same-origin Host, displayed
  the bilingual Owner initialization gate, completed Owner bootstrap, entered
  `/workspace`, loaded Operator data, and approved one seeded item through the
  CSRF-protected browser request path against an isolated database;
- the rebuilt Topbar displayed the authenticated Owner identity and a visible
  Chinese logout command; Playwright logout returned the browser to the login
  gate and the server recorded session revocation;
- secret scan and local-mode regression smokes passed.

## Security Notes

- Password values, setup codes, session values and CSRF values are not written
  to audit metadata or printed by the server.
- Password hashes use `hashlib.scrypt` with `n=16384`, `r=8`, `p=1`, a random
  16-byte salt and constant-time comparison.
- Session rows contain only a SHA-256 token hash.
- CSRF is derived from the opaque session token and is kept by the UI in memory
  or `sessionStorage`, never `localStorage`.
- Production/private host mode defaults the cookie to `Secure`; the smoke sets
  `AGENTOPS_COOKIE_SECURE=false` only because its isolated server uses HTTP
  loopback rather than the future Tailscale HTTPS endpoint.
- Existing local workstation mode remains compatible and does not require a
  human login unless explicitly enabled.

## Known Limitations

- Only first-Owner bootstrap and login/logout are exposed; invitation, account
  creation, disable, role change and session/device revocation UI are pending.
- State-changing requests, bootstrap, login and logout enforce the configured
  Origin allowlist; missing or untrusted origins fail closed when configured.
- Host-sensitive routes currently require Owner but still need a stricter
  direct-host/proxy policy before broad remote use.
- Login throttling and password reset/recovery are pending.
- Tailscale Serve configuration and second-computer acceptance are not yet
  complete.
- This is not public internet or multi-tenant SaaS authentication.

## Next Slice

Add the `agentops host init/start/status` lifecycle with generated local secret
files, trusted-origin configuration and Tailscale Serve preview. Then perform a
second-computer browser acceptance without installing repository dependencies
on the console machine.
