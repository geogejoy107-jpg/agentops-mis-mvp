# SSH Executor v0.3

## Goal

Connect the standalone Research Lab to an approved Linux server without making SSH or the remote filesystem the scientific authority.

A server profile stores connection and capability metadata such as profile name, host, user, port, remote root, Python executable, host-key policy, timeouts, concurrency and staging limits. Authentication material stays outside the profile.

## Flow

```text
validate spec and server profile
-> freeze effective protocol hash
-> build deterministic allowlisted archive
-> stage through non-interactive OpenSSH
-> execute remote supervisor
-> collect logs, metrics, actuals and artifacts
-> safe local extraction
-> protocol diff and scientific claim gate
```

Strict host-key verification is the default. A reviewed first-enrollment mode is optional. Disabled host verification is not supported.

## Current limits

- attached SSH session rather than a durable remote daemon;
- no remote reconciliation command yet;
- no scheduler or GPU allocation integration;
- no production claim until a real authorized server test exists.
