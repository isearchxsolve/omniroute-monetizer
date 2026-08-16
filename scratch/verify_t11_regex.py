"""Verify the tightened T11 password regex matches nothing real in scanned docs."""
import re

pat = r"password[\"']?\s*[:=]\s*[\"'][^\"'\s]{8,}"
files = ["MASTER_WORKLOG.md", "COMPREHENSIVE_AUDIT_AND_FIXES.md", "HANDOFF_PROMPT_PHASE2.md"]
found_any = False
for f in files:
    try:
        content = open(f, encoding="utf-8", errors="ignore").read()
    except FileNotFoundError:
        print(f"{f}: not present")
        continue
    matches = re.findall(pat, content, re.IGNORECASE)
    real = [m for m in matches if "***" not in m and "REDACTED" not in m]
    if real:
        found_any = True
        print(f"{f}: MATCHES -> {real[:5]}")
    else:
        print(f"{f}: clean ({len(matches)} raw, all redacted/none)")
print("\nRESULT:", "STILL MATCHING — investigate" if found_any else "CLEAN — regex fix valid")

# Sanity: the regex must STILL catch real quoted password leaks
print("\n--- sanity: real leaks must still be caught ---")
should_match = [
    'password = "SuperSecret123"',
    "password: 'hunter2hunter2'",
    'password="FakeSecret999"',
]
should_not_match = [
    "password = os.environ.get(",
    'password": password}',
    "INITIAL_PASSWORD bootstrap var",
    "password from .env, never printed",
]
ok = True
for t in should_match:
    hit = bool(re.search(pat, t, re.IGNORECASE))
    print(f"  {t!r} -> {'MATCH (good)' if hit else 'NO MATCH (BAD!)'}")
    ok = ok and hit
for t in should_not_match:
    hit = bool(re.search(pat, t, re.IGNORECASE))
    print(f"  {t!r} -> {'MATCH (BAD!)' if hit else 'no match (good)'}")
    ok = ok and not hit
print("\nSANITY:", "PASS" if ok else "FAIL")
