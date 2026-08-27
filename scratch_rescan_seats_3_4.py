# RESCAN: third and fourth seat Chrome profiles (:9224, :9225).
# Same method as scratch_rescan_seats_1_2.py: full tab enumeration, synchronous
# liveness eval (no awaitPromise), auth classification for video tabs.
# Read-only: never drives, never clicks. Writes state/rescan_seats_3_4.json.
import json
import time
import pathlib
import urllib.request
import websocket

PORTS = (9224, 9225)

VIDEO_TOKENS = (
    "flow", "veo", "video", "labs.google", "veoaifree", "digen", "rtst", "kie",
    "runway", "pika", "kling", "hailuo", "luma", "genmo", "haiper", "invideo",
    "synthesia", "heygen", "akool", "creen", "minimax", "pixverse", "viggle",
    "seedance", "firefly", "adobe", "nemo", "vidu", "mochi", "dreamina",
    "higgsfield", "freepik", "rendernet", "pollo", "vmake", "magichour", "giz",
)

SIGNED_IN_MARKERS = ("sign out", "log out", "logout", "signout", "my account",
                     "my profile", "dashboard", "credits", "upgrade", "subscription")
LOGIN_WALL_MARKERS = ("sign in", "log in", "login", "continue with google",
                      "create account", "sign up", "signup", "password", "email address")

LIVE_JS = "JSON.stringify({t: document.title, u: location.href, rs: document.readyState})"

AUTH_JS = r"""
(() => {
  const body = document.body;
  const txt = body ? (body.textContent || '') : '';
  const lower = txt.toLowerCase();
  const avatars = document.querySelectorAll(
    'img[alt*="avatar" i], img[class*="avatar" i], [class*="avatar" i], ' +
    '[data-testid*="avatar" i], [class*="user-menu" i], [class*="profile-pic" i]'
  ).length;
  const genBtns = [...document.querySelectorAll('button, [role="button"], a')]
    .filter(e => /generate|create|make|render/i.test(e.textContent || ''))
    .length;
  return JSON.stringify({len: txt.length, head: lower.slice(0, 4000),
                         avatars: avatars, genBtns: genBtns});
})()
"""

def cdp(ws, mid, method, params=None, timeout=25):
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        ws.settimeout(max(1.0, deadline - time.time()))
        try:
            msg = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            continue
        if msg.get("id") == mid:
            return msg
    return {"error": {"message": f"TIMEOUT after {timeout}s waiting for {method}"}}

def classify(d):
    head = d.get("head", "")
    signed = [m for m in SIGNED_IN_MARKERS if m in head]
    wall = [m for m in LOGIN_WALL_MARKERS if m in head]
    avatars = d.get("avatars", 0)
    gen = d.get("genBtns", 0)
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

results = []
for port in PORTS:
    try:
        raw = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=6).read()
        tabs = json.loads(raw)
    except Exception as e:
        print(f":{port} NO_BROWSER {type(e).__name__}")
        continue
    pages = [t for t in tabs if t.get("type") == "page"]
    vids = [t for t in pages if is_video(t)]
    print(f"\n===== :{port}  {len(pages)} page tabs total, {len(vids)} video-capable =====")
    for t in pages:
        url = t.get("url", "")
        host = url.split("/")[2] if "://" in url else "?"
        ws_url = t.get("webSocketDebuggerUrl") or ""
        rec = {"port": port, "host": host, "url": url, "video": is_video(t)}
        if not ws_url:
            rec["verdict"] = "NO_WS_URL"
            print(f"  [NO_WS_URL ] {host:24s}")
            results.append(rec)
            continue
        try:
            ws = websocket.create_connection(ws_url, timeout=15, max_size=8 * 1024 * 1024)
        except Exception as e:
            rec["verdict"] = "WS_CONNECT_FAIL"
            rec["err"] = str(e)[:120]
            print(f"  [WS_CONNECT] {host:24s} {type(e).__name__}: {str(e)[:70]}")
            results.append(rec)
            continue
        try:
            cdp(ws, 1, "Runtime.enable", timeout=12)
            r1 = cdp(ws, 2, "Runtime.evaluate",
                     {"expression": LIVE_JS, "returnByValue": True}, timeout=25)
            if "error" in r1:
                rec["verdict"] = "EVAL_ERROR"
                rec["err"] = r1["error"].get("message", "")[:120]
                print(f"  [EVAL_ERR  ] {host:24s} {rec['err']}")
                results.append(rec)
                continue
            res = r1.get("result", {})
            if res.get("exceptionDetails"):
                d = res["exceptionDetails"]
                rec["verdict"] = "JS_THROW"
                rec["err"] = str(d.get("exception", {}).get("description") or d.get("text"))[:120]
                print(f"  [JS_THROW  ] {host:24s} {rec['err']}")
                results.append(rec)
                continue
            val = res.get("result", {}).get("value")
            if not val:
                rec["verdict"] = "NO_VALUE"
                print(f"  [NO_VALUE  ] {host:24s}")
                results.append(rec)
                continue
            d = json.loads(val)
            rec["verdict"] = "LIVE"
            rec["readyState"] = d.get("rs")
            rec["title"] = d.get("t")
            line = f"  [LIVE      ] {host:24s} rs={d.get('rs'):11s} title={str(d.get('t'))[:40]}"
            if rec["video"]:
                r2 = cdp(ws, 3, "Runtime.evaluate",
                         {"expression": AUTH_JS, "returnByValue": True}, timeout=25)
                res2 = r2.get("result", {})
                val2 = res2.get("result", {}).get("value") if "error" not in r2 else None
                if val2:
                    ad = json.loads(val2)
                    verdict, why = classify(ad)
                    rec["auth"] = verdict
                    rec["auth_why"] = why
                    line += f"\n               auth={verdict:11s} {why}"
                else:
                    rec["auth"] = "AUTH_PROBE_FAIL"
                    line += "\n               auth=AUTH_PROBE_FAIL"
            print(line)
            results.append(rec)
        finally:
            try:
                ws.close()
            except Exception:
                pass
        time.sleep(0.3)

from collections import Counter
print(f"\n===== VERDICTS across {len(results)} tabs =====")
for k, v in Counter(r["verdict"] for r in results).most_common():
    print(f"  {k:14s} {v}")
live_video = [r for r in results if r["verdict"] == "LIVE" and r.get("video")]
print(f"\n===== LIVE VIDEO TABS ({len(live_video)}) =====")
for r in live_video:
    print(f"  :{r['port']}  {r['host']:24s} auth={r.get('auth','?'):12s} {r.get('auth_why','')[:60]}")
    print(f"        {r['url'][:90]}")
wireable = sorted({(r["port"], r["host"]) for r in live_video
                   if r.get("auth") in ("SIGNED_IN", "PROBABLY_IN")})
print(f"\n===== WIREABLE (live + signed-in) video hosts: {len(wireable)} =====")
for port, host in wireable:
    print(f"  :{port}  {host}")

out = pathlib.Path("state/rescan_seats_3_4.json")
out.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"\nwrote {out}")
