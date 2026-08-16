"""Find the [HealthCheck] token-validation scheduler in the dist bundle."""
import os
import re

CHUNKS = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks"

files = [os.path.join(CHUNKS, f) for f in os.listdir(CHUNKS) if f.endswith(".js") and not f.startswith("node_modules")]
print(f"scanning {len(files)} app chunks")

# 1. Find files containing the HealthCheck log strings
for f in files:
    try:
        s = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    if "[HealthCheck]" in s and ("setInterval" in s or "scheduleNext" in s or "setTimeout" in s):
        name = f.split("\\")[-1]
        # find interval constants near HealthCheck
        idx = s.find("[HealthCheck]")
        # search whole file for interval-like constants
        intervals = set(re.findall(r"(?:interval|INTERVAL|every|delay)[^;]{0,60}?(\d{4,6}|[0-9]+e[0-9])", s))
        print(f"\n=== {name} (len={len(s)}) ===")
        print(f"interval-ish constants: {sorted(intervals)[:20]}")
        # find the scheduler entry: look for 'startTokenHealth' or similar
        for pat in ["startTokenHealth", "tokenHealthCheck", "initTokenHealth", "runTokenHealth", "scheduleTokenHealth", "healthCheckInterval"]:
            for m in re.finditer(pat, s):
                print(f"  [{pat}] @{m.start()}: ...{s[max(0,m.start()-100):m.start()+250]}...")
                break
