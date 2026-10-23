"""target_gate.py - TARGET-LIST QUALITY GATE (architecture fix 1, 2026-10-12)."""
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
LOGIN_MARKERS = re.compile(
    r"sign in|sign-in|log in|log-in|login|continue with|single sign ?on|sso|"
    r"create account|sign up|get started|auth", re.I)
BOT_WALL = re.compile(r"just a moment|attention required|verify you are human|"
                      r"cf-browser-verification|challenge-platform", re.I)


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.read(300000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read(100000).decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, url, body
    except Exception as e:
        return -1, url, str(e)


def judge(provider_host, status, final_url, body):
    if BOT_WALL.search(body[:5000]):
        return "BOT_WALL", "challenge page"
    if status == -1:
        return "FETCH_ERR", body[:120]
    try:
        fhost = (urlparse(final_url).hostname or "").lower().replace("www.", "")
    except Exception:
        fhost = ""
    phost = (provider_host or "").lower().replace("www.", "")
    if fhost and phost and phost not in fhost and fhost not in phost:
        return "REDIRECT", "lands on " + fhost
    if status in (401, 403, 404, 410, 500, 502, 503):
        return "HTTP_%d" % status, "status %d" % status
    if LOGIN_MARKERS.search(body[:20000]):
        return "OK", "login surface present"
    return "NO_LOGIN", "no login markers in body"


def main():
    with io.open(r"D:\anonym\war-log\graduation_targets.json", "r",
                 encoding="utf-8") as f:
        targets = json.load(f)
    out = (r"D:\anonym\war-log\target-gate-%s.jsonl"
           % time.strftime("%Y%m%d-%H%M%S"))
    print("GATING %d targets" % len(targets))
    counts = {}
    with io.open(out, "w", encoding="utf-8") as w:
        for t in targets:
            pid = t.get("id")
            host = t.get("host") or ""
            login = t.get("login_url") or ""
            status, final, body = fetch(login)
            verdict, why = judge(host, status, final, body)
            counts[verdict] = counts.get(verdict, 0) + 1
            row = {"provider_id": pid, "name": t.get("name"), "host": host,
                   "login_url": login, "status": status, "final_url": final,
                   "verdict": verdict, "why": why}
            w.write(json.dumps(row, ensure_ascii=True) + "\n")
            print("  %-24s %-10s %s" % (pid, verdict, str(why)[:70]))
    print("TALLY: " + json.dumps(counts))
    print("GATE REPORT: " + out)


if __name__ == "__main__":
    main()
