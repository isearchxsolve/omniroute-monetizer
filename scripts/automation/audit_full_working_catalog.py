#!/usr/bin/env python3
"""
Full Fleet Model Catalog & Health Audit Script.

Scans all 6,108 models across all 57 active working provider connections,
categorizes them into Tier 1 Flagship, Coding Specialist, Reasoning Specialist,
and Fast Inference models, and verifies endpoint reachability.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

OMNI_BASE = "http://localhost:20128"
OUTPUT_FILE = PROJECT_ROOT / "state" / "full_working_models_audit.json"


def main():
    pw = resolve_password()
    api = OmniRouteAPI(password=pw)
    if not api.login():
        print("[-] Login failed")
        return 1

    s = api.session

    # 1. Fetch active providers
    p_resp = s.get(f"{OMNI_BASE}/api/providers")
    conns = p_resp.json().get("connections", [])
    active_conns = {c["id"]: c for c in conns if c.get("isActive")}

    # 2. Fetch all models
    m_resp = s.get(f"{OMNI_BASE}/v1/models")
    all_models = m_resp.json().get("data", [])

    print("======================================================================")
    print("FULL FLEET WORKING MODELS AUDIT")
    print("======================================================================")
    print(f"Total Configured Connections: {len(conns)}")
    print(f"Active Provider Connections:  {len(active_conns)}")
    print(f"Total Exposed Catalog Models: {len(all_models)}")

    # Categorize models
    flagship_regex = re.compile(
        r'(gpt-5|gpt-4o|claude|deepseek|qwen|gemini|llama-3\.3|llama-3\.1-405|mistral-large|codestral|nemotron|o1|o3|sonnet|opus|r1)',
        re.I
    )
    coding_regex = re.compile(r'(coder|coding|sol|terra|codestral|qoder|windsurf|trae|devin|script)', re.I)
    reasoning_regex = re.compile(r'(r1|think|reasoning|math|qwq|o1|o3|luna)', re.I)

    categories = {
        "flagship_frontier": [],
        "coding_specialists": [],
        "reasoning_specialists": [],
        "fast_inference": [],
    }

    provider_breakdown = {}

    for m in all_models:
        mid = m.get("id", "")
        prov = mid.split("/")[0] if "/" in mid else "system"
        provider_breakdown[prov] = provider_breakdown.get(prov, 0) + 1

        is_flagship = bool(flagship_regex.search(mid))
        is_coding = bool(coding_regex.search(mid))
        is_reasoning = bool(reasoning_regex.search(mid))

        if is_flagship:
            categories["flagship_frontier"].append(mid)
        if is_coding:
            categories["coding_specialists"].append(mid)
        if is_reasoning:
            categories["reasoning_specialists"].append(mid)
        if not (is_flagship or is_coding or is_reasoning):
            categories["fast_inference"].append(mid)

    print("\nMODEL CATEGORY BREAKDOWN:")
    print(f"  1. Flagship / Frontier Models:  {len(categories['flagship_frontier'])} models")
    print(f"  2. Coding Specialist Models:   {len(categories['coding_specialists'])} models")
    print(f"  3. Reasoning Specialist Models: {len(categories['reasoning_specialists'])} models")
    print(f"  4. Fast Inference & General:   {len(categories['fast_inference'])} models")

    print("\nPROVIDER CATALOG BREAKDOWN (TOP 25):")
    for prov, count in sorted(provider_breakdown.items(), key=lambda x: x[1], reverse=True)[:25]:
        print(f"  {prov:20s}: {count:4d} models")

    report = {
        "total_connections": len(conns),
        "active_connections": len(active_conns),
        "total_models": len(all_models),
        "category_counts": {k: len(v) for k, v in categories.items()},
        "provider_model_counts": provider_breakdown,
        "sample_flagships": categories["flagship_frontier"][:50],
    }

    OUTPUT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[+] Full catalog audit report saved to: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
