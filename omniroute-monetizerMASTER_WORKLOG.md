
### [2026-09-09 03:12] #1681 — Permanent bounded recovery fix for the stuck :8190 owner

**Root cause confirmed:** The registered `OmniRoute Session Pool Shim (keepalive)` task has `MultipleInstances=IgnoreNew` and a 72-hour execution limit. Its exact owner process entered `PRIMARY-UNHEALTHY cleanup-before-fallback` and stopped making progress. Because the owner called `psutil.process_iter()` / `psutil.wait_procs()` synchronously, a half-dead Windows process query could hold the task indefinitely; every one-minute recovery invocation was then ignored. The port had no listener.

**Code change:** `scripts/automation/session_pool_shim_task.py` now runs every exact-process discovery/cleanup and orphan-prune operation inside a daemon worker with a strict four-second deadline. A timeout raises `OwnerOperationTimeout`, writes `FAILED bounded cleanup: ...` to the diagnostic log, returns from the owner, and allows the next scheduled tick to retry. The owner never launches a new shim after an unknown cleanup result, preserving single-owner safety. All four cleanup call sites (pre-start, primary success, failed-primary fallback, and fallback success) use the bounded wrapper.

**Verification:** Existing owner tests plus a new hanging-operation regression test passed: `python -m pytest -q tests/test_session_pool_shim_task.py` => `3 passed in 0.45s`. Code was committed as `0bc6774 fix-bounded-shim-owner-recovery`, with `git diff --cached --check` clean.

**Restart authorization and next step:** The operator explicitly authorized a restart if required. The currently running exact task-owner pair must be stopped only after a final command-line identity check, then the registered scheduled task should be triggered so the new code performs the recovery. No broad process kill, port takeover, or manual parallel shim launch is permitted.

**What is not claimed yet:** The fix is committed and tested, but the live :8190 listener has not yet been re-established in this entry. Consumer catalog, 25/23 balance, and 50-model publication remain unverified until the scheduled owner returns `RECOVERED` and the endpoint answers.