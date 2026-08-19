# Sixth AI (GPT-5.6 Sol) — System-Wide Multi-Project Execution Prompt

**Run from:** `D:\omniroute-monetizer` (this directory — inherits `.sixthrules` + `AGENTS.md`)

**Context Window Strategy:** ~2.9M tokens available. Process **one project at a time** to avoid paywall. After each project completes (all tests green, committed), move to next.

---

## MANDATORY OPERATING RULES (from `.sixthrules` + `AGENTS.md`)

1. **INCREMENTAL LOGGING TO `SIXTH_WORKLOG.md`** — Before each action, state plan. After each command/edit/test, append findings with exact output. Never batch-log at end.
2. **TEST-DRIVEN EXECUTION** — Run the modular DI tests in `tests/baseline/` **first** to see failures. Implement fixes to make them pass. Tests are the contract — never weaken or remove them.
3. **MICRO-COMMITS** — `git commit` after **each passing test** or logical fix. Prevents data loss on paywall crash.
4. **PLUS/MINUS ON BLUEPRINT** — You are the Senior Engineer. Aider (Gemini) produced the initial blueprint. You **critique it**: add missing gaps, strike wrong approaches, correct architectural decisions. Annotate inline: `// SIXTH-AI-DEVIATION: [reason]`.
5. **THREE ARTIFACTS PER PROJECT** — Update all three as you go:
   - `AUDIT_REPORT.md` → Append `### Sixth AI Review — [date]` with gaps Aider missed, corrections made
   - `tests/baseline/` → **Add** new tests for gaps you discover during implementation. **Never remove** baseline tests.
   - `MASTER_BLUEPRINT.md` → Annotate with deviations, decisions, "done" checkmarks
6. **5-LEVEL GAP TAXONOMY** — Address all levels in order:
   - L1: Business/Vision Gap (does it achieve the product vision?)
   - L2: Feature Gap (missing domain features)
   - L3: Architectural Gap (wrong boundaries, missing DI, hydration)
   - L4: Structural Gap (monoliths, hidden state, circular deps)
   - L5: Defects/Bugs (precision, null, races)
7. **ABSOLUTE PATHS** — All project paths are absolute. Use them directly.

---

## PROJECT SEQUENCE (5 Projects)

### PROJECT 1: neon_unified
**Path:** `D:\neon_unified`
**Intent:** Neon Architect v5.1 unified package — code-generation system. Primary issue: shared mutable class state breaking concurrent instances. Audit for multi-instance state collisions and code-gen pipeline robustness.
**Artifacts:** `AUDIT_REPORT.md`, `MASTER_BLUEPRINT.md`, `tests/baseline/test_baseline.py`, `tests/baseline/test_concurrency_baseline.py`

### PROJECT 2: oioi (oiioii.ai filmmaker portfolio clone)
**Path:** `C:\god_ai\oioi\oioi` (note: git worktree at `C:\god_ai\.git\worktrees\neon_20260803-212543`)
**Intent:** oiioii.ai clone — filmmaker/director portfolio. Domain features: high-performance video grids (HLS/DASH), cinematic media loading, agency contact funnels. Backend: FastAPI production hardening (CORS, JWT, rate-limiting).
**Artifacts:** In git worktree — `AUDIT_REPORT.md`, `MASTER_BLUEPRINT.md`, `tests/baseline/` (video grid contract, agency funnel contract, CORS/JWT tests)

### PROJECT 3: ases_v3_1
**Path:** `C:\god_ai\ases_v3_1`
**Intent:** ASES v3.1 — Autonomous Software Engineering System (Planner→Coder→Executor→Reviewer loop with n8n orchestrator). Audit agent handoffs, TDD gate validations, state persistence between agents, execution sandbox safety.
**Artifacts:** `AUDIT_REPORT.md`, `MASTER_BLUEPRINT.md` (thin — needs expansion), `tests/baseline/agent-handoff.test.ts`, `sandbox-safety.test.ts`, `state-persistence.test.ts`, `tdd-gate.test.ts`

### PROJECT 4: ideation_to_prototype
**Path:** `D:\ideation_to_prototype`
**Intent:** Selenium QA suite + Flask demo app. Audit for 100% test reliability, flaky Selenium selectors, Flask endpoint validation (Pydantic), robust error handling without leaking stack traces.
**Artifacts:** `AUDIT_REPORT.md`, `MASTER_BLUEPRINT.md`, `tests/baseline/test_architectural_baseline.py`

### PROJECT 5: emergentsh
**Path:** `C:\god_ai\emergentsh`
**Intent:** Next.js application with Docker container dependencies. Audit Next.js build pipeline, server-side/client-side component hydration, Docker container build architecture for production readiness.
**Artifacts:** In parent `C:\god_ai\` — `AUDIT_REPORT.md`, `MASTER_BLUEPRINT.md` (thin), `tests/baseline/build_config.test.ts`, `build_pipeline.test.ts`, `docker_architecture.test.ts`, `hydration_boundary.test.ts`

---

## EXECUTION PROTOCOL PER PROJECT

```
FOR EACH PROJECT IN SEQUENCE:
  1. cd <project_path>
  2. READ all 3 artifacts (audit, blueprint, tests)
  3. RUN baseline tests — capture exact failures
  4. LOG to SIXTH_WORKLOG.md: "Starting Project X — test failures: [list]"
  5. FOR each failing test / gap in priority order (L1→L5):
       a. Implement fix per blueprint (or your corrected approach)
       b. Run test — verify PASS
       c. Micro-commit: git add -A && git commit -m "fix: [specific fix]"
       d. Log to SIXTH_WORKLOG.md with exact command output
       e. Annotate MASTER_BLUEPRINT.md with deviation or ✅ done
  6. ADD new tests for any gaps you discover during implementation
  7. RUN FULL TEST SUITE — all must pass
  8. Append to AUDIT_REPORT.md: "### Sixth AI Review — [date] — [gaps found, corrections, decisions]"
  9. Log project completion to SIXTH_WORKLOG.md
  10. MOVE TO NEXT PROJECT
```

---

## CRITICAL REMINDERS

- **DO NOT RUN TESTS IN SIXTH AI IF THEY BURN TOKENS EXCESSIVELY** — Run them in terminal, read output, log results. You verify mentally/verbally.
- **PAYWALL AWARENESS** — One massive prompt (~3M tokens). If you hit limit mid-project, your micro-commits and `SIXTH_WORKLOG.md` preserve progress. Next session picks up from log.
- **NO FABRICATION** — Never claim a test passed without terminal output evidence in the log.
- **SECRETS** — Redact all tokens as `[REDACTED]`.
- **OMNIROUTE AVAILABLE** — `http://localhost:20128/v1` with key `sk-omniroute` for any LLM calls you need during execution.

---

## START COMMAND

When you launch Sixth AI in VS Code from `D:\omniroute-monetizer`, paste this entire prompt. It will begin with Project 1 (neon_unified) and proceed sequentially.

**Begin with:** Read `D:\neon_unified\AUDIT_REPORT.md`, `D:\neon_unified\MASTER_BLUEPRINT.md`, and `D:\neon_unified\tests\baseline\*.py`. Run the tests. Log to `SIXTH_WORKLOG.md`. Execute.