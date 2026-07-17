# Local L4 Relay Transport Acceptance

Status: 3B transport primitive accepted locally; deployed Relay remains pending

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

## Boundaries

The frame smoke itself sends TLS-looking bytes and does not prove TLS; the
separate fixture proves only its own Host-side termination boundary. Unilateral
TLS half-close is explicitly not claimed because the stdlib `SSLSocket`
shutdown path used by this fixture would discard TLS wrapper state.

This slice does not yet implement SNI parsing, production Host-generated
certificates,
mutual tunnel authentication, DNS/ACME coordination, a deployed Relay daemon,
multi-Host routing, certificate rotation, or a stock-browser public endpoint.
It also does not claim crash-proof exactly-once byte delivery; product-level
idempotency remains at the Host ledger/action layer.
Those remain 3C work. The current Tailscale Serve path remains available as the
advanced private-network profile and is intentionally untouched.

## Next Slice

Add a loopback-only Host connector and fake Relay daemon around this envelope,
including authenticated Host registration, bounded reconnect state, explicit
shutdown, and a real TLS echo endpoint whose private key remains on the Host.
Then deploy the same authority-free routing boundary behind a stable domain for
3C physical browser acceptance.
