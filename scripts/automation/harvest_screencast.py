"""Record the robot harvest Chrome via the CDP screencast protocol.

WHY THIS EXISTS (operator, 2026-08-22: "is there a way to do screen recording on your browser
... so you understand what's happening"): Playwright's built-in video recording does NOT work
for browsers connected with connect_over_cdp (attach mode) -- it only works when Playwright
launches the browser. Chrome's own DevTools screencast does work over the attach connection,
and it only sends frames for the VISIBLE tab, so the recording automatically follows whatever
the automation is doing.

What you get in state/harvest/rec/:
  latest.jpg        -- the most recent frame; open it any time to see "now"
  frame_*.jpg       -- the rolling buffer (last ~15 minutes)
  rec.mp4           -- assembled by ffmpeg when the recorder stops

The robot profile only; the operator's own Chrome is never touched (port 9333 is the robot
profile's, enforced by chrome_live_guard).

Usage:  python scripts/automation/harvest_screencast.py     (Ctrl+C to stop and build rec.mp4)
"""
from __future__ import annotations

import base64
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from provider_login_helper import ROBOT_CDP_PORT  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

REC = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "rec"
MAX_FRAMES = 1800        # ~15 min at ~2 fps before pruning
FRAME_MS = 500


def main() -> int:
    REC.mkdir(parents=True, exist_ok=True)
    for old in REC.glob("frame_*.jpg"):
        old.unlink(missing_ok=True)

    sessions: dict[int, object] = {}
    pending: list[tuple[object, dict]] = []
    seq = 0

    def hook(page) -> None:
        try:
            s = page.context.new_cdp_session(page)
            s.on("Page.screencastFrame", lambda ev, _s=s: pending.append((_s, ev)))
            s.send("Page.startScreencast", {
                "format": "jpeg", "quality": 70, "everyFrameMs": FRAME_MS,
                "maxWidth": 1280, "maxHeight": 800})
            sessions[id(page)] = s
        except Exception as exc:  # page may be mid-navigation; retried on the next scan
            print(f"  hook skipped ({type(exc).__name__})", flush=True)

    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}", timeout=10000)
        print(f"[*] recording the robot Chrome (port {ROBOT_CDP_PORT}) -> {REC}", flush=True)
        print("[*] Ctrl+C to stop; an rec.mp4 is assembled from the frames", flush=True)
        try:
            while True:
                for c in b.contexts:
                    for p in c.pages:
                        if id(p) not in sessions:
                            hook(p)
                for s, ev in pending:
                    global_seq_store[0] += 1
                    n = global_seq_store[0]
                    data = base64.b64decode(ev["data"])
                    (REC / f"frame_{n:05d}_{int(time.time() * 1000)}.jpg").write_bytes(data)
                    (REC / "latest.jpg").write_bytes(data)
                    try:
                        s.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
                    except Exception:
                        pass
                pending.clear()
                frames = sorted(REC.glob("frame_*.jpg"))
                for old in frames[:-MAX_FRAMES]:
                    old.unlink(missing_ok=True)
                time.sleep(0.4)
        except KeyboardInterrupt:
            print("\n[*] stopped; building rec.mp4 ...", flush=True)
        finally:
            for s in sessions.values():
                try:
                    s.send("Page.stopScreencast")
                except Exception:
                    pass

    # Assemble: rename to gap-free sequence, then ffmpeg at the frame cadence.
    frames = sorted(REC.glob("frame_*.jpg"))
    if not frames:
        print("[-] no frames captured -- nothing to assemble")
        return 1
    seqdir = REC / "seq"
    seqdir.mkdir(exist_ok=True)
    for i, f in enumerate(frames):
        f.replace(seqdir / f"s{i:05d}.jpg")
    out = REC / "rec.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(int(1000 / FRAME_MS)),
         "-i", str(seqdir / "s%05d.jpg"), "-pix_fmt", "yuv420p", str(out)],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        print(f"[-] ffmpeg failed: {r.stderr[-300:]}")
        return 2
    print(f"[+] {len(frames)} frames -> {out}")
    return 0


global_seq_store = [0]

if __name__ == "__main__":
    raise SystemExit(main())
