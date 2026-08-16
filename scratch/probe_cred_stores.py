"""Inspect structure (keys only, no values) of local credential stores."""
import json
import os

out = {}

def structure(obj, depth=0, max_depth=3):
    if depth > max_depth:
        return "..."
    if isinstance(obj, dict):
        return {k: structure(v, depth + 1, max_depth) for k, v in obj.items()}
    if isinstance(obj, list):
        return [structure(obj[0], depth + 1, max_depth)] if obj else []
    if isinstance(obj, str):
        return f"<str len={len(obj)}>"
    return f"<{type(obj).__name__}>"

paths = {
    "codex_auth": os.path.expanduser("~/.codex/auth.json"),
    "qoder_user": os.path.expanduser("~/.qoder/.auth/user"),
    "codex_config": os.path.expanduser("~/.codex/config.toml"),
}

for name, p in paths.items():
    if not os.path.exists(p):
        out[name] = "MISSING"
        continue
    try:
        raw = open(p, encoding="utf-8", errors="replace").read()
        try:
            data = json.loads(raw)
            out[name] = structure(data)
        except Exception:
            # non-JSON: report line key patterns only
            keys = []
            for line in raw.splitlines()[:40]:
                line = line.strip()
                if "=" in line or ":" in line:
                    k = line.split("=")[0].split(":")[0].strip().strip('"').strip("'")
                    if k and len(k) < 40 and not k.startswith("#"):
                        keys.append(k)
            out[name] = {"format": "non-json", "keys": keys[:30], "bytes": len(raw)}
    except Exception as e:
        out[name] = f"ERROR {type(e).__name__}: {e}"

open(r"d:\omniroute-monetizer\scratch\cred_store_structure.json", "w", encoding="utf-8").write(json.dumps(out, indent=2))
print("done")
