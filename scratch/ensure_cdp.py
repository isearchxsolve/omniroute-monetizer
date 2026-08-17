"""One-shot: ensure slim Chrome + CDP is up, then run raw-CDP discovery.
Writes status to scratch/launch_state.txt. Stdlib only."""
import json
import os
import subprocess
import time
import urllib.request

SCRATCH = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(SCRATCH, "launch_state.txt")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = r"d:\omniroute-chrome-profile"


def w(msg):
    try:
        with open(STATE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def cdp_up():
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5) as r:
            return json.loads(r.read()).get("Browser", "?")
    except Exception:
        return None


def main():
    if os.path.exists(STATE):
        os.remove(STATE)
    ver = cdp_up()
    if ver:
        w(f"CDP already up: {ver}")
        return
    w("CDP down -> launching slim Chrome")
    # mark prefs clean
    prefs = os.path.join(PROFILE, "Profile 14", "Preferences")
    try:
        with open(prefs, "r", encoding="utf-8-sig") as f:
            j = json.load(f)
        if "profile" in j:
            j["profile"]["exit_type"] = "Normal"
            j["profile"]["exited_cleanly"] = True
            with open(prefs, "w", encoding="utf-8") as f:
                json.dump(j, f)
        w("prefs marked clean")
    except Exception as e:
        w(f"prefs edit skipped: {e}")
    args = [
        CHROME,
        f"--user-data-dir={PROFILE}",
        "--profile-directory=Profile 14",
        "--remote-debugging-port=9222",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        "--restore-last-session=false",
        "about:blank",
    ]
    subprocess.Popen(args)
    w("chrome launched, waiting for CDP...")
    for i in range(30):
        time.sleep(2)
        ver = cdp_up()
        if ver:
            w(f"CDP up after ~{(i+1)*2}s: {ver}")
            return
    w("CDP still down after 60s")


if __name__ == "__main__":
    main()
