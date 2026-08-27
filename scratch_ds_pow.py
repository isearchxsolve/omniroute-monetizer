"""Inspect DeepSeek PoW: the x-ds-pow-response header, and hunt for the challenge source."""
import json, pathlib, re, sys

p = pathlib.Path("state/secrets/session_deepseek_chat.json")
d = json.loads(p.read_text(encoding="utf-8"))
ex = d.get("recorded_exchange") or {}
hdrs = ex.get("request_headers") or {}

print("=== DeepSeek PoW-related headers ===")
for k, v in sorted(hdrs.items()):
    lk = k.lower()
    if any(s in lk for s in ("pow", "ds", "hif", "auth", "token", "x-")):
        vv = v if len(v) < 120 else v[:80] + f"...({len(v)} chars)"
        print(f"  {k}: {vv}")

print("\n=== full x-ds-pow-response ===")
print(repr(hdrs.get("x-ds-pow-response", "<missing>")))

print("\n=== other top-level keys in session file ===")
print(sorted(d.keys()))

# Look for any pow challenge captured elsewhere in the file
blob = json.dumps(d)
print("\n=== 'pow' occurrences in file ===")
for m in re.finditer(r'pow', blob, re.I):
    s = max(0, m.start()-60); e = min(len(blob), m.end()+80)
    print("  ...", blob[s:e].replace("\n"," "), "...")
