"""Master Fleet & Model Prober for OmniRoute.
Tests all connections, combos, and representative models with stream: False.
"""
from __future__ import annotations
import sys
import json
import time
import pathlib
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI, redact

sys.stdout.reconfigure(encoding="utf-8")
OUTPUT_JSON = pathlib.Path(__file__).resolve().parents[2] / "state" / "master_probed_fleet.json"
OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

OMNIROUTE_BASE = "http://localhost:20128"

def log(msg=""):
    print(msg, flush=True)

def main():
    log("=" * 80)
    log("      OMNIRoute MASTER FLEET & MODEL PROBE")
    log("=" * 80)
    
    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        log("[-] Management API login failed")
        return 1
        
    # 1. Provider Connection Tests
    log("\n[1] AUDITING CONFIGURED PROVIDER CONNECTIONS:")
    conns = api.get_connections()
    active_conns = [c for c in conns if c.get("isActive")]
    log(f"    Total Connections: {len(conns)} | Active: {len(active_conns)}")
    
    conn_results = []
    for c in active_conns:
        cid = c.get("id")
        p = c.get("provider")
        name = c.get("name", p)
        auth = c.get("authType")
        
        t0 = time.monotonic()
        t = api.test_connection(cid)
        lat = int((time.monotonic() - t0) * 1000)
        res = t.get("result") or {}
        valid = bool(res.get("valid"))
        diag = res.get("diagnosis") or res.get("error") or (res.get("message") if isinstance(res, dict) else "") or ""
        diag_str = str(diag)[:60]
        
        conn_results.append({
            "id": cid,
            "provider": p,
            "name": name,
            "authType": auth,
            "valid": valid,
            "latencyMs": lat,
            "diag": diag_str
        })
        status_tag = "VALID [200]" if valid else f"INVALID: {diag_str}"
        log(f"  - {p:22} ({auth:7}) -> {status_tag} ({lat}ms)")

    # 2. Probe Combos
    combos = [
        "frontier", "Frontier Max", "auto/pro-coding", "auto/best-coding",
        "fusion-coder", "auto/pro-reasoning", "auto/best-reasoning",
        "auto/pro-chat", "auto/best-chat", "auto/free-chat",
        "auto/asian-flagships", "kimi-coding", "moonshotai/kimi-k3-free"
    ]
    
    log("\n[2] PROBING ROUTING COMBOS (/v1/chat/completions):")
    combo_results = []
    for cid in combos:
        t0 = time.monotonic()
        try:
            r = requests.post(
                f"{OMNIROUTE_BASE}/v1/chat/completions",
                json={"model": cid, "messages": [{"role": "user", "content": "Respond with 'HEALTHY'"}], "stream": False, "max_tokens": 15},
                timeout=25
            )
            lat = int((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                js = r.json()
                content = (js.get("choices", [{}])[0].get("message", {}).get("content") or "").strip().replace("\n", " ")
                served = js.get("model", r.headers.get("x-omniroute-model", cid))
                combo_results.append({
                    "combo": cid,
                    "status": 200,
                    "latencyMs": lat,
                    "servedModel": served,
                    "response": content[:60],
                    "ok": True
                })
                log(f"  [+] {cid:24} -> 200 OK ({lat:>4}ms) [Served: {served}] -> '{content[:40]}'")
            else:
                combo_results.append({
                    "combo": cid,
                    "status": r.status_code,
                    "latencyMs": lat,
                    "error": r.text[:100],
                    "ok": False
                })
                log(f"  [-] {cid:24} -> HTTP {r.status_code} ({lat:>4}ms) -> {r.text[:60]}")
        except Exception as e:
            lat = int((time.monotonic() - t0) * 1000)
            combo_results.append({
                "combo": cid,
                "status": 0,
                "latencyMs": lat,
                "error": str(e)[:100],
                "ok": False
            })
            log(f"  [-] {cid:24} -> Timeout/Error ({lat:>4}ms): {e}")

    # 3. Probe Top Individual Models
    models = [
        "codex/gpt-5.6-sol",
        "ainative/claude-sonnet-4-5",
        "ainative/claude-opus-4",
        "ainative/deepseek-r1",
        "kimi-coding/kimi-coding-default",
        "nvidia/nemotron-3-super-120b-a12b",
        "alibaba/qwen3.7-max",
        "gemini/gemini-2.5-pro",
        "agy/gemini-3.6-flash-high",
        "groq/llama-3.3-70b-versatile",
        "cerebras/gpt-oss-120b",
        "openrouter/qwen/qwen3.8-max",
        "openrouter/anthropic/claude-3.5-sonnet",
        "deepinfra/deepseek-ai/DeepSeek-V3-0324",
        "cloudflare-ai/@cf/qwen/qwq-32b",
        "cloudflare-ai/@cf/meta/llama-3.2-3b-instruct"
    ]
    
    log("\n[3] PROBING KEY STANDALONE MODELS:")
    model_results = []
    for mid in models:
        t0 = time.monotonic()
        try:
            r = requests.post(
                f"{OMNIROUTE_BASE}/v1/chat/completions",
                json={"model": mid, "messages": [{"role": "user", "content": "Respond with 'HEALTHY'"}], "stream": False, "max_tokens": 15},
                timeout=25
            )
            lat = int((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                js = r.json()
                content = (js.get("choices", [{}])[0].get("message", {}).get("content") or "").strip().replace("\n", " ")
                model_results.append({
                    "model": mid,
                    "status": 200,
                    "latencyMs": lat,
                    "response": content[:60],
                    "ok": True
                })
                log(f"  [+] {mid:44} -> 200 OK ({lat:>4}ms) -> '{content[:40]}'")
            else:
                model_results.append({
                    "model": mid,
                    "status": r.status_code,
                    "latencyMs": lat,
                    "error": r.text[:100],
                    "ok": False
                })
                log(f"  [-] {mid:44} -> HTTP {r.status_code} ({lat:>4}ms) -> {r.text[:60]}")
        except Exception as e:
            lat = int((time.monotonic() - t0) * 1000)
            model_results.append({
                "model": mid,
                "status": 0,
                "latencyMs": lat,
                "error": str(e)[:100],
                "ok": False
            })
            log(f"  [-] {mid:44} -> Timeout/Error ({lat:>4}ms): {e}")

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "totalConnections": len(conns),
        "activeConnections": len(active_conns),
        "validConnectionsCount": sum(1 for c in conn_results if c["valid"]),
        "connections": conn_results,
        "combos": combo_results,
        "models": model_results
    }
    OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"\n[+] Probe complete! Saved to {OUTPUT_JSON}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
