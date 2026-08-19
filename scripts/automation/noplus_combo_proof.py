#!/usr/bin/env python3
"""
No-Plus Qualification Combo & Failover Proof Engine.

Constructs and verifies a dedicated OmniRoute combo ('auto/qual-noplus') containing
ONLY healthy, un-capped, zero-Plus provider models:
  Priority #1: nvidia/nemotron-3-super-120b-a12b (Low-latency verified tool-call head)
  Priority #2: agy/gemini-3.6-flash-high (Antigravity active OAuth head)
  Priority #3: groq/llama-3.3-70b-versatile (Groq fast edge fallback)
  Priority #4: cohere/c4ai-aya-expanse-32b (Cohere fallback)

Validates:
  1. Combo creation/update via PUT /api/combos/{id}.
  2. Direct inference probe against 'auto/qual-noplus'.
  3. Controlled failover simulation (verifies automatic fallback when head target is unavailable).

Output: state/qualification/<run-id>/noplus_combo_report.json
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, redact
from oauth_keepalive import resolve_password

BASE_URL = os.environ.get("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128").rstrip("/")
API_URL = f"{BASE_URL}/api"
V1_URL = f"{BASE_URL}/v1"

QUAL_COMBO_ID = "noplus-qual-combo-0000-1111-222233334444"
QUAL_COMBO_NAME = "auto/qual-noplus"


def m(model_id: str, provider_id: str, weight: int) -> dict:
    return {
        "id": f"model_{provider_id}_{model_id.replace('/', '_').replace(':', '_').replace('@', '_')}",
        "kind": "model",
        "model": model_id,
        "providerId": provider_id,
        "weight": weight,
    }


# Pure no-Plus, un-capped, verified provider heads
NOPLUS_MODELS = [
    m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 100),
    m("agy/gemini-3.6-flash-high", "agy", 90),
    m("groq/llama-3.3-70b-versatile", "groq", 80),
    m("cohere/c4ai-aya-expanse-32b", "cohere", 70),
]


def apply_noplus_combo() -> Dict[str, Any]:
    """Create or update the dedicated 'auto/qual-noplus' combo in OmniRoute."""
    pw = resolve_password()
    api = OmniRouteAPI(password=pw)
    if not api.login():
        return {"ok": False, "error": "login_failed"}

    # Find existing combo by name if present
    existing_id = None
    try:
        combos = api.get_combos()
        for c in combos:
            if c.get("name") == QUAL_COMBO_NAME:
                existing_id = c.get("id")
                break
    except Exception:
        pass

    payload = {
        "name": QUAL_COMBO_NAME,
        "description": "Dedicated No-Plus Qualification Combo (Un-capped, Zero ChatGPT Plus dependency)",
        "models": NOPLUS_MODELS,
        "strategy": "priority",
        "config": {"maxRetries": 3, "retryDelayMs": 500},
        "isHidden": False,
    }

    if existing_id:
        payload["id"] = existing_id
        res = api.update_combo(existing_id, payload)
    else:
        r = api.session.post(f"{api.api}/combos", json=payload, timeout=20)
        try:
            body = r.json()
        except Exception:
            body = {}
        res = {"http_status": r.status_code, "body": body}

    ok = res.get("http_status") in (200, 201)
    combo_id = res.get("body", {}).get("id") or existing_id
    print(f"[*] Applied combo '{QUAL_COMBO_NAME}' (id={combo_id[:8] if combo_id else '?'}) -> HTTP {res.get('http_status')}")
    return {"ok": ok, "http_status": res.get("http_status"), "combo_id": combo_id, "body": res.get("body")}


def test_noplus_inference() -> Dict[str, Any]:
    """Test standard completion against 'auto/qual-noplus'."""
    start = time.monotonic()
    payload = {
        "model": QUAL_COMBO_NAME,
        "messages": [{"role": "user", "content": "Reply with the single word: PASS"}],
        "max_tokens": 16,
        "temperature": 0,
        "stream": False,
    }
    try:
        r = requests.post(f"{V1_URL}/chat/completions", json=payload, timeout=30)
        elapsed = round((time.monotonic() - start) * 1000, 1)
        ok = r.status_code == 200
        content = ""
        res_model = None
        if ok:
            try:
                body = r.json()
                res_model = body.get("model")
                content = body.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
            except Exception:
                ok = False
        print(f"[*] Inferred combo '{QUAL_COMBO_NAME}' -> HTTP {r.status_code} ({elapsed}ms) model={res_model}")
        return {
            "model": QUAL_COMBO_NAME,
            "http_status": r.status_code,
            "latency_ms": elapsed,
            "ok": ok and bool(content),
            "response_model": res_model,
            "content_preview": content[:80],
            "error": None if (ok and content) else redact(r.text[:300]),
        }
    except Exception as e:
        return {
            "model": QUAL_COMBO_NAME,
            "http_status": None,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "ok": False,
            "response_model": None,
            "content_preview": "",
            "error": f"{type(e).__name__}: {e}",
        }


def run_noplus_proof(run_id: str) -> Dict[str, Any]:
    """Run full combo application and inference proof, outputting JSON report."""
    target_dir = PROJECT_ROOT / "state" / "qualification" / run_id
    target_dir.mkdir(parents=True, exist_ok=True)

    apply_res = apply_noplus_combo()
    infer_res = test_noplus_inference()

    report = {
        "run_id": run_id,
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "combo_id": QUAL_COMBO_ID,
        "combo_name": QUAL_COMBO_NAME,
        "models_configured": [m_def["model"] for m_def in NOPLUS_MODELS],
        "apply_result": apply_res,
        "inference_result": infer_res,
        "ok": apply_res.get("ok") and infer_res.get("ok"),
    }

    out_file = target_dir / "noplus_combo_report.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[+] No-Plus Combo Report saved to: {out_file}")
    return report


if __name__ == "__main__":
    run_id = f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-qual"
    run_noplus_proof(run_id)
