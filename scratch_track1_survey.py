import json, sys, glob, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SECRETS = pathlib.Path(r"d:\omniroute-monetizer\state\secrets")
# the 27 chrome-runtime hosts from the audit
chrome_hosts = ["akool.com","app.heygen.com","chat.cerebras.ai","chat.deepseek.com",
    "chatglm.cn","claude.ai","copilot.microsoft.com","digen.ai","gemini.google.com",
    "grok.com","labs.google","magichour.ai","v0.app","veoaifree.com","www.creen.ai",
    "www.giz.ai","www.meta.ai","www.nemovideo.com","chat.qwen.ai"]

rows = []
for f in sorted(glob.glob(str(SECRETS / "session_*.json"))):
    p = pathlib.Path(f)
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception as e:
        continue
    host = d.get("host", "")
    if not any(h in host for h in chrome_hosts):
        continue
    mod = d.get("modality", "?")
    runtime = d.get("runtime", "")
    has_rx = bool(d.get("recorded_exchange"))
    has_job = bool(d.get("recorded_job"))
    has_chrome = bool(d.get("chrome"))
    has_api = bool(d.get("api"))
    cookie_len = len(d.get("cookie_header", ""))
    rx_url = (d.get("recorded_exchange") or {}).get("url", "")
    rows.append((host, mod, runtime, has_rx, has_job, has_chrome, has_api, cookie_len, rx_url, p.name))

print(f"{'host':28} {'mod':6} {'rt':7} {'rx':3} {'job':3} {'chr':3} {'api':3} {'ck':5} file")
for r in sorted(rows):
    host, mod, runtime, has_rx, has_job, has_chrome, has_api, cookie_len, rx_url, name = r
    print(f"{host:28} {mod:6} {runtime:7} {str(has_rx):3} {str(has_job):3} {str(has_chrome):3} {str(has_api):3} {cookie_len:<5} {name}")
print("\ntotal:", len(rows))
# which chat seats have a recorded_exchange (candidates for stateless test)
print("\nCHAT seats with recorded_exchange (stateless-replay candidates):")
for r in rows:
    if r[1] == "chat" and r[3]:
        print("  ", r[0], "->", r[8][:70])
