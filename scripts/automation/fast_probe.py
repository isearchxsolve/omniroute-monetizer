"""Fast Empirical Prober for Key Combos and Frontier Models with immediate flush.
"""
from __future__ import annotations
import sys
import json
import time
import requests

sys.stdout.reconfigure(encoding="utf-8")
OMNIROUTE_BASE = "http://localhost:20128"

def log(msg):
    print(msg, flush=True)

def fast_probe():
    log("="*75)
    log("  FAST PROBE: COMBOS & FRONTIER MODELS")
    log("="*75)
    
    # 1. Combos
    combos = [
        "frontier", "Frontier Max", "auto/pro-coding", "auto/best-coding",
        "fusion-coder", "auto/pro-reasoning", "auto/best-reasoning",
        "auto/pro-chat", "auto/best-chat", "auto/free-chat",
        "auto/asian-flagships", "kimi-coding", "moonshotai/kimi-k3-free"
    ]
    
    log("\n[1] PROBING ROUTING COMBOS:")
    for cid in combos:
        t0 = time.monotonic()
        try:
            r = requests.post(
                f"{OMNIROUTE_BASE}/v1/chat/completions",
                json={"model": cid, "messages": [{"role": "user", "content": "Reply 'OK'"}], "max_tokens": 10},
                timeout=12
            )
            lat = int((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                js = r.json()
                content = (js.get("choices", [{}])[0].get("message", {}).get("content") or "").strip().replace("\n", " ")
                served = js.get("model", cid)
                log(f"  [+] {cid:22} -> 200 OK ({lat:>4}ms) [Served: {served}] -> '{content[:40]}'")
            else:
                log(f"  [-] {cid:22} -> HTTP {r.status_code} ({lat:>4}ms) -> {r.text[:60]}")
        except Exception as e:
            lat = int((time.monotonic() - t0) * 1000)
            log(f"  [-] {cid:22} -> Timeout/Error ({lat:>4}ms): {e}")

    # 2. Key Individual Models
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
        "cloudflare-ai/@cf/qwen/qwq-32b"
    ]
    
    log("\n[2] PROBING KEY STANDALONE MODELS:")
    for mid in models:
        t0 = time.monotonic()
        try:
            r = requests.post(
                f"{OMNIROUTE_BASE}/v1/chat/completions",
                json={"model": mid, "messages": [{"role": "user", "content": "Reply 'OK'"}], "max_tokens": 10},
                timeout=12
            )
            lat = int((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                js = r.json()
                content = (js.get("choices", [{}])[0].get("message", {}).get("content") or "").strip().replace("\n", " ")
                log(f"  [+] {mid:36} -> 200 OK ({lat:>4}ms) -> '{content[:40]}'")
            else:
                log(f"  [-] {mid:36} -> HTTP {r.status_code} ({lat:>4}ms) -> {r.text[:60]}")
        except Exception as e:
            lat = int((time.monotonic() - t0) * 1000)
            log(f"  [-] {mid:36} -> Timeout/Error ({lat:>4}ms): {e}")

if __name__ == "__main__":
    fast_probe()
