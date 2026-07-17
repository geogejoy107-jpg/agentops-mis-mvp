# Local L4 Relay Transport Acceptance

Status: 3B transport primitive and loopback composition accepted locally; deployed Relay remains pending

## Scope

This slice makes the browser-only Relay contract executable over temporary
`127.0.0.1` TCP connections without changing
the installed Host, Tailscale Serve, Funnel, router configuration, or any
network interface. It is a dependency-free, in-process loopback protocol test,
not a public endpoint and not a claim that ordinary browser-only onboarding is
complete.

The Relay envelope carries a route reference, connection epoch, monotonic
message ID, request correlation ID, direction, protocol version, and payload
byte count. The trusted connection context separately binds route, direction,
and epoch. Event evidence omits both untrusted references entirely. Application
bytes are forwarded unchanged and are never included in Relay event evidence.
The Relay has no task, run, approval, memory, artifact, user, or audit authority
database.

## Executable Contract

Run:

```bash
python3 scripts/local_l4_relay_transport_smoke.py
python3 scripts/private_host_relay_tls_smoke.py
python3 scripts/local_fake_relay_tunnel_smoke.py
python3 scripts/relay_persistent_epoch_smoke.py
python3 scripts/relay_tls_authenticated_tunnel_smoke.py
python3 scripts/relay_connector_service_smoke.py
python3 scripts/local_relay_connector_supervisor_smoke.py
```

The smoke proves:

- exact opaque bytes travel Console-to-Host and Host-to-Console;
- a new connection epoch restarts the message sequence at one;
- duplicate messages and request IDs inside the retained replay window, stale
  epochs, sequence gaps, spoofed connection context, and oversized frames fail
  closed;
- destination write failures become bounded `destination_unavailable` evidence
  without recording socket errors or application bytes; because `sendall` may
  have delivered a prefix, the failed epoch is invalidated and only a fresh
  connection epoch may continue;
- control metadata is capped at 4 KiB and payload frames at 256 KiB;
- reads and writes use a transport-enforced socket deadline and no unbounded
  in-process payload queue;
- replay state is capped at 256 directional streams, request replay history at
  4,096 references, and the bounded in-memory event buffer at 256 metadata
  records; route release recovers replay capacity, refuses active reservations,
  and none contains application bytes or correlatable route/request references;
- only temporary `127.0.0.1` listeners are opened; no durable state is written
  and no Tailscale command is invoked.

The second, separate raw-proxy fixture performs a real TLS handshake through a
byte-forwarding Relay.
The temporary certificate and private key are loaded only by the Host TLS
endpoint. The client verifies the exact Host certificate fingerprint, the Host
and client verify exact binary request/response bytes, and Relay evidence is
restricted to bounded direction/status/byte-count records. This proves the
fixture Relay did not terminate that TLS session or retain application
plaintext, payload hashes, certificate fingerprints, key material, or paths.
It does not yet compose TLS with the framed tunnel primitive or prove an
outbound Host-initiated connector.

`scripts/local_fake_relay_tunnel_smoke.py` then composes the boundary with a
Host-initiated control connection and one Host-initiated data connection per
browser connection. The fake Relay authenticates bounded control frames,
rejects unknown routes, bad MACs, stale epochs, registration replay and data
connection replay. A replacement control epoch cannot claim a pending browser
created by the previous epoch. A Host data connection is marked authenticated
only after a bounded Relay acknowledgement. Unauthenticated connector
handshakes are capped and are actively closed during Relay shutdown. The
browser completes a real TLS handshake with
the Host endpoint through the opaque data connection. Two successive connector
epochs reuse the same Host TLS process and preserve exact binary
request/response bytes and the Host certificate fingerprint. Relay evidence
remains limited to allowlisted status, direction and byte-count fields;
forwarding failure cannot be recorded as successful forwarding.

