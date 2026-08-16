"""Find server-side handlers for /api/restart and /api/shutdown, and how they auth."""
import os

ROOT = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute"
SKIP_DIRS = {"node_modules", ".git", ".build", "dist"}

def walk():
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
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
            if ('"/api/restart"' in line or "'/api/restart'" in line or
                '"/api/shutdown"' in line or "'/api/shutdown'" in line or
                'api/restart' in line and ('case' in line or '===' in line or 'path' in line.lower())):
                print(f"{rel}:{i+1}: {line.strip()[:140]}")

if __name__ == "__main__":
    main()
