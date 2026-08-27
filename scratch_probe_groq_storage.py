# -*- coding: utf-8 -*-
"""Probe console.groq.com storage for the live bearer token (doctrine class-a fix).

Attach-only via debuggerAddress. NEVER calls driver.quit().
Prints candidate token locations; redacts token values to first 25 chars.
"""
import json
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PORT = "127.0.0.1:9222"


def redact(v):
    v = str(v)
    return v[:25] + "...(len=%d)" % len(v)


def main() -> int:
    opts = Options()
    opts.add_experimental_option("debuggerAddress", PORT)
    driver = webdriver.Chrome(options=opts)
    driver.set_script_timeout(30)
    print("attached, windows=%d" % len(driver.window_handles))

    # find or open a console.groq.com tab
    tab = None
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if "console.groq.com" in driver.current_url:
                tab = h
                break
        except Exception:
            continue
    if tab is None:
        driver.switch_to.new_window("tab")
        driver.get("https://console.groq.com/")
        time.sleep(5)
        print("opened new console tab")
    else:
        driver.execute_cdp_cmd("Page.bringToFront", {})
        print("reusing console tab: %s" % driver.current_url)

    probe_js = r"""
    const cb = arguments[arguments.length - 1];
    const out = {localStorage: {}, sessionStorage: {}, indexedDB: [], cookies: []};
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        const v = localStorage.getItem(k) || '';
        if (/token|jwt|auth|key|bearer|firebase|groq/i.test(k) || /eyJ[A-Za-z0-9_-]{10,}/.test(v)) {
          out.localStorage[k] = v.slice(0, 60) + '...(len=' + v.length + ')';
        }
      }
    } catch (e) { out.localStorageError = String(e); }
    try {
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        const v = sessionStorage.getItem(k) || '';
        if (/token|jwt|auth|key|bearer|firebase|groq/i.test(k) || /eyJ[A-Za-z0-9_-]{10,}/.test(v)) {
          out.sessionStorage[k] = v.slice(0, 60) + '...(len=' + v.length + ')';
        }
      }
    } catch (e) { out.sessionStorageError = String(e); }
    try {
      out.cookies = document.cookie.split(';').map(c => c.trim().split('=')[0]).filter(Boolean);
    } catch (e) {}
    // IndexedDB enumeration (async)
    try {
      if (window.indexedDB && indexedDB.databases) {
        indexedDB.databases().then(dbs => {
          out.indexedDB = dbs.map(d => d.name);
          cb(out);
        }).catch(e => { out.indexedDBError = String(e); cb(out); });
        return;
      }
    } catch (e) { out.indexedDBError = String(e); }
    cb(out);
    """
    result = driver.execute_async_script(probe_js)
    print(json.dumps(result, indent=2))
    print("DONE - do NOT quit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
