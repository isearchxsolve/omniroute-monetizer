# scratch/ — Evidence Trail (Not Production)

This directory contains **probe, investigation, and one-off repair scripts** that
make up the evidence trail for `MASTER_WORKLOG.md`. They are NOT production code.

## Conventions

| Directory | Meaning | Example |
|---|---|---|
| `scratch/` | evidence trail — scripts referenced by worklog entries | `audit_git_history.py` |
| `scratch/archive/` | dead / superseded / retracted scripts — kept for reference | `raise_catalog_ttl.py` (retracted #25) |
| `scripts/automation/` | **production** — scheduled, idempotent, tested | `oauth_keepalive.py` |

## Rules

- **Never** move a script that is referenced in `MASTER_WORKLOG.md` out of
  `scratch/` — it is part of the evidence trail.
- Move clearly-dead / retracted / superseded scripts to `scratch/archive/` with a
  `README.md` explaining why they are archived.
- `scratch/` is committed to git but its contents are diagnostic; treat any file
  here as "may contain redacted credential references" — run the G9 audit
  (`scratch/audit_git_history.py`) before shipping.
- Production logic belongs in `scripts/automation/`, never here.

## Notable probes

- `audit_git_history.py` — G9 secret-in-history audit (redacted output).
- `watch_omniroute_release.py` — npm release watcher (scheduled).
- `export_sessions_cdp.py` — CDP session export pattern (worklog #34).
