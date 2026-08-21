# Sixth AI (GPT-5.6 Sol) — System-Wide Multi-Project Execution Prompt v2

**Run from:** EACH PROJECT ROOT INDIVIDUALLY (see Project Sequence below)

**Context Window Strategy:** ~2.9M tokens available. Process **one project at a time** to avoid paywall. After each project completes (all tests green, committed), move to next.

---

## CRITICAL FIX FROM v1: MANDATORY SETUP PER PROJECT

**BEFORE starting any project, you MUST copy the logging directive into that project's root:**

```bash
# From D:\omniroute-monetizer
copy .sixthrules D:\neon_unified\.sixthrules
copy .sixthrules C:\god_ai\oioi\oioi\.sixthrules
copy .sixthrules C:\god_ai\ases_v3_1\.sixthrules
copy .sixthrules D:\ideation_to_prototype\.sixthrules
copy .sixthrules C:\god_ai\emergentsh\.sixthrules
```

**VERIFY before each project:**
```bash
ls -la <project-root>/.sixthrules   # Must exist
ls -la <project-root>/SIXTH_WORKLOG.md  # Must NOT exist yet (will be created)
```

Then **cd into the project root** and run all commands from there. The `.sixthrules` file in the CWD is what triggers mandatory incremental logging.

---

## MANDATORY OPERATING RULES (from `.sixthrules` + `AGENTS.md`)

1. **INCREMENTAL LOGGING TO `SIXTH_WORKLOG.md`** — Before each action, state plan in `SIXTH_WORKLOG.md` at the project root. After each command/edit/test, append findings with exact output. Never batch-log at end.
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
**cd command:** `cd D:\neon_unified`
**Intent:** Neon Architect v5.1 unified package — code-generation system. Primary issue: shared mutable class state breaking concurrent instances. Audit for multi-instance state collisions and code-gen pipeline robustness.
**Artifacts:** `AUDIT_REPORT.md`, `MASTER_BLUEPRINT.md`, `tests/baseline/test_baseline.py`, `tests/baseline/test_concurrency_baseline.py`
**Test command:** `python -m pytest tests/baseline/ -v`
**Baseline status (2026-08-19):** 11/11 PASS — already complete. Verify and log only.

### PROJECT 2: oioi (oiioii.ai filmmaker portfolio clone)
**Path:** `C:\god_ai\oioi\oioi` (git worktree at `C:\god_ai\.git\worktrees\neon_20260803-212543`)
**cd command:** `cd C:\god_ai\oioi\oioi`
**Intent:** oiioii.ai clone — filmmaker/director portfolio. Domain features: high-performance video grids (HLS/DASH), cinematic media loading, agency contact funnels. Backend: FastAPI production hardening (CORS, JWT, rate-limiting).
**Artifacts:** `AUDIT_REPORT.md`, `MASTER_BLUEPRINT.md`, `tests/baseline/` (video grid contract, agency funnel contract, CORS/JWT tests)
**Test command:** `python -m pytest tests/baseline/ -v`
**Baseline status (2026-08-19):** 77/77 PASS after manual fix. Verify, then execute audit gaps from AUDIT_REPORT.md.

### PROJECT 3: ases_v3_1
**Path:** `C:\god_ai\ases_v3_1`
**cd command:** `cd C:\god_ai\ases_v3_1`
**Intent:** ASES v3.1 — Autonomous Software Engineering System (Planner→Coder→Executor→Reviewer loop with n8n orchestrator). Audit agent handoffs, TDD gate validations, state persistence between agents, execution sandbox safety.
**Artifacts:** `AUDIT_REPORT.md`, `MASTER_BLUEPRINT.md` (thin — needs expansion), `tests/baseline/agent-handoff.test.ts`, `sandbox-safety.test.ts`, `state-persistence.test.ts`, `tdd-gate.test.ts`
**Test command:** `npx vitest run tests/baseline/`
**Baseline status (2026-08-19):** 9/9 PASS. Execute audit gaps from AUDIT_REPORT.md.

### PROJECT 4: ideation_to_prototype
**Path:** `D:\ideation_to_prototype`
**cd command:** `cd D:\ideation_to_prototype`
**Intent:** Selenium QA suite + Flask demo app. Audit for 100% test reliability, flaky Selenium selectors, Flask endpoint validation (Pydantic), robust error handling without leaking stack traces.
**Artifacts:** `AUDIT_REPORT.md`, `MASTER_BLUEPRINT.md`, `tests/baseline/test_architectural_baseline.py`
**Test command:** `python -m pytest tests/baseline/ -v`
**Baseline status (2026-08-19):** 5/5 PASS. Execute audit gaps from AUDIT_REPORT.md.

