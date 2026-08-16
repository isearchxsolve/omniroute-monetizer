"""Insert MASTER_WORKLOG entry #27 above the END marker. T11-safe: no secrets."""
import datetime

PATH = "MASTER_WORKLOG.md"
MARKER = "<!-- END OF SESSION LOG — new entries are appended above this marker -->"

stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

entry = f"""
### [{stamp}] #27 — AGENTS.md: Embedded External-Source Triangulation Rule (anti-pattern #9)
**What:** User directed that the debugging methodology learned this session be permanently embedded in AGENTS.md so all future agents follow it unconditionally.
**Actions taken:** Added anti-pattern #9 "NO RUNTIME-ONLY GRINDING (External-Source Triangulation is MANDATORY)" to the Critical Anti-Patterns section of AGENTS.md, codifying:
1. Mandatory source order: own evidence → GitHub (issues/PRs/discussions/release notes) → Stack Overflow (via Stack Exchange API 2.3) → blind web search of the ACTUAL issue text (DuckDuckGo HTML / Bing; Google + direct SO are CAPTCHA-walled).
2. Rationale: individual developers publish fixes in blogs/forums/gists/Reddit before formal channels — well-grounded engineering reality.
3. "Merged" ≠ "released" — always verify `npm view <pkg> dist-tags --json`.
4. Read maintainers' reasoning before proposing local patches (invalidation-gap lesson from #8215).
5. Log every external source consulted, including negative results.
**Files touched:** `AGENTS.md`, `scratch/write_entry27.py` (new).
**Verification:** AGENTS.md anti-patterns section now contains items 1–9.
**Status:** ✅ Documentation complete.

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
print("entry #27 inserted above marker OK")
print("stamp:", stamp)
