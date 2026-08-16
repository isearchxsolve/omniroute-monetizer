"""Insert MASTER_WORKLOG entry #28 above the END marker. T11-safe: no secrets."""
import datetime

PATH = "MASTER_WORKLOG.md"
MARKER = "<!-- END OF SESSION LOG — new entries are appended above this marker -->"

stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

entry = f"""
### [{stamp}] #28 — AGENTS.md: Embedded Sandbox-First Fresh-State Engineering Strategy (anti-pattern #10)
**What:** User mandated a permanent first-principles engineering strategy: when a system is deeply screwed up, NEVER grind for hours inside the mess — reproduce in a fresh sandbox first.
**Actions taken:** Added anti-pattern #10 "SANDBOX-FIRST, FRESH-STATE ENGINEERING (No Grinding in the Mess)" to AGENTS.md, codifying the three stages:
1. **Fresh-state reproduction** — clean install of the exact same version in an isolated sandbox (separate dir/port/data-dir; OmniRoute supports `DATA_DIR` + `PORT` env vars). No repro fresh ⇒ accumulated state is the diagnosis.
2. **Incremental artifact replay** — copy existing artifacts/state onto the sandbox one by one, re-testing after each, until the bug reappears; the triggering artifact is the culprit.
3. **Backup, then touch production** — only after sandbox proof with real artifacts: complete byte-for-byte backup of live system, then apply fix, with one-command restore.
**Context:** This governs the approved 3-stage hotfix plan for blocker #3 (TTL-clamp hotfix): Stage 1 fresh sandbox install + hotfix + verify; Stage 2 replay real artifacts into sandbox + re-verify; Stage 3 backup live system + apply hotfix + NSSM bounce. Stage 1 install was paused pending this documentation.
**Files touched:** `AGENTS.md`, `scratch/write_entry28.py` (new).
**Verification:** AGENTS.md anti-patterns section now contains items 1–10.
**Status:** 🟡 Documentation complete; Stage 1 sandbox install awaiting user go-ahead to resume.

"""

lines = open(PATH, encoding="utf-8", errors="replace").read().splitlines(keepends=True)
out = []
inserted = False
for ln in lines:
    if MARKER in ln and not inserted:
        out.append(entry)
        inserted = True
    out.append(ln)
assert inserted, "marker not found"
open(PATH, "w", encoding="utf-8", newline="").write("".join(out))
print("entry #28 inserted above marker OK")
print("stamp:", stamp)
