#!/usr/bin/env python3
"""
KAGGLE FLEET AUTO-ROTATOR v1 -- the wire never goes down.
Watches every fleet kernel; at T-45min before its 12h expiry, pushes a fresh
session on the NEXT account (old session keeps serving until natural death =
zero-downtime overlap). ERROR/COMPLETE kernels are revived immediately.
All fleet state lives in the permanent door's KV -- kernels are disposable bodies.

Run: python rotator.py   (foreground)   -- or via background process
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ---------- constants ----------
WORK = Path("C:/kaggle/working")
VAULT = Path("D:/anonym/vault")
STATE_FILE = WORK / "rotation_state.json"
LOG_FILE = WORK / "rotator.log"
DOOR = "https://omniroute-relay.omniroute-fleet-kd.workers.dev"
TOK_DOOR = "GOLD24"
WINDOW_H = 12
MARGIN_MIN = 45          # pre-rotate this many minutes before expiry
POLL_S = 300             # 5 min cycle
GH_REPO = "isearchxsolve/omniroute-monetizer"
GH_TOKEN = "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"

# account pool: name -> token (None = default ~/.kaggle/kaggle.json)
ACCOUNTS = {
    "isearchxsolve": None,                      # token_1/6 (default kaggle.json)
    "n42888": str(VAULT / "kaggle_token_2.txt"),
    "kunaldas3104": str(VAULT / "kaggle_token_3.txt"),
    "kdas19999": str(VAULT / "kaggle_token_4.txt"),
}
CYCLE = list(ACCOUNTS.keys())  # rotation order

# managed kernels: dir under kaggle_notebooks, current owner, session start epoch
# start epochs seeded 2026-10-12 (IST times converted); rotator re-arms on each push
KERNELS = [
    {"name": "cloud-cell", "dir": "omniroute-cloud-cell", "gen": "gen_cloud_cell.py",
     "current": "kdas19999", "started": 1791790949, "critical": True},
    {"name": "fleet-worker", "dir": "kaggle-fleet-worker", "gen": None,
     "current": "isearchxsolve", "started": 1791760229, "critical": True},
    {"name": "oiioii-web", "dir": "oii oii-kaggle-web", "gen": None,
     "current": "isearchxsolve", "started": 1791765329, "critical": True},
    {"name": "emergentsh-web", "dir": "emergentsh-kaggle-web", "gen": None,
     "current": "isearchxsolve", "started": 1791765329, "critical": True},
    {"name": "relay-backup", "dir": "omniroute-relay", "gen": None,
     "current": "n42888", "started": 1791766409, "critical": False},
    {"name": "playwright", "dir": "omniroute-playwright", "gen": "gen_playwright.py",
     "current": "kdas19999", "started": int(time.time()), "critical": True},
]

KAGGLE_SLUGS = {
    "cloud-cell": "omniroute-cloud-cell-cpu-worker",
    "fleet-worker": "kaggle-fleet-worker-cpu-only",
    "oiioii-web": "oiioii-kaggle-web",
    "emergentsh-web": "emergentsh-kaggle-web",
    "relay-backup": "omniroute-relay",
    "playwright": "omniroute-playwright-executor",
}

# ---------- helpers ----------
def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def door_report(text, body="ROTATION"):
    try:
        data = json.dumps({"body": body, "text": text[:400]}).encode()
        req = urllib.request.Request(f"{DOOR}/say?token={TOK_DOOR}", data=data,
                                     headers={"content-type": "application/json",
                                              "User-Agent": "omniroute-rotator"})
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        log(f"door report failed: {e}")

def kaggle_env(account):
    """env for subprocess: token of the account (default kaggle.json if None)."""
    env = dict(os.environ)
    env.pop("KAGGLE_USERNAME", None)
    env.pop("KAGGLE_KEY", None)
    tok_path = ACCOUNTS.get(account)
    if tok_path and Path(tok_path).exists():
        env["KAGGLE_API_TOKEN"] = Path(tok_path).read_text().strip()
    else:
        env.pop("KAGGLE_API_TOKEN", None)
    return env

def kaggle_status(account, owner, slug):
    """status via the OWNER's token (private kernels need owner creds)."""
    r = subprocess.run(["kaggle", "kernels", "status", f"{owner}/{slug}"],
                       capture_output=True, text=True, timeout=60,
                       env=kaggle_env(owner))
    out = (r.stdout or "") + (r.stderr or "")
    if "RUNNING" in out:
        return "RUNNING"
    if "COMPLETE" in out:
        return "COMPLETE"
    if "ERROR" in out:
        return "ERROR"
    if "QUEUED" in out:
        return "QUEUED"
    return "UNKNOWN"

