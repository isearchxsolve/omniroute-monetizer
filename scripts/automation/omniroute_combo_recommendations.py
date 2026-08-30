#!/usr/bin/env python3
"""Generate (but do not apply) combo heads from the live, tested OmniRoute catalog."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "automation"))
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

DEFAULT_OUTPUT = ROOT / "state" / "omniroute_combo_recommendations.json"


def provider_key(model_id: str) -> str:
    return model_id.split("/", 1)[0]


def score(model_id: str, combo_name: str) -> int:
    text = model_id.lower()
    score_value = 0
    if "coding" in combo_name or "coder" in combo_name:
        score_value += 80 if any(k in text for k in ("coder", "code", "codestral", "devin")) else 0
    if "reason" in combo_name:
        score_value += 80 if any(k in text for k in ("reason", "think", "deepseek-r1", "o1", "o3")) else 0
    if "chat" in combo_name or "frontier" in combo_name:
        score_value += 60 if any(k in text for k in ("gpt", "claude", "gemini", "qwen", "sonnet", "opus")) else 0
    if "free" in combo_name:
        score_value += 30 if any(k in text for k in ("free", "llama", "qwen", "mistral")) else 0
    score_value += 20 if any(k in text for k in ("gpt-5", "claude", "deepseek", "qwen", "gemini")) else 0
    return score_value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:20128")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    api = OmniRouteAPI(base_url=args.base, password=resolve_password())
    if not api.login():
        print("management login failed")
        return 1
    try:
        providers_response = api.session.get(f"{api.api}/providers", timeout=args.timeout)
        combos_response = api.session.get(f"{api.api}/combos", timeout=args.timeout)
        models_response = api.session.get(f"{api.v1}/models", timeout=args.timeout)
    except Exception as exc:
        print(f"read failed: {type(exc).__name__}")
        return 1
    if not all(r.ok for r in (providers_response, combos_response, models_response)):
        print("read failed: management endpoint status not 2xx")
        return 1
    fleet = ROOT / "state" / "fleet_provider_audit.json"
    audited = json.loads(fleet.read_text(encoding="utf-8")) if fleet.exists() else {"connections": []}
    valid_providers = {c.get("provider") for c in audited.get("connections", []) if c.get("test", {}).get("valid") and c.get("isActive")}
    models = [str(m.get("id")) for m in (models_response.json().get("data") or []) if m.get("id")]
    eligible = [mid for mid in models if provider_key(mid) in valid_providers]
    combos = combos_response.json().get("combos") or []
    recommendations = []
    for combo in combos:
        name = str(combo.get("name") or "")
        ranked = sorted(eligible, key=lambda mid: (-score(mid, name), mid))
        recommendations.append({"name": name, "currentModelCount": len(combo.get("models") or []), "candidateHeads": ranked[:10]})
    report: dict[str, Any] = {
        "readOnly": True,
        "base": args.base.rstrip("/"),
        "catalogModelCount": len(models),
        "eligibleModelCount": len(eligible),
        "validActiveProviders": sorted(p for p in valid_providers if p),
        "combos": recommendations,
        "applied": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "catalogModelCount": len(models), "eligibleModelCount": len(eligible), "comboCount": len(recommendations), "applied": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
