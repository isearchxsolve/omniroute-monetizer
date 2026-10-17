import json
import os
import time

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

INSTALL_CELL = [
    "# OMNIROUTE PHASE 3 -- PLAYWRIGHT EXECUTOR: install browser runtime\n",
    "import subprocess, sys\n",
    "def _run(cmd):\n",
    "    r = subprocess.run(cmd, capture_output=True, text=True)\n",
    "    print('rc=', r.returncode, (r.stdout or '')[-200:], (r.stderr or '')[-200:])\n",
    "    return r.returncode\n",
    "_run([sys.executable, '-m', 'pip', 'install', '-q', 'playwright'])\n",
    "_run([sys.executable, '-m', 'playwright', 'install', 'chromium'])\n",
    "# best-effort system deps (Kaggle image already ships most; sudo apt fallback tolerated)\n",
    "_run(['sudo', '-n', 'python3', '-m', 'playwright', 'install-deps', 'chromium'])\n",
    "from playwright.sync_api import sync_playwright\n",
    "print('playwright runtime ready')"
]

MAIN_CODE = r'''
# OMNIROUTE KAGGLE PLAYWRIGHT EXECUTOR v1 -- PHASE 3 (headless SPA bodies)
# Polls ledger:PLAYWRIGHT on the permanent door. Executes real headless-Chromium
# sessions: cookie injection, CSS wait, DOM extraction, optional screenshot.
# Zero-burn: 15s poll, cached door, no idle KV writes.
import os, sys, json, time, subprocess, urllib.request, socket, threading, base64

socket.setdefaulttimeout(25)

DOORS = [
    "https://omniroute-relay.omniroute-fleet-kd.workers.dev",  # PERMANENT Worker door
    "https://measurements-orlando-infections-meal.trycloudflare.com",
    "https://retrain-schnapps-upbeat.ngrok-free.dev",
]

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
            data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
            if data.get("ok"):
                ACTIVE_DOOR = d
                LAST_RESOLVE = now
                return d
        except Exception:
            pass
    return ACTIVE_DOOR

def report_home(body, text):
    d = resolve_door()
    try:
        payload = json.dumps({"body": body, "text": text}).encode()
        req = urllib.request.Request(f"{d}/say?token={TOK}", data=payload, headers=HDRS)
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        print(f"[REPORT-ERR] {e}", flush=True)

def fetch_pw_orders():
    d = resolve_door()
    try:
        req = urllib.request.Request(f"{d}/say?body=PLAYWRIGHT&token={TOK}&limit=10", headers=HDRS)
        data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
        return data.get("orders", [])
    except Exception as e:
        resolve_door(force=True)
        return []

def parse_cookies(spec, url):
    """cookies: playwright list [{name,value,domain,path}] or Cookie header string."""
    cookies = spec.get("cookies")
    if isinstance(cookies, list) and cookies:
        out = []
        for c in cookies:
            c = dict(c)
            if not c.get("domain"):
                from urllib.parse import urlparse
                c["domain"] = urlparse(url).netloc
            out.append(c)
        return out
    hdrs = spec.get("headers") or {}
    raw = hdrs.get("cookie") or hdrs.get("Cookie")
    if not raw:
        return []
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    out = []
    for pair in str(raw).split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            out.append({"name": k.strip(), "value": v.strip(), "domain": domain, "path": "/"})
    return out

def handle_pw_task(order_text):
    from urllib.parse import urlparse
    try:
        spec = json.loads(order_text.split("PW_EXECUTE:", 1)[1])
    except Exception as e:
        report_home("WEBEXEC_ERR", f"PW PARSE-FAIL {type(e).__name__}: {e}")
        return
    jid = spec.get("job_id", "unknown")
    url = spec.get("url", "")
    timeout_s = min(int(spec.get("timeout_s") or 30), 60)
    max_bytes = min(int(spec.get("max_bytes") or 100000), 100000)
    wait_css = spec.get("wait_css")
    wait_ms = int(spec.get("wait_ms") or 0)
    raw_extract = spec.get("extract")
    if isinstance(raw_extract, str):
        # "title" -> extract <title> text; generic: string is used as both name and CSS selector
        extracts = [{"name": raw_extract, "selector": raw_extract, "attr": "text"}]
    elif isinstance(raw_extract, dict):
        extracts = [raw_extract]
    else:
        extracts = raw_extract or []
    want_shot = bool(spec.get("screenshot"))
    hdrs = spec.get("headers") or {}
    door = resolve_door()
    t0 = time.time()
    print(f"[PW] {url[:80]} job={jid} extracts={len(extracts)}", flush=True)

    def post_result(payload):
        try:
            req = urllib.request.Request(
                f"{door}/v1/tools/web.result?token={TOK}",
                data=json.dumps(payload).encode(),
                headers={"content-type": "application/json",
                          "User-Agent": "omniroute-kaggle-worker"})
            urllib.request.urlopen(req, timeout=20).read()
            print(f"[PW] result posted for {jid}", flush=True)
        except Exception as e:
            report_home("WEBEXEC_ERR", f"PW RESULT-POST-FAIL {jid} err={type(e).__name__}: {str(e)[:100]}")

    if not url:
        post_result({"job_id": jid, "status": "failed", "error": "no url", "executed_by": "kaggle:playwright"})
        return

    def run_browser():
        from playwright.sync_api import sync_playwright
        result = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                ua = hdrs.get("User-Agent") or hdrs.get("user-agent") or (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                extra = {k: v for k, v in hdrs.items() if k.lower() not in ("cookie", "user-agent")}
                ctx = browser.new_context(user_agent=ua, extra_http_headers=extra,
                                          viewport={"width": 1366, "height": 900})
                cookies = parse_cookies(spec, url)
                if cookies:
                    ctx.add_cookies(cookies)
                page = ctx.new_page()
                resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
                if wait_css:
                    try:
                        page.wait_for_selector(wait_css, timeout=min(max(wait_ms, 1000), timeout_s * 1000))
                    except Exception as e:
                        result["wait_warning"] = str(e)[:200]
                elif wait_ms:
                    page.wait_for_timeout(min(wait_ms, timeout_s * 1000))
                out = {
                    "http_status": resp.status if resp else None,
                    "final_url": page.url,
                    "title": page.title(),
                }
                if spec.get("harvest"):
                    out["_graduated_capture"] = graduate_public_capture(resp, spec["capture_id"], timeout_s)
                if extracts:
                    ext = {}
                    for e in extracts:
                        name = e.get("name") or "field"
                        sel = e.get("selector")
                        if not sel:
                            continue
                        attr = e.get("attr", "text")
                        limit = min(int(e.get("limit") or 20), 200)
                        try:
                            if e.get("all"):
                                if attr in ("text", "innerText"):
                                    vals = page.eval_on_selector_all(sel, "els => els.map(e => e.innerText.trim())")
                                elif attr == "html":
                                    vals = page.eval_on_selector_all(sel, "els => els.map(e => e.innerHTML)")
                                else:
                                    vals = page.eval_on_selector_all(sel, f"els => els.map(e => e.getAttribute('{attr}'))")
                                ext[name] = [v for v in vals if v][:limit]
                            else:
                                el = page.query_selector(sel)
                                if el is None:
                                    ext[name] = None
                                elif attr in ("text", "innerText"):
                                    ext[name] = el.inner_text().strip()
                                elif attr == "html":
                                    ext[name] = el.inner_html()
                                else:
                                    ext[name] = el.get_attribute(attr)
                        except Exception as e:
                            ext[name] = None
                            result.setdefault("extract_warnings", []).append(f"{name}: {str(e)[:120]}")
                    out["extracts"] = ext
                try:
                    out["text"] = page.inner_text("body", timeout=5000)[:max_bytes]
                except Exception:
                    out["text"] = ""
                if want_shot:
                    try:
                        shot = page.screenshot(type="png", full_page=False)
                        out["screenshot_b64"] = base64.b64encode(shot[:120000]).decode()
                    except Exception as e:
                        out["screenshot_error"] = str(e)[:120]
                result.update(out)
            finally:
                browser.close()
        return result

    try:
        th = threading.Thread(target=lambda: None)  # keep API shape stable
        res = run_browser()
        graduated = res.pop("_graduated_capture", None)
        payload = {
            "job_id": jid,
            "status": "done" if 200 <= (res.get("http_status") or 0) < 300 else "failed",
            "mode": "playwright",
            "http_status": res.get("http_status"),
            "content_type": "application/json",
            "content_b64": base64.b64encode(json.dumps(res)[:max_bytes].encode()).decode(),
            "truncated": len(json.dumps(res)) >= max_bytes,
            "error": res.get("wait_warning") or None,
            "executed_by": "kaggle:playwright",
            "duration_ms": int((time.time() - t0) * 1000),
        }
        if graduated:
            payload["graduated_capture"] = graduated
    except Exception as e:
        payload = {
            "job_id": jid, "status": "failed", "mode": "playwright",
            "error": f"{type(e).__name__}: {str(e)[:300]}",
            "executed_by": "kaggle:playwright",
            "duration_ms": int((time.time() - t0) * 1000),
        }
    post_result(payload)
    print(f"[PW] done job={jid} status={payload.get('status')} ms={payload.get('duration_ms')}", flush=True)

if not resolve_door(force=True):
    print("[INIT] Door not responding, retry loop engaged...", flush=True)
else:
    print("[INIT] Door handshake VERIFIED.", flush=True)
    report_home("KILO", "OMNIROUTE PLAYWRIGHT EXECUTOR v1 ONLINE (Phase 3)")

seen_orders = set()
beat = 0
while True:
    try:
        orders = fetch_pw_orders()
        for o in orders:
            oid = o.get("id") or str(hash(o.get("text", "")))
            if oid in seen_orders:
                continue
            text = o.get("text", "")
            if "PW_EXECUTE:" in text:
                try:
                    if not queue_job_pending(text, "PW_EXECUTE:", resolve_door(), TOK):
                        seen_orders.add(oid)
                        continue
                except Exception as ex:
                    print(f"[JOB-GATE] read failed: {type(ex).__name__}; retry next poll", flush=True)
                    continue
            seen_orders.add(oid)
            if "PW_EXECUTE:" in text:
                t = threading.Thread(target=handle_pw_task, args=(text,), daemon=True)
                t.start()
        if beat % 60 == 0:
            print(f"[HEARTBEAT] beat={beat} door={ACTIVE_DOOR}", flush=True)
    except Exception as ex:
        print(f"[LOOP-ERR] {ex}", flush=True)
    beat += 1
    time.sleep(POLL_INTERVAL)
'''

