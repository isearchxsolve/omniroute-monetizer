#!/usr/bin/env python3
"""
OMNIROUTE CAPTURE REPLAY ENGINE (Phase 2)
Loads site-flow wire recipes from state/captures/, handles parameter substitution,
fresh dynamic field regeneration (PREFLIGHT), sentinel liveness probes,
and BoringSSL / JA3 Chrome impersonation via curl_cffi.
"""
import os
import re
import sys
import time
import json
import uuid
from pathlib import Path

CAPTURES_DIR = Path("C:/kaggle/working/state/captures")
if not CAPTURES_DIR.exists():
    CAPTURES_DIR = Path("D:/anonym/state/captures")

def do_request(method, url, headers=None, data=None, cookies=None, impersonate="chrome", timeout=25):
    headers = dict(headers or {})
    try:
        from curl_cffi import requests as c_requests
        return c_requests.request(
            method=method,
            url=url,
            headers=headers,
            data=data,
            cookies=cookies,
            impersonate=impersonate,
            timeout=timeout
        )
    except Exception:
        import urllib.request
        import urllib.error
        if cookies:
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            headers["Cookie"] = cookie_str
        req_data = data.encode("utf-8") if isinstance(data, str) else data
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            text = resp.read().decode("utf-8", "replace")
            status = resp.status
            resp_headers = dict(resp.headers)
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            status = e.code
            resp_headers = dict(e.headers)
        except Exception as e:
            text = str(e)
            status = 0
            resp_headers = {}

        class MockResp:
            def __init__(self, text, status, headers):
                self.text = text
                self.status_code = status
                self.headers = headers
            def json(self):
                return json.loads(self.text)
        return MockResp(text, status, resp_headers)

def load_capture(capture_id: str) -> dict:
    parts = capture_id.split(".")
    if len(parts) >= 2:
        site = parts[0]
        site_dir = CAPTURES_DIR / site
        if site_dir.exists():
            for p in site_dir.glob("*.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if data.get("capture_id") == capture_id:
                        return data
                except Exception:
                    pass
    for p in CAPTURES_DIR.rglob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("capture_id") == capture_id:
                return data
        except Exception:
            pass
    raise FileNotFoundError(f"Capture ID '{capture_id}' not found in {CAPTURES_DIR}")

def generate_fresh_fields(fresh_spec: dict) -> dict:
    now = time.time()
    res = {}
    for k, v in (fresh_spec or {}).items():
        if v == "crypto:uuid4":
            res[k] = str(uuid.uuid4())
        elif v == "time:epoch_s":
            res[k] = str(int(now))
        elif v == "time:epoch_ms":
            res[k] = str(int(now * 1000))
        elif v == "time:iso":
            res[k] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        else:
            res[k] = ""
    return res

def substitute_template(text: str, context: dict) -> str:
    if not isinstance(text, str):
        return text
    for k, v in context.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text

def execute_capture(capture_id: str, params: dict = None, cookies: dict = None) -> dict:
    cap = load_capture(capture_id)
    params = params or {}
    
    # 1. Resolve parameters & defaults
    context = {}
    for param_name, spec in cap.get("params", {}).items():
        parts = spec.split(":")
        req_type = parts[0]
        dtype = parts[1] if len(parts) > 1 else "string"
        default = parts[2] if len(parts) > 2 else None
        
        if param_name in params:
            val = params[param_name]
        elif default is not None:
            val = default
        elif req_type == "required":
            raise ValueError(f"Missing required parameter '{param_name}' for capture '{capture_id}'")
        else:
            val = ""
        context[param_name] = val

    # 2. Generate fresh preflight fields
    fresh = generate_fresh_fields(cap.get("fresh_fields", {}))
    context.update(fresh)

    # 3. Sentinel probe check (if defined and cookies available)
    sentinel = cap.get("sentinel")
    if sentinel and cookies:
        probe = sentinel.get("probe", {})
        expect = sentinel.get("expect", {})
        p_url = substitute_template(probe.get("url", ""), context)
        p_method = probe.get("method", "GET").upper()
        try:
            r = do_request(
                method=p_method,
                url=p_url,
                cookies=cookies,
                impersonate=cap.get("tls", {}).get("impersonate", "chrome"),
                timeout=10
            )
            if expect.get("http_status") and r.status_code != expect.get("http_status"):
                return {"status": "failed", "reason": "sentinel_failed", "sentinel": sentinel.get("on_fail")}
            if expect.get("contains") and expect.get("contains") not in r.text:
                return {"status": "failed", "reason": "sentinel_failed", "sentinel": sentinel.get("on_fail")}
        except Exception as e:
            return {"status": "failed", "reason": f"sentinel_error: {e}", "sentinel": sentinel.get("on_fail")}

    # 4. Multi-step wire execution
    steps = cap.get("wire", {}).get("steps", [])
    session_cookies = dict(cookies or {})
    extracted_state = {}
    last_response = None

    for step in steps:
        s_name = step.get("name")
        s_url = substitute_template(step.get("url"), {**context, **extracted_state})
        s_method = step.get("method", "GET").upper()
        s_headers = {}
        for hk, hv in (step.get("headers") or {}).items():
            s_headers[hk] = substitute_template(hv, {**context, **extracted_state})
        
        s_data = None
        if step.get("body_template"):
            s_data = substitute_template(step.get("body_template"), {**context, **extracted_state})

        t0 = time.time()
        resp = do_request(
            method=s_method,
            url=s_url,
            headers=s_headers,
            data=s_data,
            cookies=session_cookies,
            impersonate=cap.get("tls", {}).get("impersonate", "chrome"),
            timeout=25
        )
        duration_ms = int((time.time() - t0) * 1000)

        # Extraction rules
        if step.get("extract"):
            for ex_var, rule in step.get("extract").items():
                if rule.startswith("regex:"):
                    pattern = rule[len("regex:"):]
                    match = re.search(pattern, resp.text)
                    if match:
                        extracted_state[ex_var] = match.group(1)
                elif rule.startswith("json:"):
                    jpath = rule[len("json:"):].split(".")
                    try:
                        cur = resp.json()
                        for p in jpath:
                            cur = cur[p]
                        extracted_state[ex_var] = cur
                    except Exception:
                        pass

        last_response = {
            "step": s_name,
            "http_status": resp.status_code,
            "duration_ms": duration_ms,
            "headers": dict(resp.headers),
            "text": resp.text[:10000],
        }

    return {
        "status": "done",
        "capture_id": capture_id,
        "result": last_response,
        "extracted": extracted_state
    }

if __name__ == "__main__":
    print("Testing capture engine on public capture: github.get_zen.v1...")
    res = execute_capture("github.get_zen.v1")
    print(f"Status: {res.get('status')}")
    print(f"HTTP Status: {res.get('result', {}).get('http_status')}")
    print(f"Zen: {res.get('result', {}).get('text')}")
