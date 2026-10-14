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

SUPERVISOR_TEMPLATE = r'''
# OMNIROUTE WEB KERNEL SUPERVISOR v3 -- ONE immortal cell. NOTHING blocks.
# Every dependency (pip deps, cloudflared, app code, shim, server, tunnel,
# registration) is ensured inside the retry loop. The FIRST act is an
# IP-pinned door report, so the kernel is observable even with zero DNS.
import subprocess, os, time, threading, re, json, base64, io, zipfile, urllib.request, socket, ssl, http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LABEL = "__LABEL__"
REPO_DIR = "__REPO_DIR__"
APP_DIR = "__APP_DIR__"
PORT = __PORT__
SERVICE = "__SERVICE__"
ASSET_KEY = "__ASSET_KEY__"
GH_REPO = "__GH_REPO__"
SECRET_KEY = "__SECRET_KEY__"
GH_TOKEN = "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"
DOOR = "https://omniroute-relay.omniroute-fleet-kd.workers.dev"
DOOR_HOST = "omniroute-relay.omniroute-fleet-kd.workers.dev"
DOOR_IPS = ["104.21.11.138", "172.67.166.36"]
TOK = "GOLD24"
CLONE_URL = "https://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@github.com/__GH_REPO_PATH__.git"
CFL_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"

CODE_OK = False
DEPS_OK = False
CFL_OK = False
SHIM_UP = False
SERVER_OK = False
FOUND_URL = None
PUBLISHED = False
LAST_REGISTER = 0.0
SERVER_PROC = None
TUNNEL_PROC = None
CFL_TAIL = []
UVI_TAIL = []
LAST_SPAWN = [0.0]
LAST_REPORT = [0.0]
LAST_STATE = [""]

def log(msg):
    print("[" + LABEL + "] " + str(msg), flush=True)

class PinnedConn(http.client.HTTPSConnection):
    def connect(self):
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=DOOR_HOST)

def door_fetch(path, data=None, timeout=20):
    """Door request: DNS first, then IP-pinned HTTPS (SNI = real hostname)."""
    try:
        req = urllib.request.Request(DOOR + path, data=data,
                                     headers={"content-type": "application/json",
                                              "User-Agent": "omniroute-kaggle-worker"})
        return urllib.request.urlopen(req, timeout=timeout).read()
    except Exception:
        pass
    payload = data if isinstance(data, bytes) else (str(data).encode() if data else None)
    last = None
    for ip in DOOR_IPS:
        try:
            conn = PinnedConn(ip, timeout=timeout)
            conn.request("POST" if payload else "GET", path, body=payload,
                         headers={"Host": DOOR_HOST,
                                  "content-type": "application/json",
                                  "User-Agent": "omniroute-kaggle-worker"})
            resp = conn.getresponse()
            out = resp.read()
            conn.close()
            if resp.status == 200:
                return out
            last = "HTTP " + str(resp.status)
        except Exception as e:
            last = str(e)
    raise RuntimeError("door unreachable (dns+ip): " + str(last))

def door_report(text, body="TUNNELDBG"):
    try:
        door_fetch("/say?token=" + TOK, data=json.dumps(
            {"body": body, "text": str(text)[:400]}).encode())
    except Exception:
        pass

def pip_bg_running():
    return False

# serialized pip: one attempt per lock slot; loop stays alive around it
PIP_LOCK = threading.Lock()
PIP_DONE = [False]
FAIL_N = [0]

def _strip_pins(lines):
    # py3.13 wheel lottery: pins validated on py3.11 may have no cp313 wheels.
    # Fallback pass keeps names (+extras like [bcrypt]) but drops version specifiers.
    import re
    out = []
    for l in lines:
        s = l.strip()
        if not s or s.startswith("#") or s.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?", s)
        if not m:
            continue
        name = m.group(1)
        if name.lower() in ("pyside6", "asyncpg"):
            continue
        out.append(name + (m.group(2) or ""))
    return out

def ensure_deps_serial():
    global DEPS_OK
    if DEPS_OK or PIP_DONE[0]:
        return
    if not PIP_LOCK.acquire(blocking=False):
        return
    try:
        req_txt = None
        for cand in (os.path.join(REPO_DIR, "backend", "requirements.txt"),
                     os.path.join(REPO_DIR, "requirements.txt")):
            if os.path.exists(cand):
                req_txt = cand
                break
        to_install = []
        lines = []
        if req_txt:
            lines = [l for l in open(req_txt, encoding="utf-8", errors="ignore").read().splitlines()
                     if l.strip() and not l.strip().startswith("#")
                     and not l.strip().startswith("-r")
                     and not l.strip().lower().startswith("asyncpg")
                     and not l.strip().lower().startswith("pyside6")]
        # pass 1: exact pins (laptop-validated); pass 2: pins stripped for py3.13 wheels
        fpath = os.path.join(REPO_DIR, ".req_filtered.txt")
        r = None
        for pi, plist in enumerate([lines, _strip_pins(lines)]):
            open(fpath, "w", encoding="utf-8").write("\n".join(plist))
            to_install = ["-r" + fpath, "asyncpg>=0.30.0", "slowapi", "email-validator", "aiosqlite"]
            r = subprocess.run(["python", "-m", "pip", "install", "-q"] + to_install,
                               capture_output=True, text=True, timeout=1800)
            if r.returncode == 0:
                if pi == 1:
                    log("deps installed OK via unpinned fallback (pass 2)")
                break
        if r is not None and r.returncode == 0:
            DEPS_OK = True
            PIP_DONE[0] = True
            log("app dependencies installed OK")
            door_report(LABEL + " dependencies installed OK")
        else:
            FAIL_N[0] += 1
            tail = str((r.stderr if r else ""))[-200:]
            log("app dependency install failed: " + str(tail)[-140:])
            # KV-write discipline: report first failure, then every 15th (retry loop must not burn quota)
            if FAIL_N[0] == 1 or FAIL_N[0] % 15 == 0:
                door_report(LABEL + " dependency install failed [" + str(FAIL_N[0]) + "]: " + tail)
            time.sleep(60)  # back off inside the lock slot; loop stays alive around it
    except Exception as e:
        log("pip exception: " + str(e)[:140])
        FAIL_N[0] += 1
        if FAIL_N[0] == 1 or FAIL_N[0] % 15 == 0:
            door_report(LABEL + " pip exception [" + str(FAIL_N[0]) + "]: " + str(e)[:160])
        time.sleep(60)
    finally:
        PIP_LOCK.release()

def ensure_cloudflared():
    global CFL_OK
    if CFL_OK:
        return
    path = "/usr/local/bin/cloudflared"
    if os.path.exists(path) and os.path.getsize(path) > 1000000:
        CFL_OK = True
        return
    srcs = [p for p in ("/kaggle/input/cloudflared-offline/cloudflared-linux-amd64",)]
    import glob as _g
    srcs = _g.glob("/kaggle/input/*/cloudflared-linux-amd64") or srcs
    for src in srcs:
        if os.path.exists(src):
            try:
                import shutil
                shutil.copyfile(src, path)
                if os.path.getsize(path) > 1000000:
                    os.chmod(path, 0o755)
                    CFL_OK = True
                    log("cloudflared staged from dataset mount")
                    return
            except Exception as e:
                log("cloudflared copy failed: " + str(e)[:100])
    # download fallback (GitHub releases are flaky from Kaggle; best effort)
    try:
        r = subprocess.run(["wget", "-q", CFL_URL, "-O", path], timeout=120)
        if r.returncode == 0 and os.path.getsize(path) > 1000000:
            os.chmod(path, 0o755)
            CFL_OK = True
            log("cloudflared downloaded")
    except Exception as e:
        log("cloudflared download failed: " + str(e)[:100])

def stage_code():
    global CODE_OK
    if CODE_OK:
        return
    try:
        raw = base64.b64decode(door_fetch("/v1/assets/" + ASSET_KEY + "?token=" + TOK, timeout=60))
        os.makedirs(REPO_DIR, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for entry in z.infolist():
                name = entry.filename.replace("\\", "/")
                if name.endswith("/") or entry.is_dir():
                    continue
                name = name.lstrip("/")
                if name.startswith("__MACOSX") or "/__MACOSX/" in name:
                    continue
                target = os.path.join(REPO_DIR, *name.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(entry) as srcf, open(target, "wb") as dstf:
                    dstf.write(srcf.read())
        if os.path.exists(REPO_DIR) and len(os.listdir(REPO_DIR)) > 2:
            CODE_OK = True
            log("code staged from door asset " + ASSET_KEY + " (" + str(len(raw)) + " bytes)")
            return
    except Exception as e:
        log("door asset fetch failed: " + str(e))
    try:
        r = subprocess.run(["git", "clone", "--depth", "1", CLONE_URL, REPO_DIR],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and len(os.listdir(REPO_DIR)) > 2:
            CODE_OK = True
            log("code cloned from GitHub")
    except Exception as e:
        log("clone error: " + str(e)[:120])

def shim_alive():
    try:
        urllib.request.urlopen("http://127.0.0.1:8190/v1/models", timeout=4).read(64)
        return True
    except Exception:
        return False

def ensure_shim():
    global SHIM_UP
    if SHIM_UP and shim_alive():
        return
    try:
        SHIM = ThreadingHTTPServer(("127.0.0.1", 8190), ShimHandler)
        threading.Thread(target=SHIM.serve_forever, daemon=True).start()
        SHIM_UP = True
        log("session-pool shim UP on 127.0.0.1:8190")
    except Exception as e:
        if "Address already in use" not in str(e):
            log("shim start failed: " + str(e))
            door_report(LABEL + " shim start failed: " + str(e))
        SHIM_UP = shim_alive()

class ShimHandler(BaseHTTPRequestHandler):
    def _models(self):
        data = json.dumps({"object": "list",
                           "data": [{"id": "session-pool/auto", "object": "model",
                                     "owned_by": "omniroute-session-pool"}]}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def _relay(self):
        if self.command == "GET" and self.path.split("?")[0] == "/v1/models":
            self._models()
            return
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else None
        path = self.path + ("&" if "?" in self.path else "?") + "token=" + TOK
        headers = {"Host": DOOR_HOST, "User-Agent": "omniroute-session-pool-shim",
                   "content-type": self.headers.get("content-type") or "application/json"}
        status, data, ctype = 502, json.dumps({"error": "door unreachable"}).encode(), "application/json"
        try:
            conn = http.client.HTTPSConnection(DOOR_HOST, timeout=60)
            conn.request(self.command, path, body=body, headers=headers)
            resp = conn.getresponse()
            status, data, ctype = resp.status, resp.read(), resp.getheader("content-type") or "application/json"
            conn.close()
        except Exception:
            for ip in DOOR_IPS:
                try:
                    conn = PinnedConn(ip, timeout=60)
                    conn.request(self.command, path, body=body, headers=headers)
                    resp = conn.getresponse()
                    status, data, ctype = resp.status, resp.read(), resp.getheader("content-type") or "application/json"
                    conn.close()
                    break
                except Exception as e2:
                    status, data = 502, json.dumps({"error": "door unreachable", "detail": str(e2)[:150]}).encode()
        self.send_response(status)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        self._relay()
    def do_POST(self):
        self._relay()
    def do_PUT(self):
        self._relay()
    def do_DELETE(self):
        self._relay()
    def log_message(self, fmt, *args):
        pass

def local_alive():
    try:
        urllib.request.urlopen("http://127.0.0.1:" + str(PORT) + "/", timeout=4).read(64)
        return True
    except Exception:
        return False

def ensure_server():
    global SERVER_OK, SERVER_PROC
    if SERVER_OK and local_alive():
        return
    # backoff: if we spawned less than 60s ago, let it cook before touching it
    if SERVER_PROC is not None and (time.time() - LAST_SPAWN[0]) < 60:
        if local_alive():
            SERVER_OK = True
        return
    if SERVER_PROC is not None:
        try:
            SERVER_PROC.kill()
        except Exception:
            pass
        SERVER_PROC = None
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO_DIR + os.pathsep + APP_DIR
    env["OMNIROUTE_BASE_URL"] = "http://127.0.0.1:8190/v1"
    env["INFERENCE_PROVIDER"] = "omniroute"
    if SECRET_KEY:
        env["SECRET_KEY"] = SECRET_KEY
    SERVER_PROC = subprocess.Popen(["python", "-m", "uvicorn", "app.main:app",
                                    "--host", "0.0.0.0", "--port", str(PORT)],
                                   cwd=APP_DIR, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)

    def _drain_uvi():
        for line in SERVER_PROC.stdout:
            UVI_TAIL.append(line.strip()[:160])
            del UVI_TAIL[:-10]
    threading.Thread(target=_drain_uvi, daemon=True).start()
    LAST_SPAWN[0] = time.time()
    time.sleep(12)
    SERVER_OK = local_alive()
    log("uvicorn up=" + str(SERVER_OK) + " port=" + str(PORT))
    if not SERVER_OK:
        errs = [l for l in UVI_TAIL if "Error" in l or "error" in l] or UVI_TAIL[-3:]
        # KV-write discipline: report at most once per 10 minutes
        if time.time() - LAST_REPORT[0] > 600:
            LAST_REPORT[0] = time.time()
            door_report(LABEL + " uvicorn down. out: " + " | ".join(errs[-3:]))

def ensure_tunnel():
    global TUNNEL_PROC, FOUND_URL
    if FOUND_URL and TUNNEL_PROC is not None and TUNNEL_PROC.poll() is None:
        return
    if not CFL_OK:
        return
    FOUND_URL = None
    TUNNEL_PROC = subprocess.Popen(["/usr/local/bin/cloudflared", "tunnel", "--url",
                                    "http://localhost:" + str(PORT), "--no-autoupdate"],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)
    deadline = time.time() + 50
    for line in TUNNEL_PROC.stdout:
        CFL_TAIL.append(line.strip()[:120])
        del CFL_TAIL[:-8]
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            FOUND_URL = m.group(0)
            log("tunnel UP: " + FOUND_URL)
            door_report(LABEL + " TUNNEL UP: " + FOUND_URL, body="KILO")
            return
        if time.time() > deadline:
            break
    try:
        TUNNEL_PROC.kill()
    except Exception:
        pass
    TUNNEL_PROC = None
    log("tunnel attempt failed; tail: " + " | ".join(CFL_TAIL[-3:]))
    door_report(LABEL + " tunnel attempt failed. tail: " + " | ".join(CFL_TAIL[-4:]))

def publish_github():
    global PUBLISHED
    if PUBLISHED or not FOUND_URL:
        return
    try:
        api = "https://api.github.com/repos/" + GH_REPO + "/contents/public-url.txt"
        hdrs = {"Authorization": "token " + GH_TOKEN, "Accept": "application/vnd.github+json",
                "User-Agent": "kaggle-fleet"}
        sha = None
        try:
            req = urllib.request.Request(api, headers=hdrs)
            sha = json.loads(urllib.request.urlopen(req, timeout=15).read()).get("sha")
        except Exception:
            sha = None
        body = {"message": "fleet public url", "content": base64.b64encode(FOUND_URL.encode()).decode()}
        if sha:
            body["sha"] = sha
        req = urllib.request.Request(api, data=json.dumps(body).encode(), headers=hdrs, method="PUT")
        urllib.request.urlopen(req, timeout=20).read()
        PUBLISHED = True
        log("public URL published to GitHub")
    except Exception as e:
        log("github publish failed: " + str(e))

def register_gateway():
    global LAST_REGISTER
    if not FOUND_URL:
        return
    if time.time() - LAST_REGISTER < 600:
        return
    try:
        payload = json.dumps({"service": SERVICE, "url": FOUND_URL,
                              "meta": {"port": PORT, "label": LABEL}}).encode()
        door_fetch("/v1/gateway/register?token=" + TOK, data=payload)
        LAST_REGISTER = time.time()
        log("gateway session registered: " + FOUND_URL)
    except Exception as e:
        log("gateway register failed: " + str(e))
        door_report(LABEL + " gateway register failed: " + str(e))

log("supervisor v3 starting (one immortal cell, nothing blocks)")
door_report(LABEL + " supervisor v3 STARTING (ip-pin observable)")

# DNS watchdog: Kaggle sessions get dead DNS for hours. A zombie that cannot
# reach the door is worse than a dead session -- the rotator can revive a dead
# one onto a fresh account (fresh DNS lottery). After 12 consecutive probe
# failures (~3 min), self-terminate so the rotator rotates us.
DNS_FAILS = [0]

def door_probe():
    try:
        door_fetch("/health?token=" + TOK, timeout=8)
        if DNS_FAILS[0] >= 3:
            log("door reachable again after " + str(DNS_FAILS[0]) + " failed probes")
        DNS_FAILS[0] = 0
    except Exception:
        DNS_FAILS[0] += 1

beat = 0
while True:
    try:
        door_probe()
        if DNS_FAILS[0] >= 12:
            log("door unreachable " + str(DNS_FAILS[0]) + " consecutive probes -- self-terminating for rotation")
            door_report(LABEL + " DNS dead " + str(DNS_FAILS[0]) + " probes -- self-terminating for fresh session")
            time.sleep(2)
            os._exit(1)
        ensure_cloudflared()
        stage_code()
        if CODE_OK:
            ensure_deps_serial()
            if DEPS_OK:
                ensure_shim()
                ensure_server()
                if SERVER_OK:
                    ensure_tunnel()
                    publish_github()
                    register_gateway()
        if beat % 20 == 0:
            state_line = ("beat=" + str(beat) + " code=" + str(CODE_OK) + " deps=" + str(DEPS_OK)
                          + " cfl=" + str(CFL_OK) + " server=" + str(SERVER_OK)
                          + " tunnel=" + str(bool(FOUND_URL))
                          + " dnsfails=" + str(DNS_FAILS[0])
                          + " uvi: " + " | ".join(UVI_TAIL[-2:]))
            # KV-write discipline: report on state CHANGE only (plus rare heartbeat)
            key = "code=" + str(CODE_OK) + " deps=" + str(DEPS_OK) + " cfl=" + str(CFL_OK) \
                  + " server=" + str(SERVER_OK) + " tunnel=" + str(bool(FOUND_URL))
            if key != LAST_STATE[0] and not (CODE_OK and DEPS_OK and SERVER_OK and FOUND_URL):
                LAST_STATE[0] = key
                door_report(LABEL + " state " + state_line)
            elif beat % 200 == 0:
                door_report(LABEL + " heartbeat " + state_line)
            log(state_line)
    except Exception as e:
        log("supervisor cycle error: " + type(e).__name__ + ": " + str(e))
    beat += 1
    time.sleep(15)
'''

