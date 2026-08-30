#!/usr/bin/env python3
"""Redacted, read-only inventory audit for the local OmniRoute video router."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_BASE = "http://127.0.0.1:8189"
DEFAULT_OUTPUT = ROOT / "state" / "video_capability_audit.json"


def get_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8", "replace"))
    return parsed if isinstance(parsed, dict) else {}


def summarize(health: dict[str, Any], models: dict[str, Any]) -> dict[str, Any]:
    accounts = health.get("accounts") if isinstance(health.get("accounts"), list) else []
    catalog = models.get("data") if isinstance(models.get("data"), list) else []
    return {
        "routerOk": bool(health.get("ok")),
        "dryRun": bool(health.get("dry_run")),
        "routerAuthenticated": bool(health.get("authenticated")),
        "providers": sorted(str(p) for p in (health.get("providers") or [])),
        "accountsTotal": len(accounts),
        "accountsReady": sum(1 for account in accounts if isinstance(account, dict) and account.get("ready")),
        "jobs": health.get("jobs") if isinstance(health.get("jobs"), dict) else {},
        "modelCount": len(catalog),
        "provenModelCount": sum(1 for model in catalog if isinstance(model, dict) and model.get("proven")),
        "models": [
            {"id": model.get("id"), "provider": model.get("provider"), "proven": bool(model.get("proven")),
             "quotesBeforeSpending": bool(model.get("quotes_before_spending")), "estCost": model.get("est_cost")}
            for model in catalog if isinstance(model, dict)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    try:
        report = summarize(get_json(f"{base}/healthz", args.timeout), get_json(f"{base}/v1/models", args.timeout))
    except Exception as exc:
        print(f"audit failed: {type(exc).__name__}")
        return 1
    report.update({"generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "base": base, "readOnly": True})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("routerOk", "dryRun", "providers", "accountsTotal", "accountsReady", "modelCount", "provenModelCount")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
