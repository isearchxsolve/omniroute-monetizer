"""Insert MASTER_WORKLOG entry #29 above the END marker. T11-safe: no secrets."""
import datetime

PATH = "MASTER_WORKLOG.md"
MARKER = "<!-- END OF SESSION LOG — new entries are appended above this marker -->"

stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

entry = f"""
### [{stamp}] #29 — AGENTS.md: Promoted Shallow-Investigation First Principle to Anti-Patterns Preamble
**What:** User articulated the meta-principle behind entries #26–#28: ~99% of problems are hidden in plain sight as complete obvious things that deep-diving misses, because a deep dive zooms IN while the answer requires zooming OUT. An experienced engineer handed a broken system does a SHALLOW investigation first (minutes, not hours) — is it running? right version? right port? right config? obvious flag/env var? recent change? known issue? — because that eliminates the 99% fast. Only after the shallow sweep proves the cause is NOT among the obvious 99% do you commit to a deep dive. Never open with a 10-hour deep dive.
**Actions taken:** Promoted this to a blockquote FIRST PRINCIPLE at the very top of the "Critical Anti-Patterns & Past Failures" section in AGENTS.md (line 119), so it governs ALL ten anti-patterns rather than being buried inside item #10. Verified no duplication remains in #10.
**Files touched:** `AGENTS.md`, `scratch/write_entry29.py` (new).
**Verification:** grep confirms single FIRST PRINCIPLE occurrence at preamble; item #10 intact with its 3 stages.
**Status:** ✅ Documentation complete. Stage 1 sandbox install still awaiting resume.

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
print("entry #29 inserted above marker OK")
print("stamp:", stamp)
