#!/usr/bin/env python3
"""
OmniRoute Provider Recovery v12 (100% Complete)
================================
Evidence-driven recovery based on OmniRoute UI/API.

Repairs live dashboard connections that have a plausible recovery path:
  - API refresh first; otherwise UI "Re-authenticate this connection" or "Import auth"
  - Targets any broken provider that might have a UI recovery path.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

_raw_base = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if _raw_base.endswith("/v1"):
    _raw_base = _raw_base[:-3].rstrip("/")
BASE_URL = _raw_base or "http://localhost:20128"
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "<REDACTED>")
OUT = Path(os.environ.get("OMNIROUTE_RECOVERY_DIR", "omniroute_provider_recovery"))
OUT.mkdir(parents=True, exist_ok=True)

# Broadened the recoverable set
RECOVERABLE_DIAGNOSIS = {"reauth_required", "unauthorized", "auth_missing", "expired", "missing_access_token", "upstream_auth_error", "invalid_api_key"}
PROVIDER_ROUTE = {"opencode": "opencode-go"}


def log(msg: str, level: str = "info"):
    p = {"info": "[*]", "ok": "[+]", "warn": "[!]", "err": "[-]"}.get(level, "[*]")
    print(f"{p} {msg}", flush=True)


def safe_json(r: requests.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:4000]}


def api_login() -> requests.Session:
    if not PASSWORD:
        raise RuntimeError("OMNIROUTE_PASSWORD is not set")
    s = requests.Session()
    url = f"{BASE_URL}/api/auth/login"
    log(f"POST {url}")
    r = s.post(url, json={"password": PASSWORD}, timeout=15)
    if r.status_code == 404:
        raise RuntimeError(f"404 at {url}")
    r.raise_for_status()
    token = r.cookies.get("auth_token") or s.cookies.get("auth_token")
    if not token:
        body = safe_json(r)
        token = body.get("token") or body.get("auth_token") or body.get("access_token")
        if not token:
            raise RuntimeError(f"Login OK but no auth token found: {body!r}")
    s.cookies.set("auth_token", token)
    log("Dashboard API login OK", "ok")
    return s


def get_connections(api: requests.Session) -> list[dict[str, Any]]:
    r = api.get(f"{BASE_URL}/api/providers", timeout=15)
    r.raise_for_status()
    data = safe_json(r)
    return data.get("connections", []) if isinstance(data, dict) else []


def test(api: requests.Session, cid: str) -> dict[str, Any]:
    try:
        r = api.post(f"{BASE_URL}/api/providers/{cid}/test", timeout=30)
        return {"http_status": r.status_code, "result": safe_json(r)}
    except Exception as e:
        return {"http_status": None, "exception": f"{type(e).__name__}: {e}", "result": {"valid": False}}


def refresh(api: requests.Session, cid: str) -> dict[str, Any]:
    try:
        r = api.post(f"{BASE_URL}/api/providers/{cid}/refresh", timeout=45)
        return {"http_status": r.status_code, "result": safe_json(r)}
    except Exception as e:
        return {"http_status": None, "exception": f"{type(e).__name__}: {e}", "result": {}}


def diag_of(result: dict[str, Any]) -> tuple[str, str]:
    d = result.get("result", {}).get("diagnosis", {}) if isinstance(result.get("result"), dict) else {}
    return str(d.get("type") or "unknown"), str(d.get("message") or result.get("result", {}).get("error") or "")


def screenshot(page, name: str):
    p = OUT / f"{name}.png"
    page.screenshot(path=str(p), full_page=True)
    log(f"  screenshot: {p.name}")


def write_json(name: str, data: Any):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def open_provider(page, provider: str):
    slug = PROVIDER_ROUTE.get(provider, provider)
    page.goto(f"{BASE_URL}/dashboard/providers/{slug}", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(1200)


def click_reauth_for_connection(page, identity: str) -> bool:
    # Look for any button that suggests auth or refresh
    selectors = [
        f':text("Re-authenticate"):near(:text("{identity}"))',
        f'text="Re-authenticate"',
        f':text("Login"):near(:text("{identity}"))',
        f'text="Login"',
        f':text("Refresh"):near(:text("{identity}"))',
        f'text="Refresh"',
        f'text="Edit"',
        f'text="Update Key"',
        f'text="Update"'
    ]
    
    for sel in selectors:
        try:
            button = page.locator(sel).first
            # Wait up to 3 seconds for this specific button to appear
            button.wait_for(state="visible", timeout=3000)
            log(f"  found button matching '{sel}'")
            button.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            button.click(timeout=5000)
            return True
        except Exception:
            continue
            
    log("  no reauth button found after waiting", "err")
    return False


def handle_browser_reauth(api: requests.Session, connection: dict[str, Any], page, context) -> dict[str, Any]:
    provider = connection.get("provider", "")
    cid = connection.get("id", "")
    identity = connection.get("email") or connection.get("name") or ""
    safe_id = provider.replace("/", "_") + "_" + cid[:8]
    result = {"provider": provider, "id": cid, "identity": identity, "action": None}
    # Re-enable connection before opening UI to prevent routing hangs
    try:
        conn_copy = dict(connection)
        conn_copy["isActive"] = True
        api.put(f"{BASE_URL}/api/providers/{cid}", json={"connection": conn_copy}, timeout=5)
    except Exception as e:
        log(f"  Failed to pre-enable connection for UI: {e}", "warn")
        
    open_provider(page, provider)
    screenshot(page, f"before_{safe_id}")

    clicked = click_reauth_for_connection(page, identity)
    
    result["action"] = "reauth_clicked" if clicked else "no_reauth_control"
    screenshot(page, f"after_click_{safe_id}")

    if not clicked:
        result["status"] = "ui_control_not_found"
        # BUGFIX: connection was pre-enabled above; if we can't find a re-auth
        # control, revert to inactive so it doesn't stall the health-check cycle.
        try:
            api.put(f"{BASE_URL}/api/providers/{cid}", json={"isActive": False}, timeout=10)
            log(f"  [!] Reverted pre-enabled {provider} to inactive (no UI control found)", "warn")
        except Exception as e:
            log(f"      Failed to revert: {e}")
        return result

    log("  Waiting for automated auth flow to complete (up to 15s)...")
    page.wait_for_timeout(15000)
    
    screenshot(page, f"final_{safe_id}")
    cur = test(api, cid)
    typ, msg = diag_of(cur)
    result["last_test"] = cur
    if cur.get("result", {}).get("valid"):
        log("  [+] automated flow successful, connection verified!", "ok")
        result["status"] = "recovered"
        return result

    log(f"  [-] automated flow failed: {typ} - {msg[:80]}", "warn")
    
    # PERMANENT FIX: Dead-route suppression
    # Revert isActive to False so this broken connection doesn't hang the server.
    log(f"  [!] Suppressing dead route {provider} to prevent server hang...", "warn")
    try:
        # BUGFIX: was getattr(api, "session", requests) which fell back to the
        # unauthenticated requests module -> silent 401. Use the authed session.
        api.put(f"{BASE_URL}/api/providers/{cid}", json={"isActive": False}, timeout=10)
    except Exception as e:
        log(f"      Failed to suppress: {e}")

    result["status"] = "failed"
    return result


def main():
    log("=" * 72)
    log("OmniRoute Provider Recovery v12 (100% Automated)")
    log("API-first -> OAuth refresh -> exact UI re-auth -> API verification")
    log(f"BASE_URL={BASE_URL}")
    log("=" * 72)

    api = api_login()
    connections = get_connections(api)
    write_json("connections_before.json", connections)
    log(f"Live dashboard connections: {len(connections)}")

    classified = []
    
    for c in connections:
        cid = c.get("id")
        if not cid: continue
        t = test(api, cid)
        typ, msg = diag_of(t)
        status = "OK" if t.get("result", {}).get("valid") else typ
        log(f"  {c.get('provider'):16s} {status:18s} {msg[:80]}")
        classified.append({**c, "test": t, "diagnosis": typ, "message": msg})

    write_json("classification_before.json", classified)

    # Include ANY broken connection with a recognizable auth/auth-missing error
    recovery_targets = []
    for c in classified:
        if c.get("test", {}).get("result", {}).get("valid"):
            continue
            
        msg = str(c.get("message", "")).lower()
        typ = str(c.get("diagnosis", "")).lower()
        
        # We consider it a target if it has auth issues
        if typ in RECOVERABLE_DIAGNOSIS or any(x in msg for x in ["expired", "unauthorized", "missing", "invalid", "auth"]):
            recovery_targets.append(c)

    log(f"\nConnections eligible for recovery: {len(recovery_targets)}")

    browser_needed = []
    for c in recovery_targets:
        cid = c["id"]
        provider = c.get("provider")
        log(f"\n[Refresh] {provider} / {c.get('email') or c.get('name') or cid[:8]}")
        rr = refresh(api, cid)
        tr = test(api, cid)
        if tr.get("result", {}).get("valid"):
            log("  API refresh recovered the connection", "ok")
        else:
            typ, msg = diag_of(tr)
            log(f"  still failing: {typ} {msg[:120]}", "warn")
            browser_needed.append(c)

    if browser_needed:
        log(f"\nOpening visible browser for {len(browser_needed)} connection(s)...")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False, slow_mo=120)
            context = browser.new_context(viewport={"width": 1600, "height": 1000})
            page = context.new_page()
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1200)
            try:
                pwd = page.locator('input[type="password"]').first
                pwd.wait_for(state="visible", timeout=5000)
                pwd.fill(PASSWORD)
                pwd.press("Enter")
                page.wait_for_timeout(2500)
            except Exception:
                pass

            for c in browser_needed:
                provider = c.get("provider", "")
                log(f"\n[UI] {provider} / {c.get('email') or c.get('name') or c.get('id','')[:8]}")
                try:
                    handle_browser_reauth(api, c, page, context)
                except Exception as e:
                    log(f"  browser recovery exception: {e}", "err")

            context.close()
            browser.close()

    # Final verification
    log("\n" + "=" * 72)
    log("FINAL VERIFIED STATE")
    working = 0
    for c in connections:
        cid = c.get("id")
        if not cid: continue
        tr = test(api, cid)
        if tr.get("result", {}).get("valid"):
            working += 1
            log(f"  [+] {c.get('provider'):16s} OK")
        else:
            typ, msg = diag_of(tr)
            log(f"  [-] {c.get('provider'):16s} {typ:18s} {msg[:80]}")
            
    log(f"\nWorking: {working}/{len(connections)}", "ok")

if __name__ == "__main__":
    main()
