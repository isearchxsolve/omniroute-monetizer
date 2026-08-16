# archive/reports-2026-08-15 — Superseded Reports

> These reports were the authoritative status documents **before** the OmniRoute
> Monetizer reached production readiness (20/20 acceptance, MONITIZER_READY).
> They are preserved here for audit/history; they do **not** reflect current state.

## Current source of truth (active)

| Doc | Purpose |
|---|---|
| `MASTER_WORKLOG.md` (repo root) | single cumulative journal — read first |
| `POST_AUDIT_GAPS.md` (repo root) | current gap list (P1–P8, G1–G14) |
| `POST_AUDIT_FIXES.md` (repo root) | current fix plan + status |
| `docs/INSTALLATION.md` | reproducible install |
| `docs/OPS_RUNBOOK.md` | operations + upgrade + restore |
| `acceptance_tests.py` (repo root) | T1–T20 acceptance suite |

## Archived here

- `STATUS.md`, `MONETIZER_FINAL_STATUS.md`, `MONETIZER_FINAL_REPORT.md` — superseded
  by `acceptance_tests.py` verdicts.
- `PERFORMANCE_BASELINE.md`, `PERFORMANCE_OPTIMIZATIONS.md`,
  `PERFORMANCE_REGRESSION_REPORT.md`, `OMNIROUTE_PERFORMANCE_AUDIT_COMPLETE.md` —
  superseded by `docs/OPS_RUNBOOK.md` §3 and T13–T15.
- `ROOT_CAUSE_ANALYSIS.md`, `COMPREHENSIVE_ROOT_CAUSE_ANALYSIS.md`,
  `COMPREHENSIVE_AUDIT_AND_FIXES.md`, `OMNIROUTE_RCA_AND_FIXES_FINAL.md` — Phase-1
  audits; superseded by `MASTER_WORKLOG.md` (which captures every fix incrementally).
- `ANALYSIS_COMPLETE_SUMMARY.md`, `MASTER_FIX_STRATEGY.md`, `QUICK_FIX_ROADMAP.md`,
  `DEFERRED_ACTIONS.md`, `HANDOFF_PROMPT_PHASE2.md` — superseded by
  `POST_AUDIT_GAPS.md` + `POST_AUDIT_FIXES.md`.
- `AUTONOMOUS_CREDENTIAL_HARVESTING_BREAKTHROUGH.md`,
  `AUTOMATION_REQUIREMENTS_VS_ACHIEVED.md` — superseded by `docs/` specs and
  `scripts/automation/` code.
- `STATE_MACHINE.md`, `PROVIDER_POLICY.md`, `IMPLEMENTATION_PLAN.md` — stale root
  duplicates; the active versions live in `docs/` (root copies were superseded).
- `KIMI_K3_VSCODE_SETUP_GUIDE.md`, `COPILOT_CHAT_ERRORS_ANALYSIS.md` — one-off
  integration/analysis notes superseded by `docs/` and the worklog.
