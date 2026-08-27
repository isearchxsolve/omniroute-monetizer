"""Batch DRY-RUN classification of the 15 chrome-runtime VIDEO hosts.

Dry-run = find composer + land the prompt + STOP before submit. ZERO credits spent.
This tells us which video seats are capturable (DRY_RUN_OK) vs walled (WALL) vs
wrong-page (NO_COMPOSER) before we ever spend a clip.
"""
import sys, json, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")

from capture_video_job_cdp import capture_video, _sld

# (host, port, match-substring, optional url-to-open-if-no-match)
# Ports/matches chosen from the live-tab survey (scratch_track1_video_tabs.py).
PLAN = [
    ("akool.com",        9223, "akool.com/apps/image-to-video", ""),
    ("app.heygen.com",   9223, "app.heygen.com", ""),
    ("chat.qwen.ai",     9222, "chat.qwen.ai", ""),
    ("chatglm.cn",       9222, "chatglm.cn", ""),
    ("digen.ai",         9223, "digen.ai", ""),
    ("gemini.google.com",9222, "gemini.google.com", ""),
    ("grok.com",         9222, "grok.com", ""),
    ("labs.google",      9222, "labs.google/fx/tools/flow", ""),
    ("magichour.ai",     9223, "magichour.ai/create", ""),
    ("veoaifree.com",    9222, "veoaifree.com/veo-video-generator", ""),
    ("www.creen.ai",     9225, "creen.ai/create", ""),
    ("www.giz.ai",       9223, "giz.ai/assistant", ""),
    ("www.meta.ai",      9222, "meta.ai/prompt", ""),
    ("www.nemovideo.com",9222, "nemovideo.com/workspace", ""),
]

results = []
for host, port, match, url in PLAN:
    api = _sld(host).lower()
    t0 = time.monotonic()
    try:
        row = capture_video(port, match, host, api, "", 60.0, 25.0, False, True, url)
    except Exception as e:
        row = {"host": host, "status": "EXCEPTION", "note": f"{type(e).__name__}: {e}"}
    dt = time.monotonic() - t0
    status = row.get("status")
    note = (row.get("note") or "")[:70]
    wall = row.get("wall") or ""
    comp = row.get("composer") or {}
    print(f"\n[{host}] port={port} status={status} wall={wall} dt={dt:.0f}s")
    if comp:
        print(f"    composer: tag={comp.get('tag')} editable={comp.get('editable')} cands={comp.get('candidates')}")
    if note:
        print(f"    note: {note}")
    results.append({"host": host, "port": port, "status": status, "wall": wall,
                    "composer": bool(comp), "dt": round(dt, 1), "note": note})

print("\n\n===== SUMMARY =====")
ok = [r for r in results if r["status"] == "DRY_RUN_OK"]
wall = [r for r in results if r["status"] == "WALL"]
nocomp = [r for r in results if r["status"] == "NO_COMPOSER"]
other = [r for r in results if r["status"] not in ("DRY_RUN_OK", "WALL", "NO_COMPOSER")]
print(f"DRY_RUN_OK (capturable, composer found): {len(ok)}")
for r in ok: print(f"   {r['host']}")
print(f"WALL (paywall/captcha — Law 5 full stop): {len(wall)}")
for r in wall: print(f"   {r['host']}  wall={r['wall']}")
print(f"NO_COMPOSER (wrong page / needs --url): {len(nocomp)}")
for r in nocomp: print(f"   {r['host']}  {r['note']}")
print(f"OTHER: {len(other)}")
for r in other: print(f"   {r['host']}  status={r['status']}  {r['note']}")

with open(r"d:\omniroute-monetizer\state\track1_video_dryrun.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("\nsaved -> state/track1_video_dryrun.json")
