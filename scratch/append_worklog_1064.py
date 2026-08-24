"""Insert MASTER_WORKLOG #1064 directly after #1063, whose thread it continues.

The file is not consistently ordered (newest entries live at the head, but the Flow thread was
appended near the tail), so this anchors on the NEXT entry heading after #1063 rather than on a line
number, and refuses to write if that anchor is not found exactly once.
"""
import pathlib
import sys

P = pathlib.Path("MASTER_WORKLOG.md")
ANCHOR = "### [2026-08-24 00:00] #1060 — EmergentSH OmniRoute fallback health verification"
ENTRY = pathlib.Path("scratch/entry_1064.md").read_text(encoding="utf-8")

txt = P.read_text(encoding="utf-8")
if "#1064" in txt:
    sys.exit("refusing: #1064 already present")
if txt.count(ANCHOR) != 1:
    sys.exit(f"refusing: anchor found {txt.count(ANCHOR)} times, expected 1")

P.write_text(txt.replace(ANCHOR, ENTRY.rstrip() + "\n\n" + ANCHOR), encoding="utf-8")
print(f"inserted #1064 ({len(ENTRY)} chars) before the {ANCHOR[:34]}... entry")
