# archive/legacy-automation-2026-08-16 — Superseded Automation Scripts

These scripts were the Phase-1/Phase-2 one-off automation runs (manual provider
handoff v12, provider recovery v11, UI diagnostics v10, enable noauth). They are
**superseded** by the production scheduled automation in `scripts/automation/`:

| Production (current) | Supersedes |
|---|---|
| `oauth_keepalive.py` | provider refresh/handoff manual runs |
| `health_watch.py` | provider recovery smoke runs |
| `stall_monitor.py` | UI diagnostic manual runs |
| `acceptance_watch.py` | manual acceptance re-runs |
| `backup_state.py` | manual backup copies |
| `watch_omniroute_release.py` | release-check manual runs |

## Rules

- **Do not execute** anything in this folder; it is reference-only.
- Keep it out of `scripts/automation/` so the 0-byte `provider_registry.py`
  stub and the old discovery pattern are not confused with current production.
- This move shrinks the surface for G9-style secret leaks going forward.
