"""Insert MASTER_WORKLOG entry #30 above the END marker. T11-safe: no secrets."""
import datetime

PATH = "MASTER_WORKLOG.md"
MARKER = "<!-- END OF SESSION LOG — new entries are appended above this marker -->"

stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

entry = f"""
### [{stamp}] #30 — AGENTS.md: Embedded Engineering Philosophy (Discipline Over Intelligence) at Document Top
**What:** User (23-year system architect) delivered the foundational philosophy behind all prior methodology entries: software engineering is NOT about intelligence or skills — it is about DISCIPLINE: maintaining principles backed by evidence. The method: (1) start with a SHALLOW investigation, (2) then slowly go deeper only after the shallow sweep fails, (3) incremental addition of artifacts — replay the messy original state ONE BY ONE onto a fresh install, shallow-investigating after each addition; the artifact that re-triggers the bug is the culprit. This shallow → incremental → evidence method is the fact basis of all software engineering.
**Actions taken:** Added a new top-level "ENGINEERING PHILOSOPHY (The Fact Basis of All Software Engineering)" section immediately after the Mission in AGENTS.md, so it governs every rule below it (documentation rule, architecture, anti-patterns #1–#10, certification matrix).
**Files touched:** `AGENTS.md`, `scratch/write_entry30.py` (new).
**Verification:** AGENTS.md now opens with Mission → Engineering Philosophy → Mandatory Documentation Rule.
**Status:** ✅ Philosophy embedded. Stage 1 sandbox install still awaiting resume.

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
print("entry #30 inserted above marker OK")
print("stamp:", stamp)
