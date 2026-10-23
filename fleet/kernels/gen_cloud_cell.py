import json
import os

def make_cell(source_lines):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source_lines}

def make_notebook(cells):
    return {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10.0"},
            "accelerator": "none"
        },
        "cells": cells
    }

MAIN_CODE = r'''
# OMNIROUTE KAGGLE CLOUD CELL v1.0 -- THE INFINITE CLOUD RUNWAY (CPU)
# Polls relay doors for orders: BUILD_SAAS / RENDER_VIDEO. CPU-only, 0 GPU quota.
import os, sys, json, time, subprocess, urllib.request, socket, threading

socket.setdefaulttimeout(25)  # hard ceiling on any socket op (urlopen timeout is per-op only)

try:
    import curl_cffi
    from curl_cffi import requests as c_requests
except ImportError:
    print("[INIT] Installing curl_cffi...", flush=True)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "curl_cffi"])
    import curl_cffi
    from curl_cffi import requests as c_requests

DOORS = [
    "https://omniroute-relay.omniroute-fleet-kd.workers.dev",  # PERMANENT Worker door
    "https://measurements-orlando-infections-meal.trycloudflare.com",
    "https://retrain-schnapps-upbeat.ngrok-free.dev",
]

# Self-discovery: pull the live Kaggle relay URL from GitHub (laptop-free path)
def discover_relay_door():
    try:
        req = urllib.request.Request(
            "https://raw.githubusercontent.com/isearchxsolve/omniroute-monetizer/master/relay-url.txt",
            headers={"User-Agent": "omniroute-kaggle-worker"})
        url = urllib.request.urlopen(req, timeout=10).read().decode().strip()
        if url.startswith("https://") and url not in DOORS:
            DOORS.insert(0, url)
            print(f"[DISCOVERY] Relay door found on GitHub: {url}", flush=True)
    except Exception as e:
        print(f"[DISCOVERY] No relay URL on GitHub yet ({e})", flush=True)

discover_relay_door()
TOK = "GOLD24"
HDRS = {"User-Agent": "omniroute-kaggle-worker", "ngrok-skip-browser-warning": "1"}
POLL_INTERVAL = 15

print("=" * 70, flush=True)
print("OMNIROUTE AUTONOMOUS CLOUD RUNWAY ACTIVE ON KAGGLE CPU", flush=True)
print(f"Target Door: {DOORS[0]}", flush=True)
print("Zero GPU quota consumed. Pure BoringSSL wire replay.", flush=True)
print("=" * 70, flush=True)

ACTIVE_DOOR = DOORS[0]
LAST_RESOLVE = 0

def resolve_door(force=False):
    global ACTIVE_DOOR, LAST_RESOLVE
    now = time.time()
    if not force and ACTIVE_DOOR and (now - LAST_RESOLVE < 300):
        return ACTIVE_DOOR
    for d in DOORS:
        try:
            req = urllib.request.Request(f"{d}/health?token={TOK}", headers=HDRS)
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode())
            if data.get("ok"):
                ACTIVE_DOOR = d
                LAST_RESOLVE = now
                return d
        except Exception:
            pass
    return ACTIVE_DOOR

def door_check():
    d = resolve_door(force=True)
    try:
        req = urllib.request.Request(f"{d}/health?token={TOK}", headers=HDRS)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        return data.get("ok", False)
    except Exception as e:
        print(f"[DOOR-WARN] Health probe: {e}", flush=True)
        return False

def report_home(body, text):
    d = resolve_door()
    try:
        payload = json.dumps({"body": body, "text": text}).encode()
        req = urllib.request.Request(f"{d}/say?token={TOK}", data=payload, headers=HDRS)
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        print(f"[REPORT-ERR] Failed reporting: {e}", flush=True)

def fetch_orders():
    d = resolve_door()
    out = []
    for body_name in ("OMNIROUTE", "WEBEXEC"):
        try:
            req = urllib.request.Request(f"{d}/say?body={body_name}&token={TOK}&limit=10", headers=HDRS)
            resp = urllib.request.urlopen(req, timeout=20)
            data = json.loads(resp.read().decode())
            got = data.get("orders", [])
            out.extend(got)
        except Exception as e:
            resolve_door(force=True)
    return out

def handle_webexec_task(order_text):
    # WEB_EXECUTE:{json} — the agent-internet executor.
    # Executes real HTTP against the live web from this Kaggle body.
    import base64 as _b64
    import urllib.error as _ue

    try:
        spec = json.loads(order_text.split("WEB_EXECUTE:", 1)[1])
    except Exception as e:
        report_home("WEBEXEC_ERR", f"PARSE-FAIL {type(e).__name__}: {e}")
        print(f"[WEBEXEC-ERR] bad spec: {e}", flush=True)
        return

    jid = spec.get("job_id", "unknown")
    url = spec.get("url", "")
    method = (spec.get("method") or "GET").upper()
    headers = spec.get("headers") or {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    body = spec.get("body")
    timeout_s = min(int(spec.get("timeout_s") or 20), 60)
    max_bytes = min(int(spec.get("max_bytes") or 100000), 100000)

    print(f"[WEBEXEC] {method} {url[:80]} job={jid}", flush=True)
    report_home("WXDBG", f"EXEC-START jid={jid} {method} {url[:50]}")
    t0 = time.time()

    # Door for result posting (Worker first)
    door = resolve_door()

    def post_result(payload):
        payload.update(_lease_token=spec.get("_lease_token"), _queue_generation=spec.get("_queue_generation"))
        try:
            req = urllib.request.Request(
                f"{door}/v1/tools/web.result?token={TOK}",
                data=json.dumps(payload).encode(),
                headers={"content-type": "application/json",
                          "User-Agent": "omniroute-kaggle-worker"})
            resp = urllib.request.urlopen(req, timeout=20)
            body = resp.read()[:200].decode("utf-8", "replace")
            print(f"[WEBEXEC] result posted for {payload.get('job_id')}", flush=True)
        except Exception as e:
            report_home("WEBEXEC_ERR", f"RESULT-POST-FAIL {payload.get('job_id')} err={type(e).__name__}: {str(e)[:100]}")
            print(f"[WEBEXEC] result post failed: {e}", flush=True)

    if spec.get("capture_recipe"):
        payload = replay_public_capture(spec["capture_recipe"], timeout_s)
        payload.update(job_id=jid, executed_by="kaggle:cloud-cell", duration_ms=int((time.time()-t0)*1000))
        post_result(payload)
        return

    if not url:
        post_result({"job_id": jid, "status": "failed", "error": "no url", "executed_by": "kaggle"})
        return

    data = None
    if body is not None and method != "GET":
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()

    # subprocess-curl executor: subprocess timeout KILLS hung targets (threads/urlopen cannot)
    cmd = ["curl", "-s", "--max-time", str(timeout_s), "-X", method, url,
           "--max-filesize", str(max_bytes), "--write-out", "\n%{http_code}\t%{content_type}"]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    if data is not None:
        cmd += ["--data-binary", data.decode("utf-8", "replace")]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s + 5)
        output = proc.stdout or b""
        raw, separator, metadata = output.rpartition(b"\n")
        status_code = 0
        content_type = ""
        try:
            code, content_type = metadata.decode("utf-8", "replace").split("\t", 1)
            status_code = int(code)
        except (ValueError, TypeError):
            raw = output
        success = proc.returncode == 0 and separator and 200 <= status_code < 300
        payload = {
            "job_id": jid,
            "status": "done" if success else "failed",
            "http_status": status_code or None,
            "content_type": content_type,
            "content_b64": _b64.b64encode(raw[:max_bytes]).decode(),
            "truncated": len(raw) >= max_bytes,
            "error": None if success else ((proc.stderr or b"").decode("utf-8", "replace")[:300] or f"upstream HTTP {status_code or 'unknown'}"),
            "executed_by": "kaggle:cloud-cell",
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except subprocess.TimeoutExpired:
        payload = {
            "job_id": jid, "status": "failed", "error": f"hard timeout {timeout_s}s",
            "executed_by": "kaggle:cloud-cell",
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        payload = {
            "job_id": jid, "status": "failed", "error": str(e)[:300],
            "executed_by": "kaggle:cloud-cell",
            "duration_ms": int((time.time() - t0) * 1000),
        }

    post_result(payload)
    print(f"[WEBEXEC] done job={jid} status={payload.get('status')} ms={payload.get('duration_ms')}", flush=True)

def handle_emergent_sh_task(order_id, prompt):
    report_home("OMNIROUTE_OUT", json.dumps({
        "job_id": order_id, "service": "emergentsh", "status": "FAILED",
        "error": "build_backend_not_configured"
    }))

def handle_oiioii_video_task(order_id, prompt):
    report_home("OMNIROUTE_OUT", json.dumps({
        "job_id": order_id, "service": "oiioii_film_kit", "status": "FAILED",
        "error": "video_backend_not_configured",
        "message": "No render was submitted and no video artifact exists for this request."
    }))

if not door_check():
    print("[INIT] Door not responding, entering retry loop...", flush=True)
else:
    print("[INIT] Door handshake VERIFIED. Connected to relay.", flush=True)
    report_home("KILO", "OMNIROUTE CLOUD CELL v3 WEBEXEC EXECUTOR ONLINE")

seen_orders = set()
beat = 0
door_fail_streak = [0]
while True:
    try:
        orders = fetch_orders()
        door_fail_streak[0] = 0
        for o in orders:
            oid = o.get("id") or str(hash(o.get("text", "")))
            if oid in seen_orders:
                continue
            text = o.get("text", "")
            if "WEB_EXECUTE:" in text:
                try:
                    claim = claim_queue_job(text, "WEB_EXECUTE:", resolve_door(), TOK)
                    if not claim.get("claimed"):
                        if claim.get("reason") != "leased":
                            seen_orders.add(oid)
                        continue
                    text = "WEB_EXECUTE:" + json.dumps(claim["spec"])
                except Exception as ex:
                    print(f"[JOB-GATE] read failed: {type(ex).__name__}; retry next poll", flush=True)
                    continue
            seen_orders.add(oid)
            if "BUILD_SAAS:" in text:
                handle_emergent_sh_task(oid, text.split("BUILD_SAAS:", 1)[1].strip())
            elif "RENDER_VIDEO:" in text:
                handle_oiioii_video_task(oid, text.split("RENDER_VIDEO:", 1)[1].strip())
            elif "WEB_EXECUTE:" in text:
                # subprocess executor inside daemon thread; thread-start failures reported
                def _run_webexec(t=text, _oid=oid):
                    try:
                        handle_webexec_task(t)
                    except Exception as ex:
                        try:
                            _jid = json.loads(t.split("WEB_EXECUTE:", 1)[1]).get("job_id", "?")
                        except Exception:
                            _jid = "?"
                        report_home("WEBEXEC_ERR", f"job {_jid}: {type(ex).__name__}: {ex}")
                try:
                    threading.Thread(target=_run_webexec, daemon=True).start()
                except Exception as ex:
                    report_home("WEBEXEC_ERR", f"thread-start {oid}: {type(ex).__name__}: {ex}")
        if beat % 60 == 0:
            print(f"[HEARTBEAT] beat={beat} door={ACTIVE_DOOR}", flush=True)
    except Exception as ex:
        # DNS watchdog law (same as web supervisors): Kaggle egress DNS dies while the
        # session keeps RUNNING — a phantom cell is worse than a dead one. 12 consecutive
        # door failures (~3 min at 15s poll) -> exit so the rotator revives on a fresh
        # account (fresh DNS lottery). The door itself must be down 3 straight minutes
        # to false-trigger; CF availability makes that acceptable churn.
        door_fail_streak[0] += 1
        if door_fail_streak[0] >= 12:
            print("[WATCHDOG] door unreachable 12 consecutive polls, exiting for rotation", flush=True)
            report_home("KILO", "CLOUD CELL WATCHDOG EXIT (door unreachable)")
            os._exit(1)
        print(f"[LOOP-ERR] {ex}", flush=True)
    beat += 1
    time.sleep(POLL_INTERVAL)
'''

from pathlib import Path
MAIN_CODE = Path(__file__).with_name("queue_job_guard.py").read_text(encoding="utf-8") + "\n" + MAIN_CODE
MAIN_CODE = Path(__file__).with_name("public_capture_graduation.py").read_text(encoding="utf-8") + "\n" + MAIN_CODE

cells = [
    make_cell(["# OmniRoute Cloud Cell -- CPU infinite runway\n", MAIN_CODE]),
]

nb = make_notebook(cells)

path = r"C:\kaggle\working\kaggle_notebooks\omniroute-cloud-cell\omniroute-cloud-cell.ipynb"
with open(path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)
print("Wrote:", path)

with open(path, encoding="utf-8") as f:
    json.load(f)
print("Valid JSON - main code embedded, len =", len(MAIN_CODE))
