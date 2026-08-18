"""Parse OmniRoute app.log for recent perplexity/t3 errors (full messages)."""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"

lines = open(LOG, encoding="utf-8", errors="replace").readlines()
print(f"total lines: {len(lines)}")

KEYS = ["PPLX-WEB", "T3-CHAT", "perplexity", "t3-chat", "t3.chat",
        "Missing Auth", "empty content", "ProxyEgress", "reset after",
        "401", "502", "invalid_api_key"]

out = []
for l in lines[-400:]:
    if any(k in l for k in KEYS):
        try:
            d = json.loads(l)
            ts = d.get("time") or d.get("timestamp") or ""
            tag = d.get("tag") or d.get("component") or d.get("module") or ""
            msg = d.get("msg") or d.get("message") or ""
            out.append(f"{ts[:19]} [{tag}] {msg[:400]}")
        except Exception:
            out.append(l.strip()[:400])

for o in out[-50:]:
    print(o)
