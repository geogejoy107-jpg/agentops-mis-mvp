# Private Host Backup and Restore Acceptance

Status: passed on isolated local state
Scope: private Host SQLite authority ledger

## Product Commands

```text
agentops host backup
agentops host backup-verify [--backup PATH]
agentops host restore --backup PATH --confirm-restore
```

`backup` uses the SQLite online backup API, writes a SHA-256 manifest, and may
run while the Host is serving requests. `restore` requires the managed Host to
be stopped and explicit confirmation. An existing ledger receives a separate
pre-restore safety copy before replacement.

## Verification

```bash
python3 -m py_compile \
  agentops_mis_cli/host.py \
  scripts/agentops_local_backup.py \
  scripts/private_host_backup_restore_smoke.py
python3 scripts/private_host_backup_restore_smoke.py
git diff --check
```

Result:

- backup SQLite integrity: `ok`;
- backup manifest hash: verified;
- backup and manifest permissions: private;
- unconfirmed restore: no write;
- restore while managed Host PID is alive: rejected;
- confirmed restore: ledger marker recovered;
- pre-restore safety copy: created;
- independent Host secrets file: unchanged by hash;
- hash-only Session/Token ledger state: explicitly included and treated as
  sensitive backup data;
- credential values and raw ledger rows: absent from command output;
- real user database: not used.

## Boundaries

- Credentials, logs, PID state, raw prompts/responses, and Runtime files are not
  part of this backup.
- The command backs up the SQLite authority ledger. External mutable project
  directories or future Host-managed Markdown source directories require a
  separate directory backup contract before whole-host disaster recovery can
  be claimed.
- Upgrade migration and rollback across two product versions remain a Release
  Candidate acceptance item.
