# scratch/archive/ — Retracted / Superseded Probes

Scripts here were **retracted or superseded** and are kept only for reference.

| Script | Why archived |
|---|---|
| `raise_catalog_ttl.py`, `raise_catalog_ttl2.py` | retracted (worklog #25 — unsafe invalidation gap) |
| `find_pool_logic*.py` (8 variants) | superseded by `scratch/find_rebuild_trigger.py` |
| `nuke_rate_limits.py` | AGENTS.md anti-pattern #1 (direct DB manipulation) — never run |
| `fix_combos_robust.py`, `hardcode_combos.py`, `fix_auto_pro_coding.py`, `fix_pro_coding.py` | superseded by `scratch/repair_old_combos_db.py` |

## Rules

- **Do not execute** anything in this folder.
- The live `scratch/*.py` scripts referenced by `MASTER_WORKLOG.md` remain in
  place as the evidence trail (G13 convention — see `scratch/README.md`).
