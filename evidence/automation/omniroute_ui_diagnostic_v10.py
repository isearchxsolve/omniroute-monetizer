#!/usr/bin/env python3
"""OmniRoute UI Diagnostic v10 — NON-DESTRUCTIVE, evidence-first.

Captures screenshots, DOM metadata, provider API inventory/tests, and targeted
provider detail evidence. It does not mutate provider configuration.
"""
from __future__ import annotations
import json, os, re, time
from pathlib import Path
from typing import Any
import requests
from playwright.sync_api import sync_playwright, Page

# Management API lives at the dashboard origin (/api/...), NOT under /v1.
# /v1 is the OpenAI-compatible inference surface only.
# If OMNIROUTE_BASE_URL was set for a coding tool (…/v1), strip that suffix.
_raw_base = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if _raw_base.endswith("/v1"):
    _raw_base = _raw_base[:-3].rstrip("/")
BASE_URL = _raw_base or "http://localhost:20128"
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "")
OUT = Path(os.environ.get("OMNIROUTE_DIAG_DIR", "omniroute_ui_diagnostic"))
OUT.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    print(msg, flush=True)


def redact_obj(obj: Any):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(s in kl for s in ("password", "api_key", "apikey", "token", "secret", "cookie", "authorization")):
                out[k] = "<REDACTED>"
            else:
                out[k] = redact_obj(v)
        return out
    if isinstance(obj, list):
        return [redact_obj(x) for x in obj]
    return obj


def safe_json(resp: requests.Response):
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text[:4000]}


def api_login():
    """Dashboard management auth. Official path: POST /api/auth/login (NOT under /v1)."""
    s = requests.Session()
    url = f"{BASE_URL}/api/auth/login"
    log(f"  [auth] POST {url}")
    r = s.post(url, json={"password": PASSWORD}, timeout=15)
    log(f"  [auth] -> HTTP {r.status_code}")
    if r.status_code == 404:
        raise RuntimeError(
            f"404 at {url}. Management routes are /api/* on the dashboard origin, "
            f"not under /v1. Resolved BASE_URL={BASE_URL!r}."
        )
    r.raise_for_status()
    token = r.cookies.get("auth_token") or s.cookies.get("auth_token")
    if not token:
        try:
            body = r.json()
            token = body.get("token") or body.get("auth_token") or body.get("access_token")
        except Exception:
            body = {"raw": r.text[:500]}
        if not token:
            raise RuntimeError(f"Login OK-ish but no auth_token. Body={body!r}")
        s.cookies.set("auth_token", token)
    else:
        s.cookies.set("auth_token", token)
    log("  [auth] login OK")
    return s