def next_account(current, exclude_failing=None):
    """next account in cycle after current, skipping ones that fail to push."""
    i = CYCLE.index(current) if current in CYCLE else 0
    order = CYCLE[i + 1:] + CYCLE[:i + 1]     # starts with the account AFTER current
    if exclude_failing:
        order = [a for a in order if a not in exclude_failing] or order
    return order

def push_kernel(k, account):
    """rewrite metadata id owner -> account, push with account's token. True on success."""
    nb_dir = WORK / "kaggle_notebooks" / k["dir"]
    meta_path = nb_dir / "kernel-metadata.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["id"] = f"{account}/{KAGGLE_SLUGS[k['name']]}"
        # private datasets are per-account: retarget our dataset copies to the push target
        meta["dataset_sources"] = [
            f"{account}/{s.split('/', 1)[1]}" if s.endswith("/fleet-apps") else s
            for s in meta.get("dataset_sources", [])
        ]
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # optional generator refresh (cloud cell only)
        if k.get("gen"):
            g = WORK / k["gen"]
            if g.exists():
                gr = subprocess.run([sys.executable, str(g)], capture_output=True,
                                    text=True, timeout=120, cwd=str(WORK))
                if gr.returncode != 0:
                    log(f"{k['name']}: generator rc={gr.returncode} (pushing anyway)")

        r = subprocess.run(["kaggle", "kernels", "push", "-p", str(nb_dir)],
                           capture_output=True, text=True, timeout=180,
                           env=kaggle_env(account))
        out = (r.stdout or "") + (r.stderr or "")
        ok = "successfully pushed" in out
        log(f"{k['name']}: push -> {account}: {'OK' if ok else 'FAIL ' + out[:150]}")
        return ok, out[:200]
    except Exception as e:
        log(f"{k['name']}: push exception on {account}: {e}")
        return False, str(e)

def rotate(k, reason):
    """push kernel onto the next working account; update state."""
    tried, failures = [], []
    for account in next_account(k["current"]):
        if account in tried:
            continue
        tried.append(account)
        ok, out = push_kernel(k, account)
        if ok:
            old = k["current"]
            k["current"] = account
            k["started"] = int(time.time())
            save_state()
            msg = (f"{k['name']}: ROTATED {old} -> {account} ({reason}). "
                   f"old session serves until natural death; new session live now.")
            log(msg)
            door_report(msg)
            return True
        failures.append(f"{account}: {out[:80]}")
        # account at cap / push rejected -> try next in cycle
    log(f"{k['name']}: ALL accounts failed: {failures}")
    door_report(f"{k['name']}: rotation FAILED on all accounts: {failures}",
                body="ROTATION_ERR")
    return False

def load_state():
    if STATE_FILE.exists():
        try:
            st = json.loads(STATE_FILE.read_text())
            for k in KERNELS:
                if k["name"] in st:
                    k["current"] = st[k["name"]].get("current", k["current"])
                    k["started"] = st[k["name"]].get("started", k["started"])
        except Exception as e:
            log(f"state load failed (using seeded): {e}")

def save_state():
    st = {k["name"]: {"current": k["current"], "started": k["started"]} for k in KERNELS}
    STATE_FILE.write_text(json.dumps(st, indent=2))

def hours_left(k):
    return WINDOW_H - (time.time() - k["started"]) / 3600.0

# ---------- main loop ----------
def main():
    log("AUTO-ROTATOR v1 online -- window=12h, margin=45min, poll=5min")
    log("accounts: " + ", ".join(CYCLE))
    load_state()
    door_report("AUTO-ROTATOR ONLINE: watching " + ", ".join(k["name"] for k in KERNELS))

    while True:
        now = time.time()
        for k in KERNELS:
            try:
                hl = hours_left(k)
                status = kaggle_status(k["current"], k["current"], KAGGLE_SLUGS[k["name"]])
                log(f"{k['name']}: owner={k['current']} status={status} hours_left={hl:.2f}")

                if status in ("ERROR", "COMPLETE", "UNKNOWN"):
                    # dead or unqueryable -> revive immediately (same-or-next account)
                    if not rotate(k, f"status={status}, revived"):
                        log(f"{k['name']}: revival failed, retry next cycle")

                elif hl <= MARGIN_MIN / 60.0:
                    # pre-rotate on a DIFFERENT account while this one still serves
                    if not rotate(k, f"pre-rotation, {hl:.2f}h left"):
                        log(f"{k['name']}: pre-rotation failed, retry next cycle")

                # dead-session cleanup: if we're way past window end and still marked
                # this account, the push may have silently failed -> force rotate
                elif hl <= -0.5:
                    if not rotate(k, "past window end"):
                        log(f"{k['name']}: forced rotation failed, retry next cycle")

            except Exception as e:
                log(f"{k['name']}: cycle error: {type(e).__name__}: {e}")
        save_state()
        time.sleep(POLL_S)

if __name__ == "__main__":
    main()
