"""Comprehensive Empirical Prober for all OmniRoute Providers, Combos, and Models.
Runs real chat completions and management connection tests, measuring status and latency.
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
OUTPUT_JSON = pathlib.Path(__file__).resolve().parents[2] / "state" / "live_probed_models_report.json"
OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

OMNIROUTE_BASE = "http://localhost:20128"

def probe_all():
    print("=" * 80)
    print("  OMNIRoute LIVE FLEET & MODEL PROBE")
    print("=" * 80)
    
    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        print("[-] OmniRoute management login failed")
        return
        
    # 1. Connection Health Tests
    print("\n[1] Testing Provider Connections...")
    conns = api.get_connections()
    active_conns = [c for c in conns if c.get("isActive")]
    print(f"    Total: {len(conns)} | Active: {len(active_conns)}")
    
    conn_results = []
    for c in active_conns:
        cid = c.get("id")
        provider = c.get("provider")
        name = c.get("name", provider)
        auth_type = c.get("authType")
        
        t0 = time.monotonic()
        t = api.test_connection(cid)
        latency = int((time.monotonic() - t0) * 1000)
        res = t.get("result") or {}
        valid = bool(res.get("valid"))
        err = res.get("error") or (res.get("diagnosis") or {}).get("message") or ""
        
        conn_results.append({
            "id": cid,
            "provider": provider,
            "name": name,
            "authType": auth_type,
            "valid": valid,
            "latencyMs": latency,
            "error": str(err)[:100]
        })
        status_str = "HEALTHY" if valid else f"UNHEALTHY ({err[:40]})"
        print(f"    - {provider:22} ({auth_type:7}): {status_str} ({latency}ms)")
        
    # 2. Probe Core Combos
    print("\n[2] Probing Core Combos via /v1/chat/completions...")
    combos = [
        "frontier", "Frontier Max", "auto/pro-coding", "auto/best-coding",
        "fusion-coder", "auto/pro-reasoning", "auto/best-reasoning",
        "auto/pro-chat", "auto/best-chat", "auto/free-chat",
        "auto/asian-flagships", "kimi-coding", "moonshotai/kimi-k3-free"
    ]
    
    combo_results = []
    for combo_id in combos:
        payload = {
            "model": combo_id,
            "messages": [{"role": "user", "content": "Respond with 'OK' and nothing else"}],
            "max_tokens": 15
        }
        t0 = time.monotonic()
        try:
            r = requests.post(f"{OMNIROUTE_BASE}/v1/chat/completions", json=payload, timeout=45)
            latency = int((time.monotonic() - t0) * 1000)
            status = r.status_code
            if status == 200:
                js = r.json()
                content = (js.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                served_model = js.get("model", combo_id)
                combo_results.append({
                    "combo": combo_id,
                    "status": 200,
                    "latencyMs": latency,
                    "servedModel": served_model,
                    "response": content[:60],
                    "ok": True
                })
                print(f"    [+] {combo_id:24} -> 200 OK ({latency}ms) [Served by: {served_model}] -> {content[:30]}")
            else:
                combo_results.append({
                    "combo": combo_id,
                    "status": status,
                    "latencyMs": latency,
                    "error": r.text[:120],
                    "ok": False
                })
                print(f"    [-] {combo_id:24} -> HTTP {status} ({latency}ms) -> {r.text[:80]}")
        except Exception as exc:
            latency = int((time.monotonic() - t0) * 1000)
            combo_results.append({
                "combo": combo_id,
                "status": 0,
                "latencyMs": latency,
                "error": str(exc)[:120],
                "ok": False
            })
            print(f"    [-] {combo_id:24} -> Timeout/Error ({latency}ms) -> {exc}")

    # 3. Probe Top Individual Models
    print("\n[3] Probing Top Representative Standalone Models...")
    key_models = [
        "codex/gpt-5.6-sol",
        "ainative/claude-sonnet-4-5",
        "ainative/claude-opus-4",
        "ainative/deepseek-r1",
        "kimi-coding/kimi-coding-default",
        "nvidia/nemotron-3-super-120b-a12b",
        "alibaba/qwen3.7-max",
        "gemini/gemini-2.5-pro",
        "groq/llama-3.3-70b-versatile",
        "cerebras/gpt-oss-120b",
        "openrouter/qwen/qwen3.8-max",
        "openrouter/anthropic/claude-3.5-sonnet",
        "deepinfra/deepseek-ai/DeepSeek-V3-0324",
        "cloudflare-ai/@cf/qwen/qwq-32b"
    ]
    
    model_results = []
    for mid in key_models:
        payload = {
            "model": mid,
            "messages": [{"role": "user", "content": "Respond with 'OK' and nothing else"}],
            "max_tokens": 15
        }
        t0 = time.monotonic()
        try:
            r = requests.post(f"{OMNIROUTE_BASE}/v1/chat/completions", json=payload, timeout=40)
            latency = int((time.monotonic() - t0) * 1000)
            status = r.status_code
            if status == 200:
                js = r.json()
                content = (js.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                model_results.append({
                    "model": mid,
                    "status": 200,
                    "latencyMs": latency,
                    "response": content[:60],
                    "ok": True
                })
                print(f"    [+] {mid:36} -> 200 OK ({latency}ms) -> {content[:30]}")
            else:
                model_results.append({
                    "model": mid,
                    "status": status,
                    "latencyMs": latency,
                    "error": r.text[:120],
                    "ok": False
                })
                print(f"    [-] {mid:36} -> HTTP {status} ({latency}ms) -> {r.text[:80]}")
        except Exception as exc:
            latency = int((time.monotonic() - t0) * 1000)
            model_results.append({
                "model": mid,
                "status": 0,
                "latencyMs": latency,
                "error": str(exc)[:120],
                "ok": False
            })
            print(f"    [-] {mid:36} -> Timeout/Error ({latency}ms) -> {exc}")

    # Save summary report
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
    print(f"\n[+] Probe complete. Report saved to: {OUTPUT_JSON}")

if __name__ == "__main__":
    probe_all()
