"""Locate the /api/shutdown handler and how the server registers API routes.

Read-only investigation. Prints file:line for every relevant hit.
"""
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
    shutdown_hits = []
    route_reg_hits = []
    for path in walk():
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        rel = os.path.relpath(path, ROOT)
        for i, line in enumerate(lines):
            low = line.lower()
            if "api/shutdown" in low:
                shutdown_hits.append((rel, i + 1, line.strip()[:120]))
            # route registration patterns
            if any(p in line for p in ('app.post(', 'app.get(', 'router.post(', 'router.get(',
                                       'fastify.post(', 'fastify.get(', '.route(', 'registerRoute')):
                if "shutdown" in low or "/api/" in line:
                    route_reg_hits.append((rel, i + 1, line.strip()[:120]))

    print("=== api/shutdown references ===")
    for h in shutdown_hits[:30]:
        print(f"{h[0]}:{h[1]}: {h[2]}")
    print(f"\n(total {len(shutdown_hits)})")

    print("\n=== route registrations mentioning shutdown or /api/ ===")
    for h in route_reg_hits[:40]:
        print(f"{h[0]}:{h[1]}: {h[2]}")
    print(f"\n(total {len(route_reg_hits)})")

if __name__ == "__main__":
    main()
