#!/usr/bin/env python3
"""preflight_planner.py -- replay oioi's film-planner workload against :20130 before the real run.

Why this exists
---------------
The premium film run died at planner-contract validation twice, and each death cost a full run's
setup to discover. The planner's workload is completely reproducible from outside oioi: it sends N
sequential strict-JSON requests, one six-shot scene each, and every reply must satisfy a contract
that is stated exactly in FILM_PIPELINE_DELIVERY_REPORT.md. So the surprise can be moved forward:
run the same 60 requests here, grade every reply against the same contract, and find out whether the
supply can sustain it BEFORE a run that has 16 irreplaceable clips riding on it.

This spends no credits and no clips. The chat pool is free captured supply, and the video side is
only READ (capacity + a 404 probe), never submitted to.

    python preflight_planner.py                  # 60 scenes = the real 360-shot workload
    python preflight_planner.py --scenes 12      # fast read
    python preflight_planner.py --chat-only
"""
from __future__ import annotations
import argparse
import json
import time
import urllib.error
import urllib.request

CHAT = "http://127.0.0.1:20130"
VIDEO = "http://127.0.0.1:8189"
# oioi's planner client gives up here. Anything slower is a failure even if it would have been valid.
CONSUMER_TIMEOUT_S = 45.0
MOVES = ("static", "pan_left", "pan_right", "dolly_in", "dolly_out", "crane_up")

BEATS = [
    "the tide station wakes to an unscheduled signal",
    "Mara reads the pattern and does not tell the crew",
    "the relay tower is found already powered",
    "a second signal answers from the seabed",
    "the crew splits over whether to reply",
    "Mara transmits alone at night",
]


def scene_prompt(n: int, total: int) -> str:
    beat = BEATS[n % len(BEATS)]
    return (
        "Return strict JSON only. No prose, no markdown, no commentary, nothing else.\n\n"
        f'Scene {n + 1} of {total} of a 30-minute film "Signal Tide".\n'
        f"Beat: {beat}\n\n"
        "Output a JSON array of EXACTLY 6 objects, one per shot. Each object must have exactly "
        "these keys:\n"
        '  "prompt"      - a distinct one-sentence video-generation prompt for that shot\n'
        '  "stillPrompt" - byte-identical in all 6 objects: one description of the scene location '
        "and lighting\n"
        '  "stillSeed"   - the same integer in all 6 objects\n'
        f'  "cameraMove"  - one of {list(MOVES)}; all 6 must be different\n\n'
        "Return the JSON array and nothing else."
    )


