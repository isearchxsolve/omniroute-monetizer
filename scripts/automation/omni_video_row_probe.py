"""omni_video_row_probe.py - probe chat-lane video_candidate rows through the native contract.

One row per invocation (--model), spend-gated by OMNI_VIDEO_CONFIRM_SPEND like every other
video seat. Verdicts land in state/omni_video_routes.json (the wiring ledger the shim
publishes). Terminal verdicts: PROVEN (mp4 bytes), WALL (named), FAILED (classified).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

ROUTES = pathlib.Path(__file__).resolve().parents[2] / "state" / "omni_video_routes.json"
PROOF_PROMPT = ("A single orange leaf drifts slowly across a clear blue pond, soft "
                "morning light, cinematic wide shot")


def looks_like_mp4(b: bytes) -> bool:
    return len(b or b"") > 16 and b[:4] == b"\x00\x00\x00 ftyp"[0:4] or (len(b or b"") > 16 and b[4:8] == b"ftyp")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, help="catalog route id, e.g. vertex/veo-3.1-generate-preview")
    ap.add_argument("--prompt", default=PROOF_PROMPT)
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    doc = json.loads(ROUTES.read_text(encoding="utf-8"))
    row = next((r for r in doc["routes"] if r["model"] == args.model), None)
    if row is None:
        print(f"model {args.model!r} not in the wiring ledger")
        return 1

    from omniroute_video_client import OmnirouteVideoClient, ChatError
    from veo_session_replay import SessionExpired

    seat = pathlib.Path(__file__).resolve().parents[2] / "state" / "secrets" / "session_omniroute_native.json"
    client = OmnirouteVideoClient(seat, timeout=args.timeout)
    t0 = time.time()
    verdict, url, err, http = "FAILED", None, None, None
    try:
        r = client.chat([{"role": "user", "content": args.prompt}], model=args.model)
        url = str(r.get("text") or r.get("file") or "")
        verdict = "PROVEN" if url else "FAILED"
        err = None if url else "no url in result"
    except SessionExpired as e:
        verdict, err = "WALL", f"AUTH: {e}"[:300]
    except ChatError as e:
        kind = str(getattr(e, "kind", "") or (getattr(e, "args", [""])[0] if e.args else ""))
        err = str(e)[:300]
        low = err.lower()
        # "Invalid video model" = the route id is outside OmniRoute's native video-adapter
        # registry (#1629 measured all 70 chat-lane rows there): a BUILD TARGET (cause (a)),
        # not an upstream verdict. Distinguish it from a real provider wall/refusal.
        if kind in ("wall", "auth"):
            verdict = "WALL"
        elif "invalid video model" in low:
            verdict = "BUILD_TARGET"
        else:
            verdict = "FAILED"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:300]

    row.update(status=verdict, directProof=(verdict if verdict in ("PROVEN", "WALL") else None),
               consumerProof=None,
               error=err, resultUrl=url, probedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    tmp = ROUTES.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    tmp.replace(ROUTES)
    print(f"{verdict} {args.model} ({int(time.time() - t0)}s) err={str(err)[:120] if err else '-'}")
    return 0 if verdict == "PROVEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
