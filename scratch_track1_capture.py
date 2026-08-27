"""Track 1 driver: capture genuine chat blueprints for the no-blueprint / wrong-blueprint
chat seats, using capture_sessions_cdp.capture() directly against live signed-in tabs.

Targets (all free chat, no credits):
  claude.ai, copilot.microsoft.com, grok.com, v0.app  -> no recorded_exchange yet
  www.meta.ai                                          -> recorded exchange was a
                                                          searchConversations query (wrong
                                                          endpoint); re-capture the real send.

capture() only writes the seat file on SUCCESS (a POST carrying the sentinel was seen),
so a failed capture never clobbers an existing seat. Names are chosen so slug(name) lands
on the EXISTING seat filename, overwriting the empty/wrong blueprint with a good one.
"""
import sys, json, time
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import capture_sessions_cdp as cap

PORT = 9222
# (name -> slugs to existing seat stem, url-substring to find the live tab)
TARGETS = [
    ("Claude Ai",      "claude.ai"),
    ("Copilot Msft",   "copilot.microsoft.com"),
    ("Grok Com",       "grok.com"),
    ("V0 App",         "v0.app"),
    ("Meta Ai Web",    "www.meta.ai"),
]

tabs = cap.targets(PORT)
print(f"port {PORT}: {len(tabs)} page targets\n")

results = []
for name, frag in TARGETS:
    # prefer a tab whose url contains the fragment; for copilot prefer a /chats/ tab (a /pages/
    # tab may have no chat composer). Pick the first match.
    cands = [t for t in tabs if frag in t.get("url", "")]
    if frag == "copilot.microsoft.com":
        cands.sort(key=lambda t: 0 if "/chats/" in t.get("url", "") else 1)
    match = cands[0] if cands else None
    if not match:
        print(f"  --  {name:16s} NO TAB matching {frag!r}")
        results.append({"site": name, "status": "NO_TAB"})
        continue
    print(f"  ..  {name:16s} tab: {match.get('url','')[:70]}")
    row = cap.capture(match, name, "signed_in_probable", wait=30.0)
    st = row.get("status")
    tail = ""
    if st == "CAPTURED":
        tail = f"{row.get('endpointHost')}{row.get('endpointPath')} {row.get('bodyBytes')}B via {row.get('submitStrategy')}"
    elif row.get("wall"):
        tail = f"wall={row['wall']!r}"
    elif row.get("detail"):
        tail = str(row["detail"])[:80]
    elif row.get("note"):
        tail = str(row["note"])[:80]
    print(f"      -> {st}  {tail}")
    results.append(row)
    time.sleep(2.0)

print("\n===== SUMMARY =====")
for r in results:
    print(f"  {r.get('site'):16s} {r.get('status')}")
captured = [r["site"] for r in results if r.get("status") == "CAPTURED"]
print(f"\ncaptured: {captured or 'none'}")
