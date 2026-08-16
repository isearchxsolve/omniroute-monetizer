"""Find where /api/restart and /api/shutdown are served in open-sse (the HTTP layer)."""
import os

ROOT = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\open-sse"

def walk():
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in {"node_modules", ".git"}]
        for f in fn:
            if f.endswith((".ts", ".mjs", ".js")):
                yield os.path.join(dp, f)

def main():
    for path in walk():
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        rel = os.path.relpath(path, ROOT)
        for i, line in enumerate(lines):
            if "restart" in line.lower() or "shutdown" in line.lower():
                if any(k in line for k in ('"', "'", "case", "===", "path", "url", "route", "post", "get", "handler")):
                    print(f"{rel}:{i+1}: {line.strip()[:150]}")

if __name__ == "__main__":
    main()
