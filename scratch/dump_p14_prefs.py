"""Dump Profile 14 pinned tabs / startup / session settings to find stray tab source."""
import json, os

PREFS = r"d:\omniroute-chrome-profile\Profile 14\Preferences"
OUT = r"d:\omniroute-monetizer\scratch\p14_prefs_dump.txt"

with open(PREFS, "r", encoding="utf-8-sig", errors="replace") as f:
    j = json.load(f)

lines = []
def show(path, obj):
    lines.append(f"=== {path} ===")
    lines.append(json.dumps(obj, indent=2, ensure_ascii=False)[:3000])
    lines.append("")

# pinned tabs
pt = j.get("pinned_tabs")
show("pinned_tabs", pt if pt is not None else "(absent)")

# session settings
sess = j.get("session", {})
show("session", {k: sess.get(k) for k in
                 ("restore_on_startup", "startup_urls", "exit_type", "exited_cleanly")})

# homepage / startup
show("homepage", j.get("homepage"))
show("homepage_is_newtabpage", j.get("homepage_is_newtabpage"))

# search for any 0.0.0.14 anywhere in the whole prefs
raw = json.dumps(j)
if "0.0.0.14" in raw:
    idx = raw.find("0.0.0.14")
    lines.append("=== RAW 0.0.0.14 context ===")
    lines.append(raw[max(0, idx-200):idx+200])
else:
    lines.append("=== 0.0.0.14 NOT present in Profile 14 Preferences ===")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("done")