def build_notebook(label, repo_dir, port, service, asset_key, gh_repo, gh_repo_path, secret_key=""):
    supervisor = (SUPERVISOR_TEMPLATE
                  .replace("__LABEL__", label)
                  .replace("__REPO_DIR__", repo_dir)
                  .replace("__APP_DIR__", repo_dir + "/backend")
                  .replace("__PORT__", str(port))
                  .replace("__SERVICE__", service)
                  .replace("__ASSET_KEY__", asset_key)
                  .replace("__GH_REPO__", gh_repo)
                  .replace("__GH_REPO_PATH__", gh_repo_path)
                  .replace("__SECRET_KEY__", secret_key))
    return make_notebook([
        make_cell([l + "\n" for l in supervisor.strip().split("\n")]),
    ])

base = r"C:\kaggle\working\kaggle_notebooks"

ESH_SECRET = "0UCJgss9E5cfc99YOl9NNCQemSjd0hse5tomL85Knm3xiTn0"

nb1 = build_notebook("OiiOii", "/kaggle/working/oioi", 8010,
                     "oiioii", "oioi-zip", "isearchxsolve/oioi", "isearchxsolve/oioi")
p1 = os.path.join(base, "oii oii-kaggle-web", "oii oii-kaggle-web.ipynb")
with open(p1, "w", encoding="utf-8") as f:
    json.dump(nb1, f, indent=1)
print("Wrote:", p1)

nb2 = build_notebook("EmergentSH", "/kaggle/working/emergentsh", 8000,
                     "emergentsh", "emergentsh-zip", "isearchxsolve/emergentsh", "isearchxsolve/emergentsh", ESH_SECRET)
p2 = os.path.join(base, "emergentsh-kaggle-web", "emergentsh-kaggle-web.ipynb")
with open(p2, "w", encoding="utf-8") as f:
    json.dump(nb2, f, indent=1)
print("Wrote:", p2)

for p in (p1, p2):
    with open(p, encoding="utf-8") as f:
        json.load(f)
    print("Valid JSON:", p)
