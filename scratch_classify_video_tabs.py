# Classify every video-capable tab across all automation Chrome ports as
# SIGNED_IN / LOGIN_WALL / UNCLEAR, read-only. This is the shallow-investigation
# step of the Chrome Gap Doctrine: enumerate live supply and its auth state before
# deciding what to wire. Uses textContent (NOT innerText -- innerText forces reflow
# and HANGS on WebGL pages like Google Flow). Never drives, never clicks.
import json
import sys
import pathlib
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
from cdp import list_targets

PORTS = (9222, 9223, 9224, 9225)

VIDEO_TOKENS = (
    "flow", "veo", "video", "labs.google", "veoaifree", "digen", "rtst", "kie",
    "runway", "pika", "kling", "hailuo", "luma", "genmo", "haiper", "invideo",
    "synthesia", "heygen", "akool", "creen", "minimax", "pixverse", "viggle",
    "seedance", "firefly", "adobe", "nemo", "vidu", "mochi", "dreamina",
    "higgsfield", "freepik", "rendernet", "pollo", "vmake", "magichour", "giz",
)

# Generic auth markers (from video_key_harvester / provider_login_helper).
SIGNED_IN_MARKERS = ("sign out", "log out", "logout", "signout", "my account",
                     "my profile", "dashboard", "credits", "upgrade", "subscription")
LOGIN_WALL_MARKERS = ("sign in", "log in", "login", "continue with google",
                      "create account", "sign up", "signup", "password", "email address")

# Grab a bounded slice of textContent + a few structural auth signals in one eval.
# textContent avoids the reflow hang. Bounded to 4000 chars to keep it cheap.
PROBE_JS = r"""
(() => {
  const body = document.body;
  const txt = body ? (body.textContent || '') : '';
  const lower = txt.toLowerCase();
  // avatar / account-chip presence is a strong signed-in signal
  const avatars = document.querySelectorAll(
    'img[alt*="avatar" i], img[class*="avatar" i], [class*="avatar" i], ' +
    '[data-testid*="avatar" i], [class*="user-menu" i], [class*="profile-pic" i]'
  ).length;
  // a visible generate/create button is the video-surface signal
  const genBtns = [...document.querySelectorAll('button, [role="button"], a')]
    .filter(e => /generate|create|make|render/i.test(e.textContent || ''))
    .length;
  return JSON.stringify({
    url: location.href,
    title: document.title,
    len: txt.length,
    head: lower.slice(0, 4000),
    avatars: avatars,
    genBtns: genBtns,
  });
})()
"""

def classify(d):
    head = d.get("head", "")
    signed = [m for m in SIGNED_IN_MARKERS if m in head]
    wall = [m for m in LOGIN_WALL_MARKERS if m in head]
    avatars = d.get("avatars", 0)
    gen = d.get("genBtns", 0)
    # Strong signed-in: avatar present, or signed markers with no wall markers.
    if avatars >= 1 and not wall:
        return "SIGNED_IN", f"avatars={avatars} gen={gen} signed={signed[:3]}"
    if signed and not wall:
        return "SIGNED_IN", f"signed={signed[:3]} gen={gen}"
    if wall and not signed and avatars == 0:
        return "LOGIN_WALL", f"wall={wall[:3]}"
    if gen >= 1 and not wall:
        return "PROBABLY_IN", f"gen={gen} signed={signed[:2]}"
    return "UNCLEAR", f"signed={signed[:2]} wall={wall[:2]} avatars={avatars} gen={gen}"

def is_video(t):
    blob = (t.get("url", "") + " " + t.get("title", "")).lower()
    return any(tok in blob for tok in VIDEO_TOKENS)

summary = []
for port in PORTS:
    try:
        tabs = list_targets(port)
    except Exception as e:
        print(f":{port}  NO_BROWSER ({type(e).__name__})")
        continue
    pages = [t for t in tabs if t.get("type") == "page" and is_video(t)]
    print(f"\n===== :{port}  {len(pages)} video tabs =====")
    for t in pages:
        url = t.get("url", "")
        host = url.split("/")[2] if "://" in url else url
        # Connect directly to this specific target's websocket (Page() picks the
        # first match on the port, which is not necessarily THIS tab).
        try:
            import websocket
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=20,
                                             max_size=64 * 1024 * 1024)
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": PROBE_JS, "returnByValue": True,
                                           "awaitPromise": True, "userGesture": True}}))
            import time as _t
            deadline = _t.time() + 20
            raw = None
            while _t.time() < deadline:
                ws.settimeout(max(1.0, deadline - _t.time()))
                try:
                    msg = json.loads(ws.recv())
                except Exception:
                    continue
                if msg.get("id") == 1:
                    raw = msg
                    break
            ws.close()
            if not raw or "result" not in raw:
                print(f"  [NOJS ] {host:22s} {url[:70]}")
                continue
            val = raw["result"].get("result", {}).get("value")
            if not val:
                print(f"  [NOVAL] {host:22s} {url[:70]}")
                continue
            d = json.loads(val)
            verdict, why = classify(d)
            print(f"  [{verdict:11s}] {host:22s} {why}")
            print(f"              {url[:80]}")
            summary.append({"port": port, "host": host, "url": url,
                            "verdict": verdict, "why": why})
        except Exception as e:
            print(f"  [ERR  ] {host:22s} {type(e).__name__}: {str(e)[:60]}  {url[:60]}")

print(f"\n===== SUMMARY =====")
from collections import Counter
c = Counter(s["verdict"] for s in summary)
for k, v in c.most_common():
    print(f"  {k:12s} {v}")
print(f"\nSIGNED_IN / PROBABLY_IN video hosts (wireable supply):")
seen = set()
for s in summary:
    if s["verdict"] in ("SIGNED_IN", "PROBABLY_IN") and s["host"] not in seen:
        seen.add(s["host"])
        print(f"  :{s['port']}  {s['host']:22s} {s['why']}")

out = pathlib.Path("state/video_tab_auth_audit.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
