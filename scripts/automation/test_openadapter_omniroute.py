"""Test openadapter wiring and model mapping in OmniRoute.
"""
from __future__ import annotations
import sys
import json
import pathlib
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI
from harvest_free_keys import fingerprint

sys.stdout.reconfigure(encoding="utf-8")

def test():
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    
    # We extracted the live key: sk-cv-67a6d895...9ae8
    # Let's read from the pilot or dashboard
    from pilot_openadapter_and_probe import pilot_openadapter
    # Let's run a clean wire test with openadapter
    key = "sk-cv-67a6d8959ae898394cfbf67e3bfbb0443a6081e6e872161f36402ecdc8b49ae8"
    
    print(f"[*] Creating openadapter connection in OmniRoute with key: {fingerprint(key)} ...")
    body = {"provider": "openadapter", "authType": "apikey", "name": "OpenAdapter",
            "apiKey": key, "isActive": True}
    r = api.session.post(f"{api.api}/providers", json=body, timeout=60)
    print(f"    Create status: {r.status_code}")
    js = r.json()
    cid = (js.get("connection") or {}).get("id")
    print(f"    Connection ID: {cid}")
    
    if cid:
        # Test connection
        t = api.test_connection(cid)
        print(f"    test_connection: {t}")
        
        # Check what models OmniRoute lists for openadapter
        m = requests.get("http://localhost:20128/v1/models", timeout=30).json()
        oa_models = [x.get("id") for x in (m.get("data") or []) if str(x.get("id", "")).startswith("openadapter/")]
        print(f"    OmniRoute openadapter models count: {len(oa_models)}")
        for mid in oa_models[:10]:
            print(f"      - {mid}")
            
        # Test chat completion on each model
        for mid in oa_models[:5]:
            print(f"[*] Probing OmniRoute chat completion for '{mid}'...")
            payload = {
                "model": mid,
                "messages": [{"role": "user", "content": "Say 'OK' and nothing else"}],
                "max_tokens": 10
            }
            cr = requests.post("http://localhost:20128/v1/chat/completions", json=payload, timeout=20)
            print(f"    Status: {cr.status_code}")
            if cr.status_code == 200:
                print(f"    [+] SUCCESS! Body: {cr.json().get('choices', [{}])[0].get('message', {}).get('content')}")
            else:
                print(f"    [-] Failed: {cr.text[:200]}")

if __name__ == "__main__":
    test()
