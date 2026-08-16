#!/usr/bin/env python3
"""
OmniRoute Provider Recovery v11
================================
Evidence-driven recovery based on OmniRoute v3.8.49 UI/API observed in the
user's diagnostic bundle.

This is intentionally NOT a catalog/model optimizer.
It repairs only live dashboard connections that have a plausible recovery path:
  - OAuth: API refresh first; otherwise UI "Re-authenticate this connection"
  - API-key/base-url providers: no invented credentials; report missing creds
  - known upstream/runtime failures: report and do not hammer

Authoritative success criterion: POST /api/providers/{id}/test -> valid=True.
The browser is an interaction mechanism, never the final judge.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Management API is /api/* on the dashboard origin. /v1 is inference only.
# Strip a trailing /v1 if OMNIROUTE_BASE_URL was set for a coding tool.
_raw_base = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if _raw_base.endswith("/v1"):
    _raw_base = _raw_base[:-3].rstrip("/")
BASE_URL = _raw_base or "http://localhost:20128"
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "")
OUT = Path(os.environ.get("OMNIROUTE_RECOVERY_DIR", "omniroute_provider_recovery"))
OUT.mkdir(parents=True, exist_ok=True)

OAUTH_RECOVERABLE = {"reauth_required", "unauthorized", "auth_missing", "expired", "missing_access_token"}
# Observed dashboard route aliases from the captured UI bundle.
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
        raise RuntimeError(
            f"404 at {url}. Management routes are /api/* (not under /v1). "
            f"Resolved BASE_URL={BASE_URL!r}."
        )
    r.raise_for_status()
    token = r.cookies.get("auth_token") or s.cookies.get("auth_token")
    if not token:
        body = safe_json(r)
        token = body.get("token") or body.get("auth_token") or body.get("access_token")
        if not token:
            raise RuntimeError(f"Dashboard login succeeded but no auth token found: {body!r}")
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
        d = safe_json(r)
        return {"http_status": r.status_code, "result": d}
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
    """Target the re-auth button inside the connection row for this identity."""
    buttons = page.locator('button[title="Re-authenticate this connection"]')
    n = buttons.count()
    log(f"  found {n} re-auth button(s)")
    if n == 0:
        return False

    wanted = identity.lower().strip()
    candidates = []
    for i in range(n):
        try:
            b = buttons.nth(i)
            text = b.evaluate("""b => {
              let e=b;
              for(let j=0;j<8 && e;j++,e=e.parentElement){
                const t=(e.innerText||'').trim().replace(/\\s+/g,' ');
                if(t.length>0 && t.length<1000 && /account|connection|re-auth|token/i.test(t)) return t;
              }
              return '';
            }""") or ""
            if wanted and wanted in text.lower():
                candidates.append(i)
        except Exception:
            pass

    if not candidates:
        if n != 1:
            log("  re-auth controls exist, but none matched the target connection identity; refusing to guess", "warn")
            return False
        idx = 0
    else:
        idx = candidates[0]
    b = buttons.nth(idx)
    b.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    log(f"  clicking Re-authenticate this connection (button {idx + 1}/{n})")
    try:
        b.click(timeout=5000)
        return True
    except Exception as e:
        log(f"  re-auth click failed: {type(e).__name__}: {e}", "err")
        return False


def handle_browser_reauth(api: requests.Session, connection: dict[str, Any], page, context) -> dict[str, Any]:
    provider = connection.get("provider", "")
    cid = connection.get("id", "")
    identity = connection.get("email") or connection.get("name") or ""
    safe_id = provider.replace("/", "_") + "_" + cid[:8]
    result = {"provider": provider, "id": cid, "identity": identity, "action": None}

    open_provider(page, provider)
    screenshot(page, f"before_{safe_id}")

    clicked = click_reauth_for_connection(page, identity)
    if not clicked:
        # Codex exposes a second explicit import/auth workflow; prefer it if available.
        import_btn = page.locator('button[title="Import auth"], button:has-text("Import auth")')
        if import_btn.count() and import_btn.first.is_visible():
            log("  no re-auth button matched; using Import auth")
            try:
                import_btn.first.click(timeout=5000)
                clicked = True
            except Exception:
                clicked = False

    result["action"] = "reauth_clicked" if clicked else "no_reauth_control"
    screenshot(page, f"after_click_{safe_id}")

    if not clicked:
        result["status"] = "ui_control_not_found"
        return result

    # Give OAuth callback/consent time to complete. We keep the visible browser open.
    deadline = time.time() + 90
    last_type = None
    while time.time() < deadline:
        page.wait_for_timeout(3000)
        cur = test(api, cid)
        typ, msg = diag_of(cur)
        result["last_test"] = cur
        if cur.get("result", {}).get("valid") is True:
            result["status"] = "recovered"
            screenshot(page, f"recovered_{safe_id}")
            return result
        if typ != last_type:
            log(f"  verification: {typ} {msg[:100]}")
            last_type = typ
        # Reauth may have opened an auth popup/tab. Keep it alive and visible.
        for p in context.pages:
            try:
                if p is not page and not p.is_closed():
                    log(f"  auth window: {p.url}")
            except Exception:
                pass

    result["status"] = "not_recovered_after_90s"
    screenshot(page, f"timeout_{safe_id}")
    return result


def main():
    log("=" * 72)
    log("OmniRoute Provider Recovery v11")
    log("API-first -> OAuth refresh -> exact UI re-auth -> API verification")
    log(f"BASE_URL={BASE_URL}")
    log("=" * 72)

    api = api_login()
    connections = get_connections(api)
    write_json("connections_before.json", connections)
    log(f"Live dashboard connections: {len(connections)}")

    # First classify every current connection from the authoritative API.
    classified = []
    for c in connections:
        cid = c.get("id")
        if not cid:
            continue
        t = test(api, cid)
        typ, msg = diag_of(t)
        classified.append({**c, "test": t, "diagnosis": typ, "message": msg})
        status = "OK" if t.get("result", {}).get("valid") else typ
        log(f"  {c.get('provider'):16s} {status:18s} {msg[:80]}")

    write_json("classification_before.json", classified)

    # Recoverable OAuth connections. De-duplicate by connection ID; duplicate provider names matter.
    oauth_targets = [
        c for c in classified
        if str(c.get("authType", "")).lower() == "oauth"
        and not c.get("test", {}).get("result", {}).get("valid")
        and (c.get("diagnosis") in OAUTH_RECOVERABLE or "expired" in str(c.get("message", "")).lower())
    ]

    # Known non-repairable-at-this-layer cases: do not hammer upstream or invent credentials.
    manual = []
    for c in classified:
        msg = str(c.get("message", "")).lower()
        typ = str(c.get("diagnosis", "")).lower()
        if "402" in msg or typ == "upstream_error" and "402" in msg:
            manual.append({"provider": c.get("provider"), "id": c.get("id"), "reason": "upstream_402"})
        if "local cli runtime is not installed" in msg:
            manual.append({"provider": c.get("provider"), "id": c.get("id"), "reason": "missing_local_cli_runtime"})
        if "missing api key" in msg or "invalid api key" in msg or typ in {"auth_missing", "upstream_auth_error"}:
            # OAuth missing-access-token remains recoverable; API-key auth does not.
            if str(c.get("authType", "")).lower() != "oauth":
                manual.append({"provider": c.get("provider"), "id": c.get("id"), "reason": "credentials_not_available_to_tool"})

    log(f"OAuth connections eligible for recovery: {len(oauth_targets)}")
    log(f"Non-UI/manual cases: {len(manual)}")
    write_json("manual_cases.json", manual)

    refresh_results = []
    browser_needed = []
    for c in oauth_targets:
        cid = c["id"]
        provider = c.get("provider")
        log(f"\n[OAuth] {provider} / {c.get('email') or c.get('name') or cid[:8]}")
        rr = refresh(api, cid)
        refresh_results.append({"provider": provider, "id": cid, "refresh": rr})
        tr = test(api, cid)
        refresh_results[-1]["after_refresh_test"] = tr
        if tr.get("result", {}).get("valid"):
            log("  API refresh recovered the connection", "ok")
        else:
            typ, msg = diag_of(tr)
            log(f"  still failing: {typ} {msg[:120]}", "warn")
            browser_needed.append(c)

    write_json("refresh_results.json", refresh_results)

    browser_results = []
    if browser_needed:
        log(f"\nOpening visible browser for {len(browser_needed)} OAuth connection(s)...")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False, slow_mo=120)
            context = browser.new_context(viewport={"width": 1600, "height": 1000})
            page = context.new_page()
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(1200)
            pwd = page.locator('input[type="password"]').first
            if pwd.count() and pwd.is_visible():
                if not PASSWORD:
                    raise RuntimeError("OMNIROUTE_PASSWORD is not set")
                pwd.fill(PASSWORD)
                pwd.press("Enter")
                page.wait_for_timeout(2500)
            screenshot(page, "00_recovery_home")
            # Post-login destinations: /home, /dashboard, /dashboard/*. Failure = still on password field.
            still_login = False
            try:
                pwd_el = page.locator('input[type="password"]').first
                still_login = pwd_el.count() > 0 and pwd_el.is_visible()
            except Exception:
                still_login = False
            path = page.url.replace(BASE_URL, "") or "/"
            body_text = (page.locator("body").inner_text() or "").lower()
            logged_in = (
                path.startswith("/home")
                or path.startswith("/dashboard")
                or ("providers" in body_text)
                or not still_login
            )
            if not logged_in:
                raise RuntimeError(f"Browser login did not reach the dashboard: {page.url}")
            log(f"Browser login OK -> {page.url}", "ok")

            for c in browser_needed:
                provider = c.get("provider", "")
                log(f"\n[UI] {provider} / {c.get('email') or c.get('name') or c.get('id','')[:8]}")
                try:
                    browser_results.append(handle_browser_reauth(api, c, page, context))
                except Exception as e:
                    log(f"  browser recovery exception: {type(e).__name__}: {e}", "err")
                    browser_results.append({"provider": provider, "id": c.get("id"), "status": "exception", "error": str(e)})

            context.close()
            browser.close()

    write_json("browser_recovery_results.json", browser_results)

    # Final authoritative verification.
    final = []
    for c in connections:
        cid = c.get("id")
        if not cid:
            continue
        tr = test(api, cid)
        typ, msg = diag_of(tr)
        final.append({"provider": c.get("provider"), "id": cid, "authType": c.get("authType"), "valid": bool(tr.get("result", {}).get("valid")), "diagnosis": typ, "message": msg})

    write_json("final_verification.json", final)
    ok = [x for x in final if x["valid"]]
    bad = [x for x in final if not x["valid"]]

    log("\n" + "=" * 72)
    log("FINAL VERIFIED STATE")
    log(f"Working: {len(ok)}/{len(final)}", "ok")
    log(f"Still failing: {len(bad)}")
    for x in bad:
        log(f"  {x['provider']:16s} {x['diagnosis']:18s} {x['message'][:100]}")
    log(f"Evidence directory: {OUT.resolve()}")
    log("No provider is called fixed unless the OmniRoute API test says valid=True.")


if __name__ == "__main__":
    main()
