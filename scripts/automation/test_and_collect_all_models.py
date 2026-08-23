"""Query and test models for all healthy providers, collecting verified working models.
"""
from __future__ import annotations
import sys
import json
import time
import pathlib
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI

sys.stdout.reconfigure(encoding="utf-8")
OMNIROUTE_BASE = "http://localhost:20128"
OUTPUT_JSON = pathlib.Path(__file__).resolve().parents[2] / "state" / "verified_latest_models.json"
OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

def log(msg):
    print(msg, flush=True)

def test_models_for_providers():
    log("=" * 80)
    log("  PROBING ALL MODELS FOR HEALTHY PROVIDERS")
    log("=" * 80)
    
    # Load probed fleet data to get healthy providers
    fleet_path = pathlib.Path(__file__).resolve().parents[2] / "state" / "master_probed_fleet.json"
    healthy_providers = set()
    if fleet_path.exists():
        fleet = json.loads(fleet_path.read_text(encoding="utf-8"))
        healthy_providers = {c["provider"] for c in fleet.get("connections", []) if c.get("valid")}
    log(f"[*] Found {len(healthy_providers)} healthy providers from recent fleet probe.")
    
    # Fetch all models from OmniRoute /v1/models
    log("[*] Fetching full model list from OmniRoute /v1/models...")
    try:
        r = requests.get(f"{OMNIROUTE_BASE}/v1/models", timeout=30)
        data = r.json().get("data", [])
        all_models = [m.get("id") for m in data if m.get("id")]
        log(f"[+] Total models in OmniRoute: {len(all_models)}")
    except Exception as e:
        log(f"[-] Failed to fetch /v1/models: {e}")
        return []

    # Filter models belonging to healthy providers or core combos
    target_models = []
    combos = [
        "frontier", "Frontier Max", "auto/pro-coding", "auto/best-coding",
        "fusion-coder", "auto/pro-reasoning", "auto/best-reasoning",
        "auto/pro-chat", "auto/best-chat", "auto/free-chat",
        "auto/asian-flagships", "kimi-coding", "moonshotai/kimi-k3-free"
    ]
    target_models.extend(combos)
    
    # Also pick representative models per healthy provider
    by_prov = {}
    for m in all_models:
        if "/" in m:
            p = m.split("/")[0]
            if p in healthy_providers:
                by_prov.setdefault(p, []).append(m)
                
    log(f"[*] Grouped models across {len(by_prov)} healthy providers.")
    
    # Select candidate models (up to 3 per provider to test thoroughly without flooding)
    candidate_models = list(combos)
    for p, p_models in by_prov.items():
        candidate_models.extend(p_models[:3])
        
    log(f"[*] Selected {len(candidate_models)} candidates for empirical verification...")
    
    verified_models = []
    for mid in candidate_models:
        t0 = time.monotonic()
        try:
            r = requests.post(
                f"{OMNIROUTE_BASE}/v1/chat/completions",
                json={"model": mid, "messages": [{"role": "user", "content": "Reply 'OK'"}], "stream": False, "max_tokens": 10},
                timeout=12
            )
            lat = int((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                js = r.json()
                content = (js.get("choices", [{}])[0].get("message", {}).get("content") or "").strip().replace("\n", " ")
                served = js.get("model", r.headers.get("x-omniroute-model", mid))
                verified_models.append({
                    "id": mid,
                    "servedModel": served,
                    "latencyMs": lat,
                    "ok": True,
                    "sample": content[:40]
                })
                log(f"  [+] {mid:45} -> 200 OK ({lat:>4}ms) [Served: {served}]")
            else:
                log(f"  [-] {mid:45} -> HTTP {r.status_code} ({lat:>4}ms)")
        except Exception as e:
            lat = int((time.monotonic() - t0) * 1000)
            log(f"  [-] {mid:45} -> Timeout/Error ({lat:>4}ms)")

    OUTPUT_JSON.write_text(json.dumps({"count": len(verified_models), "models": verified_models}, indent=2), encoding="utf-8")
    log(f"\n[+] Verified {len(verified_models)} models. Saved to: {OUTPUT_JSON}")
    return verified_models

if __name__ == "__main__":
    test_models_for_providers()