### PROJECT 5: emergentsh
**Path:** `C:\god_ai\emergentsh`
**cd command:** `cd C:\god_ai\emergentsh`
**Intent:** Next.js application with Docker container dependencies. Audit Next.js build pipeline, server-side/client-side hydration boundaries, multi-stage Dockerfile security, container health checks.
**Artifacts:** In parent `C:\god_ai\` — `AUDIT_REPORT.md`, `MASTER_BLUEPRINT.md` (thin), `tests/baseline/build_config.test.ts`, `build_pipeline.test.ts`, `docker_architecture.test.ts`, `hydration_boundary.test.ts`
**Test command:** `npx vitest run ../tests/baseline/build_config.test.ts ../tests/baseline/build_pipeline.test.ts ../tests/baseline/docker_architecture.test.ts ../tests/baseline/hydration_boundary.test.ts`
**Baseline status (2026-08-19):** 13/13 PASS after docker regex fix. Execute audit gaps from AUDIT_REPORT.md.

---

## PER-PROJECT EXECUTION TEMPLATE (COPY-PASTE FOR EACH)

```
=== STARTING PROJECT N: <name> ===

1. VERIFY SETUP:
   ls -la .sixthrules          # MUST EXIST
   ls -la SIXTH_WORKLOG.md     # MUST NOT EXIST YET

2. LOG ENTRY #1 — Project Start:
   Append to SIXTH_WORKLOG.md:
   ### [YYYY-MM-DD HH:MM] #1 — Starting Project N: <name>
   **Goal:** <one-line goal>
   **Initial Test Results:** (run baseline tests, capture exact output)
   **Gap Analysis:** (read AUDIT_REPORT.md, list gaps)
   **Plan:** (numbered steps)
   **Next Step:** Run baseline tests

3. RUN BASELINE TESTS:
   <test command>
   Log exact output to SIXTH_WORKLOG.md entry #2

4. FOR EACH GAP FOUND:
   a. Log entry: "Investigating <gap>"
   b. Write failing test (if defect) or add test (if missing feature)
   c. Fix source code (NOT tests — tests are contract)
   d. Re-run tests, log PASS
   e. Micro-commit: `git add -A && git commit -m "fix: <description>"`
   f. Update AUDIT_REPORT.md with "### Sixth AI Review — [date]"
   g. Update MASTER_BLUEPRINT.md with ✅ or deviation note

5. FINAL VERIFICATION:
   Re-run ALL baseline tests — must be 100% green
   Log final entry: "Project N COMPLETE — X/Y tests green"
   Commit SIXTH_WORKLOG.md

=== MOVE TO NEXT PROJECT ===
```

---

## FAILURE RECOVERY PROTOCOL

If paywall/crash hits mid-project:
- **On resume:** `cd <project-root> && cat SIXTH_WORKLOG.md` → restores exact context
- The `.sixthrules` file in the CWD ensures logging resumes automatically
- Micro-commits mean zero code loss — only the in-memory worklog entry is lost
- Re-read AUDIT_REPORT.md and MASTER_BLUEPRINT.md for architectural context

---

## ABSOLUTE COMMANDS REFERENCE

```bash
# neon_unified
cd D:\neon_unified && python -m pytest tests/baseline/ -v

# oioi
cd C:\god_ai\oioi\oioi && python -m pytest tests/baseline/ -v

# ases_v3_1
cd C:\god_ai\ases_v3_1 && npx vitest run tests/baseline/

# ideation_to_prototype
cd D:\ideation_to_prototype && python -m pytest tests/baseline/ -v

# emergentsh
cd C:\god_ai\emergentsh && npx vitest run ../tests/baseline/
```

---

## LOG FORMAT (from `.sixthrules` — MANDATORY)

```markdown
### [YYYY-MM-DD HH:MM] #<EntryNumber> — <TASK_TITLE>
**Goal:** <What you are attempting>
**Actions Taken:**
- Action 1
- Action 2
**Exact Command Output / Findings:**
- Output/error snippet (verbatim)
**Files Modified:**
- `path/to/file1`
- `path/to/file2`
**Verification Status:** PASS | FAIL | DEGRADED
**Next Step:** <What comes next>
```

---

## NEVER DO THESE

- ❌ Run from `D:\omniroute-monetizer` and expect `.sixthrules` to inherit
- ❌ Batch-log at the end of a project
- ❌ Edit `tests/baseline/` to make tests pass (tests are immutable contract)
- ❌ Skip micro-commits
- ❌ Move to next project before 100% baseline green
- ❌ Claim PASS without exact command output in log

---

## SUCCESS CRITERIA (ALL MUST BE TRUE)

- [ ] All 5 projects have `.sixthrules` in their root
- [ ] All 5 projects have `SIXTH_WORKLOG.md` with incremental entries
- [ ] All baseline tests green: neon(11) + oioi(77) + ases(9) + ideation(5) + emergentsh(13) = 115/115
- [ ] Each project has micro-commits per fix
- [ ] Each project has updated `AUDIT_REPORT.md` with "Sixth AI Review" section
- [ ] Each project has annotated `MASTER_BLUEPRINT.md`
- [ ] Zero test edits — only source fixes and new test additions