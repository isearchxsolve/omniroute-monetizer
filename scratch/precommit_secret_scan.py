"""T11 pre-commit secret scan over untracked files (excludes vendored scratch/MonkeyCode)."""
import re, subprocess, os

os.chdir(r"d:\omniroute-monetizer")
out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
files = []
for line in out.splitlines():
    if line.startswith("??"):
        p = line[3:].strip().strip('"')
        if p.startswith("scratch/MonkeyCode"):
            continue
        if os.path.isdir(p):
            for root, _, fs in os.walk(p):
                for f in fs:
                    files.append(os.path.join(root, f))
        else:
            files.append(p)

PAT = re.compile(
    r"sk-[a-zA-Z0-9_-]{16,}|nvapi-[a-zA-Z0-9_-]{16,}|ghp_[a-zA-Z0-9]{20,}|"
    r"github_pat_[a-zA-Z0-9_]{20,}|AIza[0-9A-Za-z_-]{20,}|xox[baprs]-[a-zA-Z0-9-]{10,}|"
    r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"
)
hits = 0
for p in files:
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, 1):
                m = PAT.search(line)
                if m:
                    hits += 1
                    print(f"{p}:{i}: {line.strip()[:130]}")
    except Exception as e:
        print(f"{p}: READ ERR {e}")
print(f"\nscanned {len(files)} files, {hits} secret-pattern hits")
