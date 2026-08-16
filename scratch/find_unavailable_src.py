"""Fast search for 'accounts unavailable' in OmniRoute dist code."""
import os

ROOT = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute"
hits = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    # skip node_modules inside
    dirnames[:] = [d for d in dirnames if d != "node_modules"]
    for fn in filenames:
        if fn.endswith((".js", ".mjs", ".cjs")):
            p = os.path.join(dirpath, fn)
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue
            if "accounts unavailable" in content:
                # find line numbers
                for i, line in enumerate(content.splitlines(), 1):
                    if "accounts unavailable" in line:
                        hits.append((p, i, line.strip()[:200]))

print(f"hits: {len(hits)}")
for p, i, line in hits:
    print(f"{p}:{i}")
    print(f"  {line}")
