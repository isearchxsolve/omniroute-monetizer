"""Find where /api/restart and /api/shutdown are actually handled server-side.

Search for the HTTP request dispatcher and any 'restart'/'shutdown' handling
in the server bootstrap / open-sse.
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
    for path in walk():
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        rel = os.path.relpath(path, ROOT)
        for i, line in enumerate(lines):
            low = line.lower()
            # look for restart/shutdown as an action handled in request flow
            if ("restart" in low or "shutdown" in low) and (
                "url" in low or "pathname" in low or "path ===" in low or
                "startswith" in low or "case " in low or "handle" in low or
                "process.exit" in low or "graceful" in low
            ):
                # skip the CLI command definitions and comments-only
                if rel.startswith("bin\\cli\\api-commands"):
                    continue
                print(f"{rel}:{i+1}: {line.strip()[:150]}")

if __name__ == "__main__":
    main()
