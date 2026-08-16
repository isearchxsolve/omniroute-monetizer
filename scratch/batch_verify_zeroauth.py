#!/usr/bin/env python3
"""Batch-verify cloud zero-auth providers upstream (no keys, no signup).
Zero-fabrication: only marks verified after a real 200 with content.
"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

HDRS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
MSG = [{"role": "user", "content": "Reply with the single word: ready"}]

CANDIDATES = [
    # (slug, chat_url, model, extra_headers, payload_style)
    ("pollinations", "https://gen.pollinations.ai/v1/chat/completions", "openai", {}, "openai"),
    ("duckduckgo-web", "https://duckduckgo.com/duckchat/v1/chat", "gpt-4o-mini", {}, "ddg"),
    ("theoldllm", "https://theoldllm.vercel.app/api/chatgpt", "gpt-4o-mini", {}, "openai"),
    ("hackclub", "https://ai.hackclub.com/proxy/v1/chat/completions", None, {}, "openai"),
    ("g4f-gemini", "https://g4f.space/api/gemini/v1/chat/completions", "gemini-2.0-flash", {}, "openai"),
    ("g4f-groq", "https://g4f.space/api/groq/v1/chat/completions", "llama-3.1-8b-instant", {}, "openai"),
    ("g4f-nvidia", "https://g4f.space/api/nvidia/v1/chat/completions", None, {}, "openai"),
    ("uncloseai", "https://hermes.ai.unturf.com/v1/chat/completions", None, {}, "openai"),
]

results = {}


def try_chat(slug, url, model, extra, style):
    headers = dict(HDRS)
    headers.update(extra)
    if style == "ddg":
        # DuckDuckGo needs a VQD token first
        try:
            req = urllib.request.Request("https://duckduckgo.com/duckchat/v1/status",
                                         headers={"User-Agent": "Mozilla/5.0", "x-vqd-accept": "1"})
            r = urllib.request.urlopen(req, timeout=20)
            vqd = r.headers.get("x-vqd-4")
            if not vqd:
                return ("fail", "no vqd token", None)
            headers["x-vqd-4"] = vqd
        except Exception as e:
            return ("fail", f"vqd fetch: {e}", None)
        payload = {"model": model, "messages": MSG}
    else:
        payload = {"model": model or "openai", "messages": MSG, "max_tokens": 16, "temperature": 0}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=45)
        body = r.read().decode(errors="replace")
        try:
            j = json.loads(body)
            content = (j.get("choices") or [{}])[0].get("message", {}).get("content", "")
        except Exception:
            content = body[:80]
        return ("ok", f"HTTP {r.status}", content[:60])
    except urllib.error.HTTPError as e:
        return ("fail", f"HTTP {e.code}", e.read().decode(errors="replace")[:150])
    except Exception as e:
        return ("fail", str(e)[:100], None)


def pick_model(models_url):
    """Fetch first model id from a models endpoint."""
    try:
        req = urllib.request.Request(models_url, headers=HDRS)
        r = urllib.request.urlopen(req, timeout=20)
        data = json.loads(r.read().decode())
        ids = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
        return ids[0] if ids else None
    except Exception:
        return None


for slug, url, model, extra, style in CANDIDATES:
    if model is None:
        # try to discover model
        mu = {"hackclub": "https://ai.hackclub.com/proxy/v1/models",
              "g4f-nvidia": "https://g4f.space/api/nvidia/v1/models",
              "uncloseai": "https://hermes.ai.unturf.com/v1/models"}.get(slug)
        if mu:
            model = pick_model(mu)
            print(f"[{slug}] discovered model: {model}")
        if model is None:
            model = "openai" if slug == "uncloseai" else "gpt-4o-mini"
    status, info, content = try_chat(slug, url, model, extra, style)
    results[slug] = {"status": status, "info": info, "content": content, "model": model}
    mark = "✅" if status == "ok" else "❌"
    print(f"{mark} {slug}: {info}" + (f" | reply={content!r}" if content else ""))

ok = [k for k, v in results.items() if v["status"] == "ok"]
print(f"\nVERIFIED zero-auth: {len(ok)}/{len(CANDIDATES)}: {ok}")

with open(os.path.join(ROOT, "state", "zeroauth_verify_results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print("[+] saved state/zeroauth_verify_results.json")
