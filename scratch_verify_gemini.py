"""Verify Gemini's keyword unlock is a real answer, not 58 inside an id/timestamp."""
import json, pathlib, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "scripts/automation")
from universal_replay import UniversalSessionClient

p = pathlib.Path("state/secrets/session_gemini_google_com.json")
if not p.exists():
    # find it
    for f in pathlib.Path("state/secrets").glob("session_*gemini*.json"):
        p = f
        break
print("file:", p.name)
client = UniversalSessionClient(str(p))
try:
    res = client.chat([{"role": "user", "content": "Reply with only the number: 41 + 17"}])
    print("extracted text:", repr(res.get("text"))[:200])
    raw = res.get("raw", "")
except Exception as e:
    raw = getattr(e, "raw", "") or ""
    print("EXC:", type(e).__name__, str(e)[:150])

print("raw len:", len(raw))
# Show every occurrence of 58 with context, and whether it stands alone (non-digit neighbours)
for m in re.finditer(r"58", raw):
    s, e = max(0, m.start()-40), min(len(raw), m.end()+40)
    ctx = raw[s:e].replace("\n", " ")
    before = raw[m.start()-1] if m.start() > 0 else "^"
    after = raw[m.end()] if m.end() < len(raw) else "$"
    standalone = not before.isdigit() and not after.isdigit()
    print(f"  [{'ALONE' if standalone else 'EMBEDDED'}] ...{ctx}...")
