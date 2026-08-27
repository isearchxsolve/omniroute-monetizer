"""Transport audit: for every dispatchable seat, which runtime transport does
the pool dispatch to? Classify CHROME-FREE (stateless HTTP / API cred) vs
STILL-CHROME-AT-RUNTIME. Zero cost - dispatch logic only, no provider calls."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from session_pool import SessionPool, _client_for

pool = SessionPool()
chrome_free = []
chrome_runtime = []
for s in pool.sessions:
    if not s.dispatchable:
        continue
    try:
        raw = json.loads(s.path.read_text(encoding="utf-8-sig"))
    except Exception:
        continue
    cls = _client_for(s.host, raw)
    name = cls.__name__ if cls else "None"
    entry = (s.host, s.modality, name)
    if name in ("ChromeReplayClient", "ChromeVideoClient"):
        chrome_runtime.append(entry)
    else:
        chrome_free.append(entry)

print(f"CHROME-FREE at runtime ({len(chrome_free)}):")
for h, m, n in sorted(chrome_free):
    print(f"   {m:5} {h:26} {n}")
print(f"\nSTILL CHROME AT RUNTIME ({len(chrome_runtime)}):")
for h, m, n in sorted(chrome_runtime):
    print(f"   {m:5} {h:26} {n}")
print(f"\nTOTAL dispatchable: {len(chrome_free) + len(chrome_runtime)} | "
      f"chrome-free: {len(chrome_free)} | chrome-runtime: {len(chrome_runtime)}")
