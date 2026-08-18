"""Parse app.log for latest PPLX-WEB entries (raw upstream detail)."""
import json
import os

LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"

lines = []
with open(LOG, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            j = json.loads(line)
        except Exception:
            continue
        msg = str(j.get("message") or j.get("msg") or "")
        tag = str(j.get("tag") or j.get("label") or j.get("context") or "")
        if "PPLX" in msg.upper() or "PPLX" in tag.upper() or "perplexity" in msg.lower():
            ts = j.get("timestamp") or j.get("time") or ""
            lines.append(f"{ts} [{tag}] {msg[:400]}")

for l in lines[-40:]:
    print(l)
print(f"\ntotal PPLX entries: {len(lines)}")
