"""Fix the deepseek class-(a) tab-state gap (worklog #1120 §3).

The deepseek tab on :9222 is parked on an old conversation page
(/a/chat/s/<uuid>) whose composer the generic bridge can't find -> NO_INPUT.
Navigate that tab to a fresh chat (/) so the composer is present, then
re-verify through the same ChromeReplayClient dispatch path the pool uses.

Doctrine: this is a class-(a) fixable tab-state gap, NOT a provider death.
We only reposition automation's OWN tab; we never touch the operator's Chrome.
"""
import json
import pathlib
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CDP = "http://127.0.0.1:9222"
SEAT = pathlib.Path(__file__).parent / "state" / "secrets" / "session_deepseek_chat.json"


def cdp_json(path):
    req = urllib.request.Request(CDP + path)
    return json.loads(urllib.request.urlopen(req, timeout=8).read())


def main():
    # 1. Find the deepseek tab.
    tabs = cdp_json("/json")
    target = None
    for t in tabs:
        if t.get("type") == "page" and "deepseek" in (t.get("url") or "").lower():
            target = t
            break
    if not target:
        print("NO deepseek tab on :9222 — nothing to fix")
        return 1
    print(f"BEFORE: {target.get('url')}")

    # 2. Navigate it to a fresh chat via Selenium (attach by debuggerAddress).
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    opts = Options()
    opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=opts)
    try:
        # Switch to the deepseek tab handle.
        for h in driver.window_handles:
            try:
                driver.switch_to.window(h)
                if "deepseek" in (driver.current_url or "").lower():
                    break
            except Exception:
                continue
        driver.get("https://chat.deepseek.com/")
        time.sleep(6)  # let the fresh-chat composer mount
        print(f"AFTER:  {driver.current_url}")
    finally:
        # NEVER quit() a debugger-attached driver — that closes the seat Chrome.
        # Just drop the handle; the browser keeps running.
        pass

    # 3. Re-verify through the pool's dispatch path.
    sys.path.insert(0, str(pathlib.Path(__file__).parent / "scripts" / "automation"))
    from chrome_replay_client import ChromeReplayClient
    c = ChromeReplayClient(secret=SEAT)
    try:
        r = c.chat([{"role": "user", "content": "Reply exactly one word: Omni."}])
        print(f"VERIFY OK  label={r.get('label')} text={repr((r.get('text') or '')[:80])}")
        return 0
    except Exception as e:
        print(f"VERIFY ERR {type(e).__name__}: {str(e)[:160]}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
