"""Controlled OmniRoute service restart to apply OMNIROUTE_DISABLE_CREDENTIAL_HEALTH_CHECK.

Steps:
1. Login (session cookie).
2. POST /api/restart (falls back to /api/shutdown if 404).
3. Wait for the port to go down, then poll /api/monitoring/health until back up.
4. Verify the new process did NOT start the credential health scheduler
   (by checking the fresh service-stderr.log for the scheduler banner).

No secrets are printed.
"""
import os
import sys
import time

import requests

BASE_URL = "http://localhost:20128"
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "<REDACTED>")
LOG_PATH = r"C:\Users\Admin\.omniroute\logs\service-stderr.log"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def login():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"login failed: {r.status_code}")
    log("login OK")
    return s


def trigger_restart(s):
    for endpoint in ("/api/restart", "/api/shutdown"):
        try:
            r = s.post(f"{BASE_URL}{endpoint}", timeout=15)
            log(f"POST {endpoint} -> {r.status_code} {r.text[:200]!r}")
            if r.status_code in (200, 202, 204):
                return endpoint
        except requests.exceptions.RequestException as e:
            # Connection reset/aborted can mean the server is already dying — good.
            log(f"POST {endpoint} raised {type(e).__name__}: {e} (server may be going down)")
            return endpoint
    raise RuntimeError("neither /api/restart nor /api/shutdown accepted")


def wait_down(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(f"{BASE_URL}/api/monitoring/health", timeout=2)
        except requests.exceptions.RequestException:
            log("server is DOWN (as expected)")
            return True
        time.sleep(1)
    log("WARNING: server never went down within timeout")
    return False


def wait_up(timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/api/monitoring/health", timeout=5)
            if r.status_code == 200:
                log(f"server is UP: {r.text[:200]!r}")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError("server did not come back up within timeout")


def check_scheduler_disabled():
    """The new log must NOT contain the credential health scheduler banner."""
    try:
        with open(LOG_PATH, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError as e:
        log(f"could not read log: {e}")
        return None
    started = "[CredentialHealth] Starting credential health check" in content
    tested = "[CredentialHealth] Testing" in content
    log(f"log check: scheduler_started={started}, sweep_ran={tested}")
    return not started and not tested


def main():
    s = login()
    endpoint = trigger_restart(s)
    log(f"restart triggered via {endpoint}; waiting for server to go down...")
    time.sleep(2)
    wait_down()
    log("waiting for server to come back up (NSSM auto-restart, ~10s delay + boot)...")
    wait_up()
    time.sleep(5)  # let startup logs flush
    ok = check_scheduler_disabled()
    if ok is True:
        log("SUCCESS: credential health scheduler is DISABLED in the new process")
    elif ok is False:
        log("WARNING: scheduler still appears active — check .env loading")
    else:
        log("INCONCLUSIVE: could not verify from log")
    # quick latency probe x4 to see if stalls are gone
    log("latency probe x4 on /v1/models:")
    for i in range(4):
        t0 = time.time()
        try:
            r = requests.get(f"{BASE_URL}/v1/models", timeout=45)
            log(f"  attempt {i+1}: {r.status_code} in {time.time()-t0:.1f}s")
        except requests.exceptions.RequestException as e:
            log(f"  attempt {i+1}: FAILED after {time.time()-t0:.1f}s ({e})")


if __name__ == "__main__":
    main()
