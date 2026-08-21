# MASTER REMEDIATION PROMPT — Four Vibe-Coding Platforms (Verify → Fix → Prove)

> Paste this entire document into the executing agent session. It is self-contained.
> Source evidence: `D:\omniroute-monetizer\MASTER_WORKLOG.md` entries #1005–#1008 (read them first if accessible).

---

## 0. MISSION

You are remediating four vibe-coding platform repos that were deep-audited on 2026-08-22.
Each repo is BOTH a software product (Layer 1: its own discipline) and a generator of
software products (Layer 2: the apps it emits). Both layers must be fixed.

Targets, in mandatory execution order:

1. `D:\neon_unified` (Neon Architect v5.1.0) — audit score 5.9/10
2. `C:\god_ai\ases_v3_1` (ASES) — audit score ~7.2/10
3. `C:\god_ai\emergentsh` (emergent.sh clone) — audit score ~4.5/10
4. `D:\ideation_to_prototype` (idea-terminal-engine) — audit score ~6.8/10

Order rationale: start where fixes are cheapest and unblock everything else
(reproducibility gates), then fail-closed gates, then sandboxing, then live proof (most expensive, last).

---

## 1. NON-NEGOTIABLE EXECUTION RULES

1. **Event-driven state loop.** For EVERY gap: [VERIFY] → [FIX] → [TEST] → [LOG] → [COMMIT],
   one gap at a time. Never batch logs. Never hold more than one gap's changes unlogged.
2. **Verify BEFORE fixing.** Reproduce each gap with an exact command first. If a gap does
   NOT reproduce, log that with the command + output and SKIP the fix — do not fix what
   you cannot reproduce.
3. **Log honestly.** Failures get logged with actual error output. Never mark broken work
   done. A skipped/blocked gap is logged as BLOCKED with the exact reason.
4. **No secrets in logs or code.** Redact all tokens/keys. `.env.example` stays valueless.
5. **Fail CLOSED.** Any gate you touch must block release on failure. A gate that returns
   "approved/skip" on its own failure is a defect by definition.
6. **Per-repo worklog.** Create/append `REMEDIATION_WORKLOG.md` at each repo root:
   `### [YYYY-MM-DD HH:MM] GAP-<repo>-<n> — <title>` with Goal / Repro command / Root cause /
   Fix / Test output (verbatim) / Commit hash. Commit after each logged gap.
7. **No destructive shortcuts.** Never edit databases directly, never delete evidence files,
   never weaken a test to make it pass. If a test is wrong, fix the test AND log why.
8. **Distinguish failure classes.** Inference/network errors ≠ verification failures. Never
   conflate them in code or logs.

---

## 2. PROJECT 1 — `D:\neon_unified`

### GAP-NU-1 (FATAL, reproducibility) — suite does not collect from clean checkout
- **Repro:** `cd /d D:\neon_unified && python -m pytest --collect-only -q`
- **Expected defect:** 1 collection error: `tests\baseline\test_baseline.py:8` →
  `oiioii_clone_final\src\jobs.py:13: from src.models import ...` →
  `ModuleNotFoundError: No module named 'src'`. No conftest.py exists in the repo.
