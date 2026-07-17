# MacBook Remote Console Dogfood Acceptance

Status: real second-device transport and direct-browser rendering verified;
normal Chrome proxy path and authenticated workflow remain open

Date: 2026-07-18 (Asia/Shanghai)

## Topology

- The Mac mini remains the AgentOps MIS Host, model/Worker runtime, knowledge
  store and authoritative ledger.
- The MacBook Air is the real human Console device on the existing private
  Tailscale network.
- Tailscale Serve on the Host keeps HTTPS port `8443` mapped to the loopback
  Private Host. Funnel remains disabled.
- The MacBook uses the detached `screen` session `codex-resume` as an optional
  SSH-operated Codex execution channel. This is an internal dogfood mechanism,
  not a customer dependency or product authority.

No Tailscale command, Serve mapping, Host database, Runtime credential or
customer record was changed during the source hardening work.

## Verified Evidence

From the MacBook:

- Tailscale peer ping reached the Host directly.
- TCP connection to the Host HTTPS port succeeded.
- `curl` with certificate verification returned HTTP `200` over both HTTP/1.1
  and HTTP/2.
- A fresh temporary Chrome profile with `--no-proxy-server` rendered the real
  AgentOps MIS Chinese account-and-access login surface at `1280x720`.
- No username, password, cookie, setup code or form submission was used.

The first normal-Chrome screenshot truthfully showed
`ERR_CONNECTION_CLOSED`. Investigation found that the MacBook system browser
was using a loopback HTTP/HTTPS/SOCKS proxy backed by Qiqi/mihomo, and its
bypass list omitted the Tailscale range and Host. The existing proxy settings
were preserved; only the Tailscale CGNAT range, `*.ts.net`, and the exact Host
name/address were appended to the Wi-Fi bypass list. A fresh normal Chrome
profile still returned `ERR_CONNECTION_CLOSED`, while the same fresh Chrome
with `--no-proxy-server` rendered the Workspace. The remaining defect is
therefore the normal Chrome/proxy integration, not Tailscale Serve or MIS.

All screenshots and receipts remain temporary local evidence under `/tmp` and
are not committed.

## Not Yet Accepted

- a fresh normal-Chrome screenshot after the exact bypass update;
- member pairing or Owner login from the MacBook;
- customer task creation, approval, evaluation, audit and artifact download;
- browser/Tailscale disconnect while a real Hermes/OpenClaw task continues;
- logout plus Owner device revocation;
- exact-release correlation with a packaged Host build.

This receipt therefore does not close the full physical second-computer gate.
It does prove that the installed Host, Tailscale Serve, certificate, and a real
Chrome engine can render the Workspace from the MacBook without a container.

## Safety

- Existing Tailscale remains installed and enabled as the advanced private
  network profile.
- No Funnel, router port forwarding, public tunnel or non-loopback Python bind
  was enabled.
- The remote Codex task was read-only and produced bounded receipt metadata;
  full terminal scrollback was not ingested.
- The temporary Chrome profile contains no user account or browsing history.
