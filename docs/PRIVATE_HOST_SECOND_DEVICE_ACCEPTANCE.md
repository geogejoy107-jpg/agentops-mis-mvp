# Private Host Second-Device Acceptance

Status: execution protocol; physical second-device evidence pending

This protocol proves that a computer without the AgentOps MIS repository,
Python, Node, Git, Hermes, OpenClaw, or an Agent Gateway token can operate the
Private Host through a browser on the same trusted tailnet. Passing local or CI
smokes does not satisfy this protocol.

## Roles And Boundary

- The Host computer runs the production Host, ledger, knowledge index, Worker,
  and explicitly confirmed Hermes/OpenClaw adapter.
- The Console computer has only Tailscale, a modern browser, and a human MIS
  account.
- Tailscale Serve remains private and must not use Funnel. Use HTTPS port 8443
  when port 443 is already owned by OpenClaw.
- Browser Session credentials and Agent Gateway machine credentials remain
  separate.
- A browser-generated device checklist is non-authoritative. The authoritative
  acceptance receipt is generated and hashed by the Host from ledger evidence.

## Preconditions

On the Host:

1. Install one exact versioned Private Host asset after verifying its published
   SHA-256.
2. Run `agentops host init`, `agentops host start`, `agentops host doctor`, and
   `agentops host status`.
3. Manually start and sign in to Tailscale.
4. Review `agentops host tailscale-preview --https-port 8443`.
5. Apply only with explicit operator confirmation, then restart the Host:

   ```bash
   agentops host tailscale-apply --https-port 8443 --confirm
   agentops host restart
   agentops host console-url
   ```

6. Confirm that an unrelated Serve target, including OpenClaw on port 443, was
   not replaced.

On the Console:

1. Join the same trusted tailnet.
2. Do not clone the repository or install AgentOps MIS, Python, Node, Git, or an
   Agent Runtime.
3. Open the HTTPS Console URL without adding credentials to the URL.

## Browser Acceptance Flow

Perform the following from the Console browser:

1. Verify that an unauthenticated browser cannot read workspace data.
2. Sign in with a human account and open **Admin Console > Host Acceptance**.
3. Refresh Host readiness and verify ledger, knowledge, Worker, and adapter
   states are explicit (`ready`, `degraded`, or `unavailable`).
4. Create the low-risk acceptance marker task from the page and verify that its
   task ID is readable after refresh.
5. Open Dispatch Desk and submit one explicitly confirmed Hermes or OpenClaw
   customer task. Record only the returned task and run IDs.
6. Close the browser or disconnect the Console from the tailnet while the Host
   Worker continues. Reconnect and verify the same task and run.
7. Review the related Evaluation and Audit entries.
8. Decide the related prepared action or delivery approval with an authorized
   human account.
9. Review the related memory candidate; approve or reject it deliberately.
10. Download only the approved ID-addressed artifact from Task or Run Detail.
11. Generate the Host authority acceptance receipt for the completed run, then
    download its JSON through the authenticated browser.
12. Log out and verify that the receipt and artifact downloads fail closed.

## Pass Criteria

The run passes only when all of these are true:

- the Console required no project or Runtime dependency;
- HTTPS used a private tailnet URL and no Funnel/public route;
- human login, CSRF, Origin, workspace, and role enforcement remained active;
- the marker task and real customer task were created from the Console Session;
- a fresh explicitly confirmed Hermes or OpenClaw run completed on the Host;
- browser or tailnet disconnect did not stop or duplicate the Host run;
- reconnect showed the same task, run, evaluation, audit, memory, approval, and
  artifact evidence;
- approved artifact download succeeded and was audited;
- logout made protected reads/downloads fail;
- the Host receipt hash matched its canonical bounded payload;
- no credential, Session, CSRF value, setup code, raw prompt/response, private
  message, full transcript, database row content, or Host filesystem path was
  captured in the receipt, screenshots, recording, or repository.

## Bounded Evidence Record

Record only:

```text
acceptance date (UTC)
release tag and exact commit
Host operating-system major version
Console operating-system and browser major version
private HTTPS used: true/false
Tailscale Funnel used: false
task_id
run_id
adapter
approval_id
evaluation_id or evaluation status
memory_id and decision
artifact_id and bounded artifact metadata SHA-256
Host acceptance receipt_id and payload SHA-256
disconnect/reconnect passed: true/false
logout denial passed: true/false
final pass/fail and bounded failure reason
```

Do not record the tailnet DNS name, IP address, account email, username,
password, setup code, cookies, tokens, URL query, raw model content, knowledge
text, project files, database path, or unrestricted Host paths.

## Current Result

Host-side staging was refreshed on 2026-07-14 with
`v1.6.0-private-host-preview.24` at exact commit
`d52415f7d838c584faa61204fe27fafb4c622324`:

- GitHub download and published checksum verification passed;
- upgrade created a pre-update ledger backup and preserved user data;
- Host health, managed preview.24 production UI and real Hermes/OpenClaw Workers
  are ready; Worker Status/Fleet verify both process identities, report both as
  Host-managed without double-counting their Agent rows, and report zero
  unverified process claims;
- the published no-repository bootstrap passed release-consumer
  install gates from the public GitHub tag in a fresh temporary HOME without a
  repository on the consumer; this same-Mac receipt is not another-Mac proof;
- installed Agent Gateway CLI configuration is machine-only, confirmation
  gated, origin bound and separate from the browser Session;
- installed Gateway, Hermes and OpenClaw preflight checks passed without live
  execution;
- private Tailscale HTTPS uses port 8443 with one exclusive MIS handler;
- Funnel is disabled and the unrelated port 443 target remains unchanged;
- the private HTTPS Workspace returned HTTP 200;
- the self-validating existing Workspace account UI, installed
  HTML/CSS/JavaScript and exact installed version were verified locally and
  matched the release build;
- one Hermes and one OpenClaw Worker are running, and same-adapter duplicate
  Host ownership now fails closed without terminating an external Worker.

Fresh Hermes run `run_gw_242eac97293e` and OpenClaw run
`run_gw_23bb6ba9f13e` are `waiting_approval`. This is expected: machine
credentials staged the work but could not approve their own Agent Plans. No
Runtime execution is claimed for these runs until a human Owner approves them.

Owner bootstrap is still required. No physical second-device browser login,
task dispatch, approval, evaluation/audit/memory review, artifact download,
disconnect/reconnect or logout-denial receipt is attached yet. Automated
browser runtimes outside the Host tailnet are not accepted as a substitute.
No tailnet DNS name, IP address, account identifier, credential or setup code is
recorded in this document.