- **Fix:** add a root `conftest.py` that inserts each `oiioii_clone*` package root into
  `sys.path` deterministically (or convert the generated app's imports to package-relative —
  prefer conftest; it doesn't mutate generated output).
- **Acceptance:** `python -m pytest --collect-only -q` → 0 errors; `python -m pytest -q` →
  full suite passes. Paste exact counts into the worklog. The fleet claim "1,160/1,160" must
  become reproducible with a pinned command in README.

### GAP-NU-2 (HIGH, fail-open QA) — vision loop is opt-in and degrades to skip
- **Evidence:** `generation_core.py::_run_qa_pass` returns `None` (="no QA signal") when
  Playwright missing, no `_preview_starter`, or server fails. `qa_self_heal.py` is never
  invoked by the generation path.
- **Fix:** (a) make the QA pass DEFAULT-ON for web stacks (`fastapi-react`,
  `nextjs-postgres`) with a built-in static/dev preview starter; (b) replace `None`-on-failure
  with an explicit `QAResult(passed=False, reason=...)` recorded in `GenerationResult.errors`
  unless the user explicitly passes `--no-qa`; (c) wire `qa_self_heal.py`'s loop as the
  repair path when QA fails (max 5 rounds, already implemented there).
- **Acceptance:** a generated `fastapi-react` project with a deliberately broken selector
  fails generation (fail-closed) and self-heal repairs it; regression test covers both.

### GAP-NU-3 (HIGH, no sandbox) — generated tests run as host subprocess
- **Evidence:** `generation_core.py::_run_tests` uses `subprocess.run(cmd, cwd=project_dir)`.
- **Fix:** add a Docker execution mode mirroring ases_v3_1's hardened pattern
  (`--network none --read-only --cpus 1.0 --memory 512m`, command allowlist, path jail).
  Keep host mode only behind an explicit `--unsafe-host-exec` flag, default Docker when
  Docker is available; when Docker is unavailable AND flag absent → fail closed.
- **Acceptance:** test proving a generated `tests/` attempting to write outside the project
  dir is blocked in Docker mode.

### GAP-NU-4 (MED, multi-stack gap) — only 2 of 4 stacks have test runners
- **Evidence:** `_run_tests` returns "No automated runner wired for {stack} in v5 core yet"
  for `expo-node` and `flutter-fastapi`.
- **Fix:** wire `npm test`/`jest` for expo-node; syntax+analyze gate (`dart analyze` when
  SDK present) for flutter-fastapi. Where the host lacks toolchains (no JDK/Android SDK —
  documented limitation #6), fail closed with an explicit BLOCKED record, never silent pass.
- **Acceptance:** each stack returns a real TestRunResult; missing-toolchain case is a
  recorded, loud skip that blocks release certification.

### GAP-NU-5 (MED, misleading output) — flagship output is a stub
- **Evidence:** `oiioii_clone_final/backend/main.py` = 1 line; `frontend/styles.css` = 0 bytes;
  5 of 8 `oiioii_clone*` dirs have no frontend.
- **Fix:** either regenerate `oiioii_clone_final` to completeness via the fixed pipeline, or
  rename/delete the `_final` suffix and document which clone is the reference output.
  Do not ship a directory named `final` that cannot run.
- **Acceptance:** reference output boots (`uvicorn`/static serve) and its own tests pass.

### GAP-NU-6 (FATAL, live proof) — no successful live generation on record
- **Evidence:** FLEET_WORKLOG step 16: `success=False`, consistency 3→1, test-repair failed.
- **Fix:** after GAP-NU-1..5 are green, run ONE clean `fastapi-react` live generation with a
  real NIM key (one job at a time; respect 429 backoff). Capture full stdout log.
- **Acceptance:** `success=True`, consistency `[OK] import graph clean`, generated-app tests
  pass, QA pass result recorded. Log run_id + metrics. If NIM quota blocks you: log BLOCKED
  with the exact HTTP evidence. Do not fake it.

### GAP-NU-7 (MED, monolith backlog) — 641KB single-file agents
- **Fix (minimal):** do NOT attempt a full refactor in this sweep. Add
  `docs/MONOLITH_EXTRACTION_PLAN.md` mapping the 17 tool classes in `neon_architect.py` to
  proposed modules, and freeze the file with a lint rule forbidding growth (ruff max-lines
  or pre-commit size check).

---

## 3. PROJECT 2 — `C:\god_ai\ases_v3_1`

### GAP-AS-1 (FATAL, golden path blocked) — sandbox path mismatch
- **Repro:** read `agent_service/sandbox_executor.py` (latest commit 730255c1): targets
  `/tmp/ases_sandboxes/{execution_id}` (UNDERSCORE); real sandbox root created by
  `agent_service/sandbox.py` is `/tmp/ases-sandboxes` (HYPHEN).
- **Fix:** single source of truth — export `SANDBOX_ROOT` from `sandbox.py` and import it in
  `sandbox_executor.py`. Delete the duplicated literal.
- **Acceptance:** regression test asserting executor's root == sandbox's root; golden-path
  test now reaches the real sandbox dir.

### GAP-AS-2 (FATAL, fails open) — visual reviewer approves on its own failure
- **Evidence:** `agent_service/visual_reviewer.py` `_visual_skip()` returns
  `{"approved": True}`; screenshot commands (`npm install`, `npm start &`,
  `python .ases_screenshot.py`) are NOT in `sandbox.py`'s command ALLOWLIST frozenset,
  containers run `--network none` and have no Playwright → reviewer can never succeed →
  always skips → always "approved".
- **Fix:** (a) bake Playwright/chromium into the sandbox image OR add the exact commands to
  the allowlist with network exception for npm registry (scoped, logged); (b) change skip
  semantics: `_visual_skip()` must return `{"approved": False, "reason": "visual gate
  unavailable"}` and block release unless the job explicitly declares `visual_review: optional`.
- **Acceptance:** test proving reviewer failure blocks release; one real screenshot round-trip
  on a trivial generated page.

### GAP-AS-3 (HIGH, all-mocked E2E) — green suite shipped two fatal flaws
- **Fix:** add ONE true end-to-end golden-path test (real sandbox, real tiny generation,
  real pytest inside container) marked `@pytest.mark.e2e`, run in CI. Mocked suites may stay
  for unit speed but must not be the release gate.
- **Acceptance:** `pytest -m e2e` passes with zero mocks in the request path.

### GAP-AS-4 (MED, dead code) — `mobile_stacks.py` imported nowhere
- **Fix:** wire RN/Expo/Flutter definitions into the planner's stack selection, or delete the
  file and the doc claims. Dead capability claims are a monetization lie.
- **Acceptance:** grep proves import-or-delete; docs match reality.

---

## 4. PROJECT 3 — `C:\god_ai\emergentsh`

### GAP-EM-1 (FATAL, auth) — forgeable JWT + unauthenticated API
- **Evidence:** `backend/app/core/auth.py`: `SECRET_KEY = os.getenv("SECRET_KEY",
  "your-secret-key-change-in-production")`. `backend/app/api/pipeline.py`: no auth on
  `/run /stream /export /jobs /credits`.
- **Fix:** fail closed at startup if `SECRET_KEY` env is absent or equals the known default
  (refuse to boot, loud error). Add auth dependency to all `/api/pipeline/*` routes.
- **Acceptance:** boot-without-SECRET_KEY test (expects refusal); unauthenticated request to
  each route → 401 test.

### GAP-EM-2 (FATAL, tenancy) — credits are one global in-memory counter
- **Evidence:** `pipeline.py` `USER_CREDITS = 10` global; `_JOBS`/`_JOB_QUEUES` in-memory dicts.
- **Fix:** per-user credit ledger keyed by authenticated identity, persisted (SQLite via the
  app's ORM is fine); jobs owned per user. No cross-user visibility.
- **Acceptance:** two-user isolation test: user A spending credits never touches user B;
  restart preserves ledger.

### GAP-EM-3 (HIGH, streaming parity) — `stream_run()` has no retry loop
- **Evidence:** `backend/agent_pipeline.py` (610 lines): `run()` retries; `stream_run()` —
  the path the UI actually uses — does not.
- **Fix:** extract the retry policy into one function used by BOTH paths; stream retries must
  not duplicate already-yielded SSE events (resume-from-stage semantics).
- **Acceptance:** test injecting a transient failure mid-stream → stream completes via retry.

### GAP-EM-4 (HIGH, fake moat) — FrontendAgent polish check is a string search
- **Evidence:** `if "backdrop-blur" not in code and "transition" not in code: raise`.
- **Fix:** replace with a structural design-token lint: generated frontend must import the
  token module and use ≥N primitives; then (reuse!) run a screenshot + pixel-diff or
  vision-model critique pass. Steal the pattern from neon_unified's `qa_browser.py`.
- **Acceptance:** a token-less generated page fails the gate; a compliant one passes.

### GAP-EM-5 (HIGH, no sandbox) — pytest runs as host subprocess
- **Evidence:** `backend/sandbox_executor.py` (50 lines).
- **Fix:** same Docker pattern as GAP-NU-3 (share the design; do not reinvent).
- **Acceptance:** escape-attempt test blocked.

### GAP-EM-6 (MED, dead UI) — workspace dead buttons
- **Evidence:** `frontend/src/app/workspace/page.tsx`: Settings/Refresh/Copy/GitHub buttons
  do nothing; no loading/error/empty states.
- **Fix:** wire or remove every button; implement the four states for the job view.
- **Acceptance:** Playwright smoke over workspace: every visible control either works or is
  gone; screenshot evidence saved.

---

## 5. PROJECT 4 — `D:\ideation_to_prototype`

This repo is the discipline benchmark (fail-closed, RELEASED selftest proven). Touch lightly.

### GAP-IP-1 (MED, isolation) — evidence_runner is host subprocess
- **Evidence:** `engine/evidence_runner.py`: allowlist + no-shell + blocks `-c/-e/--eval`
  (good) but still host-native.
- **Fix:** optional Docker backend behind config `exec.isolation: docker|host`, default docker
  when available, fail closed otherwise. Keep the allowlist in BOTH modes.
- **Acceptance:** existing 1,229-test suite stays green; new test proves docker mode runs the
  RELEASED selftest path.

### GAP-IP-2 (MED, no vision evidence) — BEHOLDER reads text only
- **Fix:** add an optional visual-evidence step: for tasks claiming UI output, capture a
  screenshot via headless browser and attach it to the evidence artifact; BEHOLDER prompt
  gains the image when the provider supports vision. Fail closed if a UI claim has no visual
  evidence.
- **Acceptance:** a UI-claiming task without screenshot evidence is rejected.

### GAP-IP-3 (LOW, honest metrics) — test-count inflation
- **Evidence:** 1,229 collected from 73 functions via parametrize; `reports/stability_runs.json`
  honestly records a 1,059-error run.
- **Fix:** document function-count vs collected-count in README; add a CI summary line
  printing both. No code change beyond reporting.

---

## 6. CROSS-PROJECT DEFINITION OF DONE

The sweep is done only when ALL hold:

1. Every GAP above is FIXED (test green) or BLOCKED (logged with exact evidence).
2. Each repo: clean-checkout test command documented in README passes with 0 errors.
3. Every gate touched fails CLOSED. Grep each repo for `approved.*True` / `return None`
   inside failure handlers of reviewer/QA code paths — any remaining fail-open must be
   explicitly flagged and justified in the worklog.
4. No secrets in any log, commit, or config (grep `sk-`, `Bearer `, `api_key.*=.*["'][A-Za-z0-9]`).
5. Live proof: neon_unified has ≥1 successful live generation; ases_v3_1 has ≥1 real
   (unmocked) e2e golden path. Everything else may be offline-verified.
6. Final report appended to each `REMEDIATION_WORKLOG.md`: table of GAP → status → test
   evidence → commit hash, plus an updated audit score per repo.

## 7. IF YOU RUN OUT OF CONTEXT

The worklogs are your non-volatile RAM. On resume: read the target repo's
`REMEDIATION_WORKLOG.md`, find the last logged GAP, continue at the next one. Never redo a
FIXED gap; never skip a BLOCKED one without re-testing it.

BEGIN WITH GAP-NU-1. VERIFY FIRST. FIX SECOND. LOG ALWAYS.