`scripts/local_relay_connector_supervisor_smoke.py` adds a disabled-by-default,
in-process supervisor around the Host connector. It proves deterministic
bounded backoff, strictly increasing process-lifetime epochs, recovery after a
forced control-connection loss, a second real Host-terminated TLS round trip,
bounded allowlisted status history, and bounded permanent stop. The supervisor
accepts only literal loopback test endpoints and owns no listener, OS service,
network configuration, persistent credential, or Tailscale state.

`scripts/relay_persistent_epoch_smoke.py` adds the crash-safe epoch primitive
needed by that supervisor. The allocator writes the next epoch before network
use under an exclusive file lock, atomically replaces a `0600` schema-bound
state file inside a `0700` directory, fsyncs both file and directory, and
rejects corruption, connector mismatch, broad permissions and symlinks. The
state stores only a hash-derived connector reference and the last epoch; it
omits endpoint, route, key material and filesystem paths. A restarted allocator
and 16 concurrent allocators cannot reuse an epoch. The supervisor integration
uses this allocator for reconnects and reports only that crash persistence is
enabled, never the state path or connector identity. Corrupt or mismatched
state stops before network connection with only the bounded
`epoch_allocation_failed` status code.

`scripts/relay_tls_authenticated_tunnel_smoke.py` adds the production tunnel
authentication shape without deploying an endpoint. Plain connector transport
remains restricted to literal loopback. A non-loopback-capable connector must
receive a caller-owned TLS context with certificate and hostname verification.
The loopback fixture proves an untrusted Relay certificate fails before HMAC
registration, a trusted TLS connection still rejects the wrong Host HMAC key,
and both control and per-browser data connections use Relay-authenticated TLS.
Inside that outer tunnel, the browser verifies a different Host application
certificate and completes an exact binary round trip with TLS terminating at
the Host endpoint. Relay evidence remains payload-, key-, certificate-, path-,
hostname- and port-free.

`scripts/relay_connector_service_smoke.py` runs the same connector as a real
foreground subprocess suitable for later Host/LaunchAgent ownership. Its
strict `0600` config/secret inputs and atomic `0600` status/epoch outputs live
under `0700` directories. Disabled configuration exits without reading a
secret or attempting a connection; invalid secrets fail before network use.
The enabled service establishes nested TLS, survives a forced Relay restart
with a higher persisted epoch, completes a second browser-to-Host TLS round
trip, and writes a clean stopped state on `SIGTERM`. Status and process output
omit endpoint, route, key, certificate path and filesystem paths.

## Boundaries

The frame smoke itself sends TLS-looking bytes and does not prove TLS; the
separate fixture proves only its own Host-side termination boundary. Unilateral
TLS half-close is explicitly not claimed because the stdlib `SSLSocket`
shutdown path used by this fixture would discard TLS wrapper state.

The composed connector remains a loopback fake Relay with a single route,
short test deadlines and an in-memory temporary tunnel key. It does not prove a
deployed service, internet routing, long-lived browser sessions, TLS half-close
or transport exactly-once delivery.

The foreground service is not yet wired into Host startup or the installer. Its
epoch can now be crash-persistent when the protected allocator is supplied,
while backoff/status state remains process-local. This proves the reconnect and
epoch identity behavior needed by a later Host-owned connector daemon, not the
deployed Relay itself.

This slice does not yet implement SNI parsing, production Host-generated
certificates, DNS/ACME coordination, a deployed Relay daemon,
multi-Host routing, certificate rotation, or a stock-browser public endpoint.
It also does not claim crash-proof exactly-once byte delivery; product-level
idempotency remains at the Host ledger/action layer.
Those remain 3C work. The current Tailscale Serve path remains available as the
advanced private-network profile and is intentionally untouched.

## Next Slice

Wire the accepted disabled-by-default foreground connector into the Host
lifecycle with certificate provisioning and Owner enable/disable controls.
Then add SNI/multi-Host routing and deploy the same authority-free boundary
behind a stable domain for 3C physical browser acceptance.