def ask(prompt: str, model: str) -> tuple:
    """POST /v1/messages the way oioi does. Returns (text, status, seat, ms)."""
    body = json.dumps({"model": model, "max_tokens": 2000,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(f"{CHAT}/v1/messages", data=body,
                                headers={"content-type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=CONSUMER_TIMEOUT_S) as r:
            doc = json.loads(r.read())
        ms = round((time.perf_counter() - t0) * 1000)
        parts = doc.get("content") or []
        text = "".join(p.get("text") or "" for p in parts if isinstance(p, dict))
        return text, r.status, doc.get("model") or "?", ms
    except urllib.error.HTTPError as e:
        ms = round((time.perf_counter() - t0) * 1000)
        try:
            err = json.loads(e.read()).get("error") or {}
        except Exception:
            err = {}
        return "", e.code, (err.get("type") or "http_error"), ms
    except Exception as e:
        ms = round((time.perf_counter() - t0) * 1000)
        return "", 0, f"{type(e).__name__}", ms


def grade(text: str) -> tuple:
    """Grade one reply against the planner contract. Returns (ok, reason)."""
    s = (text or "").strip()
    if not s:
        return False, "empty"
    if s[0] not in "[{":
        return False, f"not a JSON body (starts {s[:12]!r})"
    try:
        doc = json.loads(s)
    except Exception as e:
        return False, f"unparseable ({type(e).__name__})"
    rows = doc if isinstance(doc, list) else next(
        (v for v in doc.values() if isinstance(v, list)), None) if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        return False, "no array of shots"
    if len(rows) != 6:
        return False, f"array length {len(rows)}, contract requires exactly 6"
    if not all(isinstance(r, dict) for r in rows):
        return False, "shots are not objects"
    if any(not str(r.get("prompt") or "").strip() for r in rows):
        return False, "a shot has an empty prompt"
    stills = {str(r.get("stillPrompt") or "") for r in rows}
    if len(stills) != 1 or not stills.pop().strip():
        return False, f"stillPrompt not shared byte-identically ({len(stills) + 1} distinct)"
    moves = [str(r.get("cameraMove") or "").strip().lower() for r in rows]
    if len(set(moves)) != 6:
        return False, f"cameraMove not 6 distinct values ({len(set(moves))} distinct)"
    return True, ""


def video_preflight() -> None:
    print("video router (:8189) -- READ ONLY, no job submitted")
    try:
        with urllib.request.urlopen(f"{VIDEO}/v1/video/capacity", timeout=30) as r:
            cap = json.loads(r.read())
        seats = cap.get("seats") or []
        print(f"  ok    capacity           {cap.get('totalClipsAvailable')} clip(s) across "
              f"{len(seats)} seat(s)")
        for s in seats[:8]:
            print(f"          seat {str(s.get('provider') or s.get('host'))[:22]:22s} "
                  f"clipsRemaining={s.get('clipsRemaining')}")
    except Exception as e:
        print(f"  FAIL  capacity           {type(e).__name__}: {e}")
        return
    # A job the router has never seen must 404 cleanly rather than 500 -- the consumer polls unknown
    # ids after a restart, and a crash there would look like a lost film.
    try:
        urllib.request.urlopen(f"{VIDEO}/v1/video/jobs/preflight-nonexistent-id", timeout=20).read()
        print("  WARN  unknown job id      returned 200; expected 404")
    except urllib.error.HTTPError as e:
        verdict = "ok  " if e.code == 404 else "WARN"
        print(f"  {verdict}  unknown job id      {e.code} (404 is correct)")
    except Exception as e:
        print(f"  FAIL  unknown job id      {type(e).__name__}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenes", type=int, default=60, help="60 = the real 360-shot workload")
    ap.add_argument("--model", default="pool/auto")
    ap.add_argument("--chat-only", action="store_true")
    a = ap.parse_args()

    if not a.chat_only:
        video_preflight()
        print()

    print(f"chat planner (:20130) -- {a.scenes} sequential strict-JSON scene requests, "
          f"{CONSUMER_TIMEOUT_S:.0f}s consumer timeout")
    ok = 0
    fails: dict[str, int] = {}
    seats: dict[str, int] = {}
    worst = 0
    slow = 0
    t0 = time.time()
    for n in range(a.scenes):
        text, status, seat, ms = ask(scene_prompt(n, a.scenes), a.model)
        worst = max(worst, ms)
        if ms > CONSUMER_TIMEOUT_S * 1000:
            slow += 1
        if status != 200:
            reason = f"HTTP {status} ({seat})"
            good = False
        else:
            good, reason = grade(text)
            seats[seat] = seats.get(seat, 0) + 1
        if good:
            ok += 1
            print(f"  scene {n + 1:2d}/{a.scenes}  ok    {ms:6d}ms  {seat[:28]}")
        else:
            fails[reason] = fails.get(reason, 0) + 1
            print(f"  scene {n + 1:2d}/{a.scenes}  FAIL  {ms:6d}ms  {reason[:70]}")

    el = time.time() - t0
    print(f"\n  {ok}/{a.scenes} scenes satisfied the planner contract "
          f"({100.0 * ok / max(1, a.scenes):.0f}%)")
    print(f"  elapsed {el:.0f}s  |  slowest single request {worst}ms  |  "
          f"over consumer timeout: {slow}")
    if seats:
        print("  seats that answered: " + ", ".join(f"{k[:22]}={v}" for k, v in
                                                    sorted(seats.items(), key=lambda x: -x[1])))
    if fails:
        print("  failure modes:")
        for r, c in sorted(fails.items(), key=lambda x: -x[1]):
            print(f"    {c:3d}x  {r}")
    print()
    if ok == a.scenes:
        print("  VERDICT: the planner path will not die on supply. Launch the premium run.")
        return 0
    print(f"  VERDICT: {a.scenes - ok} scene(s) would have failed. A strict planner aborts the whole "
          f"run on the first one, so this must reach 100% before the 16-clip pass.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
