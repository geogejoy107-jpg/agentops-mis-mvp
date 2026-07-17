# Local L4 Relay Transport Acceptance

Status: 3B transport primitive accepted locally; deployed Relay remains pending

## Scope

This slice makes the browser-only Relay contract executable over temporary
`127.0.0.1` TCP connections without changing
the installed Host, Tailscale Serve, Funnel, router configuration, or any
network interface. It is a dependency-free, in-process loopback protocol test,
not a public endpoint and not a claim that ordinary browser-only onboarding is
complete.

The Relay envelope carries only a random route reference, connection epoch,
monotonic message ID, request correlation ID, direction, protocol version, and
payload byte count. Application bytes are forwarded unchanged and are never
included in Relay event evidence. The Relay has no task, run, approval, memory,
artifact, user, or audit authority database.

## Executable Contract

Run:

```bash
python3 scripts/local_l4_relay_transport_smoke.py
```

The smoke proves:

- exact opaque bytes travel Console-to-Host and Host-to-Console;
- a new connection epoch restarts the message sequence at one;
- duplicate messages, duplicate request IDs, stale epochs, sequence gaps, and
  oversized frames fail closed;
- destination write failures become bounded `destination_unavailable` evidence
  without recording socket errors or application bytes;
- control metadata is capped at 4 KiB and payload frames at 256 KiB;
- forwarding uses blocking `sendall`, so socket backpressure is propagated
  instead of accumulating an unbounded in-process queue;
- replay state is capped at 256 directional streams, request replay history at
  4,096 references, and the bounded in-memory event buffer at 256 metadata
  records; none contains application bytes;
- only temporary `127.0.0.1` listeners are opened; no durable state is written
  and no Tailscale command is invoked.

## Boundaries

This slice does not yet implement SNI parsing, Host-generated certificates,
mutual tunnel authentication, DNS/ACME coordination, a deployed Relay daemon,
multi-Host routing, certificate rotation, or a stock-browser public endpoint.
Those remain 3C work. The current Tailscale Serve path remains available as the
advanced private-network profile and is intentionally untouched.

## Next Slice

Add a loopback-only Host connector and fake Relay daemon around this envelope,
including authenticated Host registration, bounded reconnect state, explicit
shutdown, and a real TLS echo endpoint whose private key remains on the Host.
Then deploy the same authority-free routing boundary behind a stable domain for
3C physical browser acceptance.
