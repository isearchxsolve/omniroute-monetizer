"""Resolve MASTER_WORKLOG.md rebase conflict: keep BOTH blocks, renumber ours.
Remote (HEAD) pushed #53-#59 from a parallel session; our unpushed #53-#61
become #60-#68. Internal cross-refs in our block are updated.
"""
import re

P = r"d:\omniroute-monetizer\MASTER_WORKLOG.md"
lines = open(P, encoding="utf-8").read().splitlines(keepends=True)

start = sep = end = None
for i, l in enumerate(lines):
    if l.startswith("<<<<<<<"):
        start = i
    elif l.startswith("=======") and start is not None and sep is None:
        sep = i
    elif l.startswith(">>>>>>>") and sep is not None:
        end = i
        break
assert start is not None and sep is not None and end is not None, "conflict markers not found"

head_block = lines[start + 1:sep]          # remote #53-#59
ours_block = lines[sep + 1:end]            # our #53-#61

# renumber our entry headers #53..#61 -> #60..#68
ours_text = "".join(ours_block)
mapping = {53: 60, 54: 61, 55: 62, 56: 63, 57: 64, 58: 65, 59: 66, 60: 67, 61: 68}
for old, new in sorted(mapping.items(), reverse=True):
    ours_text = re.sub(rf"^(### \[\d{{4}}-\d{{2}}-\d{{2}} [0-9:]+\]) #{old}( —)",
                       rf"\1 #{new}\2", ours_text, flags=re.M)

# fix internal cross-references in our block
ours_text = ours_text.replace("Follow-up to #56 (openrouter per-model lockout)",
                              "Follow-up to #63 (openrouter per-model lockout)")
ours_text = ours_text.replace("removed in #57 (`claude-sonnet-5`",
                              "removed in #64 (`claude-sonnet-5`")
ours_text = ours_text.replace("(Entries #59/#60 targeted Zed",
                              "(Entries #66/#67 targeted Zed")

# add a merge note at the top of our renumbered block
note = ("\n> **Merge note (rebase):** Entries #60–#68 below were written by a parallel local session "
        "and originally numbered #53–#61; renumbered to continue after the remote-pushed #53–#59 "
        "(commit c2663e1). No content was altered.\n\n")

resolved = lines[:start] + head_block + [note] + [ours_text] + lines[end + 1:]
open(P, "w", encoding="utf-8", newline="").write("".join(resolved))

# verify: no markers, headers sequential
txt = "".join(resolved)
assert "<<<<<<<" not in txt and ">>>>>>>" not in txt and "\n=======\n" not in txt
headers = re.findall(r"^### \[\d{4}-\d{2}-\d{2} [0-9:]+\] #(\d+) —", txt, flags=re.M)
nums = [int(h) for h in headers]
print("entries:", len(nums), "first:", nums[0], "last:", nums[-1])
dups = [n for n in set(nums) if nums.count(n) > 1]
print("duplicate numbers:", dups if dups else "none")
print("sequence check:", "OK" if nums == sorted(nums) else "OUT OF ORDER: " + str(nums[-15:]))