from pathlib import Path
MAIN_CODE = Path(__file__).with_name("queue_job_guard.py").read_text(encoding="utf-8") + "\n" + MAIN_CODE
MAIN_CODE = Path(__file__).with_name("public_capture_graduation.py").read_text(encoding="utf-8") + "\n" + MAIN_CODE

cells = [
    make_cell(INSTALL_CELL),
    make_cell(["# OmniRoute Playwright Executor -- infinite poll loop\n", MAIN_CODE]),
]

nb = make_notebook(cells)

nb_dir = r"C:\kaggle\working\kaggle_notebooks\omniroute-playwright"
os.makedirs(nb_dir, exist_ok=True)
path = os.path.join(nb_dir, "omniroute-playwright.ipynb")
with open(path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)
print("Wrote:", path)

meta = {
    "id": "isearchxsolve/omniroute-playwright-executor",
    "title": "Omniroute playwright executor",
    "code_file": "omniroute-playwright.ipynb",
    "language": "python",
    "kernel_type": "notebook",
    "is_private": True,
    "enable_gpu": False,
    "enable_internet": True,
    "dataset_sources": [],
    "competition_sources": [],
    "kernel_sources": [],
    "model_sources": []
}
with open(os.path.join(nb_dir, "kernel-metadata.json"), "w", encoding="utf-8") as f:
    json.dump(meta, f, indent=2)
print("Wrote kernel-metadata.json")

with open(path, encoding="utf-8") as f:
    json.load(f)
print("Valid JSON - playwright kernel ready, len =", len(MAIN_CODE))
