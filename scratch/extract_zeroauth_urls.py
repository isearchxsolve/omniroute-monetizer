#!/usr/bin/env python3
"""Extract baseUrl/modelsUrl/format for zero-auth candidates from OmniRoute dist."""
import os
import re
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"

# cloud zero-auth candidates (exclude local-server ones)
CANDS = ["pollinations", "duckduckgo-free", "duckduckgo-web", "edgetts", "gtts",
         "qwen", "theoldllm", "mixedbread", "hackclub", "g4f-gemini", "g4f-groq",
         "g4f-nvidia", "uncloseai", "veoaifree-web", "felo-web", "auggie",
         "chipotle", "mimocode", "coqui", "ovhcloud"]

# find the big provider-config chunk among SSR chunks (not mcp server.js)
best_file = None
best_count = 0
for root, dirs, files in os.walk(DIST):
    for fn in files:
        if not fn.endswith(".js"):
            continue
        fp = os.path.join(root, fn)
        if "mcp-server" in fp:
            continue
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                t = f.read()
        except Exception:
            continue
        c = t.count('authType:')
        if c > best_count:
            best_count = c
            best_file = fp

print(f"config chunk: {best_file} ({best_count} authType)")
text = open(best_file, encoding="utf-8", errors="ignore").read()

out = {}
for cand in CANDS:
    # find the provider block: "cand":{id:"cand", ... } up to next top-level provider
    pat = re.compile(re.escape(f'"{cand}"') + r':\{id:"' + re.escape(cand) + r'"')
    m = pat.search(text)
    if not m:
        # try unquoted key
        pat = re.compile(re.escape(cand) + r':\{id:"' + re.escape(cand) + r'"')
        m = pat.search(text)
    if not m:
        out[cand] = {"found": False}
        continue
    start = m.start()
    # grab ~1200 chars of the block
    block = text[start:start + 1200]
    base = re.search(r'baseUrl:"([^"]+)"', block)
    models = re.search(r'modelsUrl:"([^"]+)"', block)
    fmt = re.search(r'format:"([^"]+)"', block)
    auth = re.search(r'authType:"([^"]+)"', block)
    out[cand] = {
        "found": True,
        "baseUrl": base.group(1) if base else None,
        "modelsUrl": models.group(1) if models else None,
        "format": fmt.group(1) if fmt else None,
        "authType": auth.group(1) if auth else None,
    }

print(json.dumps(out, indent=1))
with open(os.path.join(os.path.dirname(__file__), "..", "state", "zeroauth_candidates.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print("[+] saved state/zeroauth_candidates.json")