def save_json(name: str, obj: Any):
    (OUT / name).write_text(json.dumps(redact_obj(obj), indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"  [save] {name}")


def save_text(name: str, text: str):
    (OUT / name).write_text(text, encoding="utf-8")
    log(f"  [save] {name}")


def screenshot(page: Page, name: str):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    log(f"  [shot] {path.name}")


def page_meta(page: Page) -> dict[str, Any]:
    return page.evaluate("""() => ({
      url: location.href,
      title: document.title,
      bodyText: document.body ? document.body.innerText.slice(0,30000) : '',
      htmlLength: document.documentElement ? document.documentElement.outerHTML.length : 0,
      links: Array.from(document.querySelectorAll('a[href]')).map(a => ({text:(a.innerText||'').trim(), href:a.href})).filter(x=>x.text||x.href).slice(0,500),
      buttons: Array.from(document.querySelectorAll('button,[role=button]')).map(b => ({text:(b.innerText||'').trim(), aria:b.getAttribute('aria-label')||'', title:b.getAttribute('title')||'', disabled:!!b.disabled, tag:b.tagName, cls:typeof b.className==='string'?b.className.slice(0,180):''})).filter(x=>x.text||x.aria||x.title).slice(0,500),
      inputs: Array.from(document.querySelectorAll('input,textarea,select')).map(e => ({tag:e.tagName, type:e.getAttribute('type')||'', name:e.getAttribute('name')||'', id:e.id||'', placeholder:e.getAttribute('placeholder')||'', aria:e.getAttribute('aria-label')||'', cls:typeof e.className==='string'?e.className.slice(0,180):''})).slice(0,400)
    })""")


def provider_rows(page: Page):
    return page.evaluate("""() => {
      const out=[]; const seen=new Set();
      const sels=['tr','[data-provider]','[data-testid*="provider" i]','[class*="provider" i]','[class*="connection" i]','[class*="card" i]','[class*="row" i]','[class*="item" i]'];
      for(const sel of sels){
        for(const el of document.querySelectorAll(sel)){
          const r=el.getBoundingClientRect(); if(!r.width||!r.height) continue;
          const text=(el.innerText||el.textContent||'').trim().replace(/\\s+/g,' '); if(!text||text.length>1000) continue;
          const key=text.slice(0,250); if(seen.has(key)) continue; seen.add(key);
          out.push({selector:sel,tag:el.tagName,text:text.slice(0,1000),cls:typeof el.className==='string'?el.className.slice(0,220):'',attrs:Array.from(el.attributes).reduce((a,x)=>(a[x.name]=x.value,a),{}),buttons:Array.from(el.querySelectorAll('button,[role=button]')).map(b=>({text:(b.innerText||'').trim(),aria:b.getAttribute('aria-label')||'',title:b.getAttribute('title')||'',disabled:!!b.disabled})).slice(0,50),links:Array.from(el.querySelectorAll('a[href]')).map(a=>({text:(a.innerText||'').trim(),href:a.href})).slice(0,50),inputs:Array.from(el.querySelectorAll('input,textarea,select')).map(i=>({type:i.getAttribute('type')||'',name:i.getAttribute('name')||'',id:i.id||'',placeholder:i.getAttribute('placeholder')||'',aria:i.getAttribute('aria-label')||''})).slice(0,50)});
        }
      }
      return out.slice(0,500);
    }""")


def click_targeted_provider(page: Page, name: str):
    # First inspect all visible text matches and surrounding clickable ancestors.
    info = page.evaluate("""(name) => {
      const els = Array.from(document.querySelectorAll('*')).filter(e => {
        const t=(e.innerText||e.textContent||'').trim().replace(/\\s+/g,' ');
        const r=e.getBoundingClientRect();
        return r.width && r.height && t && t.toLowerCase().includes(name.toLowerCase()) && t.length < 400;
      });
      return els.slice(0,40).map(e => ({tag:e.tagName,text:(e.innerText||e.textContent||'').trim().slice(0,400),cls:typeof e.className==='string'?e.className.slice(0,180):'',id:e.id||'',data:Array.from(e.attributes).filter(a=>a.name.startsWith('data-')).reduce((o,a)=>(o[a.name]=a.value,o),{}),buttons:Array.from(e.querySelectorAll('button,[role=button]')).map(b=>({text:(b.innerText||'').trim(),aria:b.getAttribute('aria-label')||'',title:b.getAttribute('title')||''})).slice(0,20)}));
    }""", name)
    return info


def main():
    if not PASSWORD:
        raise SystemExit("OMNIROUTE_PASSWORD is not set")
    log("=" * 72)
    log("OmniRoute UI Diagnostic v10 — NON-DESTRUCTIVE")
    log("Evidence first: screenshots + DOM + API. No provider mutation.")
    log(f"BASE_URL={BASE_URL}  (management API is /api/*, inference is /v1/*)")
    log("=" * 72)

    api = api_login()
    providers_resp = api.get(f"{BASE_URL}/api/providers", timeout=15)
    providers = safe_json(providers_resp)
    save_json("api_providers.json", providers)
    connections = providers.get("connections", []) if isinstance(providers, dict) else []
    log(f"[API] /api/providers -> HTTP {providers_resp.status_code}, connections={len(connections)}")

    tests=[]
    for c in connections:
        cid=c.get('id'); name=c.get('provider')
        if not cid: continue
        try:
            r=api.post(f"{BASE_URL}/api/providers/{cid}/test", timeout=30)
            tests.append({"provider":name,"id":cid,"http_status":r.status_code,"result":safe_json(r)})
        except Exception as e:
            tests.append({"provider":name,"id":cid,"exception":f"{type(e).__name__}: {e}"})
    save_json("api_provider_tests.json", tests)

    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=False, slow_mo=150)
        context=browser.new_context(viewport={"width":1600,"height":1000})
        page=context.new_page()
        network=[]
        def on_response(resp):
            if "/api/" in resp.url:
                network.append({"status":resp.status,"url":resp.url,"method":resp.request.method})
        page.on("response", on_response)

        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1200)
        screenshot(page,"00_initial")
        save_json("00_initial.json", page_meta(page))

        pwd=page.locator('input[type="password"]').first
        if pwd.count() and pwd.is_visible():
            pwd.fill(PASSWORD); pwd.press("Enter"); page.wait_for_timeout(3000)
        screenshot(page,"01_after_login")
        save_json("01_after_login.json", page_meta(page))

        for idx,path in enumerate(["providers","discovery","combos"],start=2):
            url=f"{BASE_URL}/dashboard/{path}"
            try:
                page.goto(url,wait_until="domcontentloaded",timeout=20000)
                page.wait_for_timeout(1500)
                screenshot(page,f"0{idx}_{path}")
                save_json(f"0{idx}_{path}.json",page_meta(page))
                if path=="providers":
                    save_json("02_provider_rows.json",provider_rows(page))
            except Exception as e:
                save_text(f"0{idx}_{path}_ERROR.txt",f"{type(e).__name__}: {e}")

        # For every live API connection, capture UI evidence if its name appears.
        for idx,c in enumerate(connections, start=1):
            name=str(c.get('provider') or '')
            if not name: continue
            try:
                page.goto(f"{BASE_URL}/dashboard/providers",wait_until="domcontentloaded",timeout=20000)
                page.wait_for_timeout(900)
                matches=click_targeted_provider(page,name)
                save_json(f"provider_{idx:02d}_{name}_matches.json",matches)
                loc=page.get_by_text(name,exact=True)
                if not loc.count(): loc=page.get_by_text(name,exact=False)
                if loc.count() and loc.first.is_visible():
                    loc.first.scroll_into_view_if_needed(); page.wait_for_timeout(300)
                    screenshot(page,f"provider_{idx:02d}_{name}_list")
                    try:
                        loc.first.click(timeout=3000)
                        page.wait_for_timeout(1200)
                        screenshot(page,f"provider_{idx:02d}_{name}_detail")
                        save_json(f"provider_{idx:02d}_{name}_detail.json",page_meta(page))
                    except Exception as e:
                        save_text(f"provider_{idx:02d}_{name}_click_ERROR.txt",f"{type(e).__name__}: {e}")
                else:
                    screenshot(page,f"provider_{idx:02d}_{name}_NOT_FOUND")
            except Exception as e:
                save_text(f"provider_{idx:02d}_{name}_ERROR.txt",f"{type(e).__name__}: {e}")

        save_json("network_api_requests.json",network)
        save_text("README.txt","NON-DESTRUCTIVE bundle. Review 02_providers.png, 02_provider_rows.json, provider_*_detail.png/json, api_providers.json and api_provider_tests.json before any mutation.")
        context.close(); browser.close()

    log("="*72)
    log(f"Diagnostic bundle: {OUT.resolve()}")
    log("Upload the entire folder. No provider state was changed.")
    log("="*72)

if __name__=="__main__":
    main()
