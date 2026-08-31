#!/usr/bin/env python3
"""Gate 3 (rigorous): real pure-Python video proof through :8190, seat-pool harness.

Submits ONE video job (model=video/<host>/auto) via POST /v1/chat/completions,
polls GET /v1/video/jobs/{id} until terminal, then downloads the returned
video.url with pure-python urllib and verifies it is real downloadable media
(Content-Type startswith video/ OR binary magic bytes, and bytes > 0). No
browser, no restart of any service.

OmniRoute-native video harness is a SEPARATE path that proxies through :20128;
while :20128 is unresponsive it cannot be proven here and is reported as
blocked (not declared dead).
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
SHIM = "http://127.0.0.1:8190"
OUT = ROOT / "state" / "gate3_video_proof.json"


def submit(host, prompt, job_key, timeout=60):
    body = json.dumps({
        "model": f"video/{host}/auto",
        "messages": [{"role": "user", "content": prompt}],
        "video": {"job_key": job_key},
    }).encode()
    req = urllib.request.Request(
        f"{SHIM}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                  "Authorization": "Bearer sk-omniroute"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def poll(job_id, timeout=300, interval=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = urllib.request.urlopen(
                f"{SHIM}/v1/video/jobs/{job_id}",
                timeout=20).read().decode()
            d = json.loads(r)
            st = d.get("video", {}).get("status")
            url = d.get("video", {}).get("url")
            if st in ("completed", "failed", "error"):
                return d
        except Exception as e:
            return {"error": f"poll: {type(e).__name__}: {str(e)[:160]}"}
        time.sleep(interval)
    return {"error": "poll_timeout"}


def verify_media(url, timeout=120):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer sk-omniroute"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type", "")
        data = resp.read()
    magic = data[:12]
    is_video = (ctype.lower().startswith("video/") or
                magic[:4] in (b"\x00\x00\x00\x18", b"\x00\x00\x00\x20") or  # ftyp mp4
                magic.startswith(b"RIFF") or                              # avi/webm-ish
                magic.startswith(b"\x1aE\xdf\xa3"))                       # webm
    return {"content_type": ctype, "bytes": len(data),
            "is_video": bool(is_video), "head_hex": magic[:8].hex()}


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "rtst.ai"
    prompt = sys.argv[2] if len(sys.argv) > 2 else \
        "Generate a short 3-second video clip of ocean waves at sunset."
    job_key = f"gate3_{host}_{int(time.time())}"
    rec = {"host": host, "job_key": job_key, "prompt": prompt,
           "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        receipt = submit(host, prompt, job_key)
        rec["submit_status"] = receipt.get("video", {}).get("status")
        rec["job_id"] = receipt.get("video", {}).get("jobId")
        print("SUBMIT:", rec["submit_status"], "job_id=", rec["job_id"])
        result = poll(rec["job_id"])
        rec["final_status"] = result.get("video", {}).get("status")
        rec["provider"] = result.get("video", {}).get("provider")
        rec["session"] = result.get("video", {}).get("session")
        url = result.get("video", {}).get("url")
        rec["video_url"] = url
        print("FINAL:", rec["final_status"], "provider=", rec.get("provider"),
              "url=", (url or "")[:80])
        if rec["final_status"] == "completed" and url:
            mv = verify_media(url)
            rec["media_verification"] = mv
            rec["media_ok"] = mv.get("is_video") and mv.get("bytes", 0) > 0
            print("MEDIA:", mv)
        else:
            rec["media_ok"] = False
    except urllib.error.HTTPError as e:
        rec["error"] = f"http_{e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    rec["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    OUT.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print("RESULT:", json.dumps({k: rec[k] for k in
                                  ("host", "final_status", "media_ok", "error")
                                  if k in rec}))


if __name__ == "__main__":
    main()
