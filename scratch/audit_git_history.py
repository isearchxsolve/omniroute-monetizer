"""
G9: Audit git history for secrets (never print raw values).

Scans `git log -p --all` for live-key patterns and writes a REDACTED
audit report to state/git_secret_audit.json. Only key-id prefixes
(sha256[:12]) are reported, never the raw secret.

Run: python scratch/audit_git_history.py
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "state" / "git_secret_audit.json"

PATTERNS = [
    ("openrouter", r"sk-or-v1-[A-Za-z0-9]{20,}"),
    ("anthropic", r"sk-ant-[A-Za-z0-9_-]{20,}"),
    ("github", r"gh[pousr]_[A-Za-z0-9]{20,}"),
    ("nvidia", r"nvapi-[A-Za-z0-9_-]{20,}"),
    ("generic_sk", r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}"),
    ("enc_key", r"STORAGE_ENCRYPTION_KEY[=:]\s*[0-9a-fA-F]{32,}"),
    ("password", r"password[\"']?\s*[:=]\s*[\"'][^\"'\s]{8,}"),
    ("apikey_assign", r"(?i)(api[_-]?key|token|secret)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-]{20,}[\"']"),
    ("bearer", r"bearer [A-Za-z0-9_.\-]{20,}",),
]


def scan_history() -> list[dict]:
    proc = subprocess.run(
        ["git", "log", "-p", "--all", "--format=%H %cI"],
        cwd=REPO, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git log failed: {proc.stderr[:500]}")
    lines = proc.stdout.splitlines()

    hits: list[dict] = []
    current_commit = None
    current_file = None

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("commit "):
            current_commit = line.split()[1]
        elif line.startswith("Date:"):
            continue
        elif re.match(r"^[0-9a-f]{40} ", line) and current_commit is None:
            current_commit = line.split()[0]
        elif line.startswith("+++ b/") or line.startswith("diff --git"):
            m = re.search(r"b/(.+)$", line)
            current_file = m.group(1) if m else current_file
        elif current_commit:
            for name, pattern in PATTERNS:
                for m in re.finditer(pattern, line):
                    # only consider added lines (+) to reduce noise
                    if not line.startswith("+") and not line.startswith("+++"):
                        continue
                    if re.match(r"^[0-9a-f]{40} ", line) or line.startswith("+++"):
                        continue
                    raw_secret = m.group(0).lstrip("+")
                    if len(raw_secret) < 8:
                        continue
                    digest = hashlib.sha256(raw_secret.encode()).hexdigest()[:12]
                    hits.append({
                        "pattern": name,
                        "key_id": digest,
                        "commit": current_commit,
                        "file": current_file or "?",
                        "line": line[:120],
                    })
    return hits


def dedupe(hits: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for h in hits:
        k = (h["pattern"], h["key_id"], h["commit"])
        if k in seen:
            continue
        seen.add(k)
        out.append(h)
    return out


def main() -> int:
    hits = scan_history()
    hits = dedupe(hits)
    report = {
        "scanned_commits": subprocess.run(
            ["git", "rev-list", "--all", "--count"], cwd=REPO,
            capture_output=True, text=True).stdout.strip(),
        "hits_total_raw": len(scan_history()),
        "hits_unique": hits,
        "verdict": "CLEAN" if not hits else "REVIEW REQUIRED",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Audit complete: {report['hits_total_raw']} raw matches, "
          f"{len(hits)} unique (pattern+key-prefix+commit).")
    print(f"Verdict: {report['verdict']}")
    print(f"Report: {OUT}")
    return 0 if not hits else 2


if __name__ == "__main__":
    raise SystemExit(main())
