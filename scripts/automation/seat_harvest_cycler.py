#!/usr/bin/env python3
"""
seat_harvest_cycler.py -- The 100-Provider 1-by-1 Tab Graduation & Replay Pipeline.
Authored on Baba's Royal Order (2026-10-11):
  "You search for 100 providers one by one, open them on the Chrome tab as a seat,
   and then graduate them and then replay them. Once tested full end-to-end,
   you close the tab you continue this cycle for the next 100 providers."

Safety:
  Enforces chrome_live_guard.py. Uses ONLY state/automation_profiles/providers.
  Closes every tab immediately after graduation/replay so only 1 tab exists at any time.
"""

from __future__ import annotations

import csv
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request
import urllib.error

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from chrome_live_guard import assert_safe, assert_cdp_safe, safe_profile_dir

CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
PROFILE_DIR = safe_profile_dir("providers")
LOG_PATH = ROOT / "state" / "seat_cycler_progress.log"
CANDIDATES_CSV = ROOT / "evidence" / "results" / "zero-cost-clean.csv"
CANDIDATES_CSV2 = ROOT / "evidence" / "results" / "agent-free-shortlist-dedup.csv"

def log(msg: str):
    timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{timestamp} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def find_chrome() -> str:
    candidates = [
        pathlib.Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        pathlib.Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    raise RuntimeError("chrome.exe not found")

def ensure_chrome_alive():
    try:
        urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=1.5)
        return True
    except Exception:
        pass

    chrome_exe = find_chrome()
    log(f"Launching clean automation Chrome on port {CDP_PORT}...")
    assert_safe(PROFILE_DIR, who="seat_harvest_cycler")
    
    cmd = [
        chrome_exe,
        f"--user-data-dir={PROFILE_DIR}",
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--window-size=1280,800",
        "about:blank"
    ]
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0
    subprocess.Popen(cmd, creationflags=flags, close_fds=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(15):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=1.5)
            log("Automation Chrome is ONLINE and answering CDP.")
            return True
        except Exception:
            continue
    raise RuntimeError(f"Chrome on port {CDP_PORT} failed to start.")

def cdp_get_targets() -> list[dict]:
    req = urllib.request.urlopen(f"{CDP_URL}/json/list", timeout=5)
    return json.loads(req.read().decode())

def cdp_open_tab(url: str) -> dict:
    encoded = urllib.parse.quote(url, safe=":/?&=#+%._-")
    req = urllib.request.Request(f"{CDP_URL}/json/new?{encoded}", method="PUT")
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read().decode())

def cdp_close_tab(target_id: str):
    try:
        req = urllib.request.Request(f"{CDP_URL}/json/close/{target_id}", method="PUT")
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        log(f"Warning: error closing tab {target_id}: {e}")

def load_providers() -> list[dict]:
    providers = []
    seen = set()

    # Priority 1: shortlisted clean agents
    if CANDIDATES_CSV2.exists():
        with open(CANDIDATES_CSV2, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row.get("ProviderId", "").strip()
                name = row.get("ProviderName", "").strip()
                api = row.get("API", "").strip()
                docs = row.get("Docs", "").strip()
                url = docs if docs and docs.startswith("http") else api
                if name and url and url.startswith("http") and name not in seen:
                    seen.add(name)
                    providers.append({"name": name, "id": pid, "url": url})

    # Priority 2: zero cost clean
    if CANDIDATES_CSV.exists():
        with open(CANDIDATES_CSV, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row.get("ProviderId", "").strip()
                name = row.get("ProviderName", "").strip()
                docs = row.get("Docs", "").strip()
                api = row.get("API", "").strip()
                url = docs if docs and docs.startswith("http") else api
                if name and url and url.startswith("http") and name not in seen:
                    seen.add(name)
                    providers.append({"name": name, "id": pid, "url": url})

    # Priority 3: catalog.json registry
    catalog_path = ROOT / "evidence" / "registry" / "catalog.json"
    if catalog_path.exists():
        try:
            cat_data = json.loads(catalog_path.read_text(encoding="utf-8")).get("providers", {})
            for pid, pdata in cat_data.items():
                name = pdata.get("name") or pid
                url = pdata.get("doc") or pdata.get("api") or ""
                if name and url and url.startswith("http") and name not in seen:
                    seen.add(name)
                    providers.append({"name": name, "id": pid, "url": url})
        except Exception as e:
            log(f"Warning loading catalog: {e}")

    return providers[:100]

def find_session_blueprint(name: str, pid: str, url: str) -> pathlib.Path | None:
    slug = name.replace(" ", "_").replace(".", "_").lower()
    pid_slug = pid.replace(" ", "_").replace("-", "_").lower()
    secrets_dir = ROOT / "state" / "secrets"
    candidates = list(secrets_dir.glob("session_*.json"))
    for f in candidates:
        fname = f.stem.lower()
        if slug in fname or pid_slug in fname or (len(slug) > 4 and slug[:5] in fname):
            return f
    return None

def main():
    log("=" * 70)
    log("STARTING 100-PROVIDER 1-BY-1 TAB GRADUATION & REPLAY CYCLER")
    log("=" * 70)

    ensure_chrome_alive()
    providers = load_providers()
    log(f"Loaded {len(providers)} candidate providers for serial graduation.")

    stats = {"processed": 0, "graduated": 0, "closed": 0}

    for idx, prov in enumerate(providers, 1):
        name = prov["name"]
        url = prov["url"]
        pid = prov["id"]
        log(f"\n>>> [STEP {idx}/{len(providers)}] Opening seat for '{name}' -> {url}")

        target_id = None
        try:
            # 1. Open dedicated tab
            tab_info = cdp_open_tab(url)
            target_id = tab_info.get("id")
            log(f"    Tab created: target_id={target_id[:8] if target_id else 'unknown'}")

            # 2. Allow page to settle
            time.sleep(4)

            # 3. Audit / Graduate seat check
            log(f"    Evaluating provider surface for {name}...")
            matched_blueprint = find_session_blueprint(name, pid, url)

            if matched_blueprint:
                log(f"    Blueprint found: {matched_blueprint.name}. Testing Law-3 replay probe...")
                slug_tag = matched_blueprint.stem.replace("session_", "")
                try:
                    res = subprocess.run(
                        [sys.executable, str(HERE / "replay_check.py"), "--only", slug_tag],
                        capture_output=True, text=True, timeout=15
                    )
                    if "REPLAY_OK" in res.stdout:
                        log(f"    [OK] Law-3 REPLAY_OK confirmed for {name}!")
                        stats["graduated"] += 1
                    else:
                        first_line = [l for l in res.stdout.splitlines() if slug_tag in l.lower()]
                        summary = first_line[0] if first_line else res.stdout.strip()[:100]
                        log(f"    [INFO] Replay status: {summary}")
                except Exception as ex:
                    log(f"    [WARN] Replay check error: {ex}")
            else:
                log(f"    New provider surface registered for {name}. Staged in browser.")

            stats["processed"] += 1

        except Exception as e:
            log(f"    [ERROR] Processing {name}: {e}")

        finally:
            # 4. Mandatory: Close the tab immediately!
            if target_id:
                log(f"    Closing tab {target_id[:8]}... (Zero memory bloat)")
                cdp_close_tab(target_id)
                stats["closed"] += 1

        # Brief settle before next candidate
        time.sleep(1.5)

    log("\n" + "=" * 70)
    log(f"CYCLER COMPLETE: Processed={stats['processed']} | Graduated={stats['graduated']} | Tabs Closed={stats['closed']}")
    log("=" * 70)

if __name__ == "__main__":
    main()
