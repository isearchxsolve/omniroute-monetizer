#!/usr/bin/env python3
"""
Tier 1 — Zero-DOM Fast-Path CLI & Runtime Token Harvester (COMPLETE)

Harvests active tokens from local developer runtimes, verifies each one
directly against the upstream provider endpoint (200 OK required), then
hot-injects validated keys into matching OmniRoute apikey connections
via PUT /api/providers/{id} and confirms with POST /api/providers/{id}/test.

Rules enforced (AGENTS.md):
- A credential is NEVER reported as harvested unless verified with an
  authenticated 200 OK against the external provider's upstream endpoint.
- Only injects into connections with authType == "apikey" (OAuth sessions
  are handled by refresh/re-auth paths, not raw key injection).
- Idempotent: skips injection when the connection is already active.
- No secrets in logs or artifacts (all redacted).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from omniroute_api import OmniRouteAPI, log, mask_token, save_json  # noqa: E402

HARVEST_TIMEOUT = 15


@dataclass
class HarvestedToken:
    source: str            # e.g. "env:OPENROUTER_API_KEY", "gh-cli"
    provider: str          # canonical OmniRoute provider slug
    token: str
    upstream_verified: bool = False
    upstream_status: Optional[int] = None
    injected_connection: Optional[str] = None
    injection_status: Optional[int] = None
    test_valid: Optional[bool] = None
    note: str = ""

    def redacted(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "provider": self.provider,
            "token": mask_token(self.token),
            "upstream_verified": self.upstream_verified,
            "upstream_status": self.upstream_status,
            "injected_connection": self.injected_connection,
            "injection_status": self.injection_status,
            "test_valid": self.test_valid,
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# Upstream verification endpoints (one lightweight authenticated GET each)
# ---------------------------------------------------------------------------

def _verify(url: str, headers: Dict[str, str]) -> Optional[int]:
    try:
        r = requests.get(url, headers=headers, timeout=HARVEST_TIMEOUT)
        return r.status_code
    except Exception as e:
        log(f"Upstream check failed for {url}: {type(e).__name__}", "warn")
        return None


UPSTREAM_VERIFIERS = {
    "openrouter": lambda t: _verify(
        "https://openrouter.ai/api/v1/key",
        {"Authorization": f"Bearer {t}"},
    ),
    "nvidia": lambda t: _verify(
        "https://integrate.api.nvidia.com/v1/models",
        {"Authorization": f"Bearer {t}"},
    ),
    "cerebras": lambda t: _verify(
        "https://api.cerebras.ai/v1/models",
        {"Authorization": f"Bearer {t}"},
    ),
    "cohere": lambda t: _verify(
        "https://api.cohere.com/v2/models",
        {"Authorization": f"Bearer {t}"},
    ),
    "github": lambda t: _verify(
        "https://api.github.com/user",
        {"Authorization": f"Bearer {t}", "Accept": "application/vnd.github+json"},
    ),
    "anthropic": lambda t: _verify(
        "https://api.anthropic.com/v1/models",
        {"x-api-key": t, "anthropic-version": "2023-06-01"},
    ),
    "openai": lambda t: _verify(
        "https://api.openai.com/v1/models",
        {"Authorization": f"Bearer {t}"},
    ),
    "deepseek": lambda t: _verify(
        "https://api.deepseek.com/models",
        {"Authorization": f"Bearer {t}"},
    ),
    "huggingface": lambda t: _verify(
        "https://huggingface.co/api/whoami-v2",
        {"Authorization": f"Bearer {t}"},
    ),
}

# env var -> provider slug
ENV_PROVIDER_MAP = {
    "OPENROUTER_API_KEY": "openrouter",
    "NVIDIA_API_KEY": "nvidia",
    "CEREBRAS_API_KEY": "cerebras",
    "COHERE_API_KEY": "cohere",
    "ANTHROPIC_API_KEY": "anthropic",
    "OPENAI_API_KEY": "openai",
    "DEEPSEEK_API_KEY": "deepseek",
    "GITHUB_TOKEN": "github",
    "HF_TOKEN": "huggingface",
    "HUGGINGFACE_TOKEN": "huggingface",
}


def _classify_token(token: str) -> Optional[str]:
    if token.startswith(("ghp_", "gho_", "ghu_", "ghs_")):
        return "github"
    if token.startswith("sk-or-"):
        return "openrouter"
    if token.startswith("sk-ant-"):
        return "anthropic"
    if token.startswith("sk-proj-") or re.match(r"^sk-[A-Za-z0-9]{40,}$", token):
        return "openai"
    if token.startswith("sk-cs-"):
        return "cerebras"
    if token.startswith("hf_"):
        return "huggingface"
    return None


# ---------------------------------------------------------------------------
# Harvest sources
# ---------------------------------------------------------------------------

def harvest_env_tokens() -> List[HarvestedToken]:
    out: List[HarvestedToken] = []
    for env, provider in ENV_PROVIDER_MAP.items():
        val = (os.environ.get(env) or "").strip()
        if val and len(val) > 10:
            out.append(HarvestedToken(source=f"env:{env}", provider=provider, token=val))
    return out


def harvest_github_cli() -> List[HarvestedToken]:
    out: List[HarvestedToken] = []
    try:
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        token = (res.stdout or "").strip()
        if res.returncode == 0 and token:
            out.append(HarvestedToken(source="gh-cli", provider="github", token=token))
    except Exception:
        pass
    if not out:
        gh_hosts = os.path.expanduser("~/.config/gh/hosts.yml")
        if os.path.exists(gh_hosts):
            try:
                for line in open(gh_hosts, encoding="utf-8"):
                    if "oauth_token:" in line:
                        token = line.split("oauth_token:", 1)[1].strip().strip("'\"")
                        if token:
                            out.append(HarvestedToken(source="gh-hosts.yml", provider="github", token=token))
                        break
            except Exception:
                pass
    return out


def harvest_codex_config() -> List[HarvestedToken]:
    """Extract plain API keys (not OAuth blobs) from codex config files."""
    out: List[HarvestedToken] = []
    paths = [
        os.path.expanduser("~/.codex/config.toml"),
        os.path.expanduser("~/.codex/config.json"),
    ]
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            content = open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for m in re.finditer(
            r"(OPENROUTER|NVIDIA|OPENAI|ANTHROPIC|CEREBRAS|COHERE|DEEPSEEK)[A-Z_]*_?(?:API_)?KEY\s*[=:]\s*[\"']?([A-Za-z0-9_\-]{20,})",
            content,
        ):
            token = m.group(2)
            provider = _classify_token(token) or m.group(1).lower()
            out.append(HarvestedToken(source=f"codex-config:{os.path.basename(path)}", provider=provider, token=token))
    return out


def harvest_zed_config() -> List[HarvestedToken]:
    out: List[HarvestedToken] = []
    zed = os.path.expandvars(r"%APPDATA%\Zed\settings.json")
    if not os.path.exists(zed):
        return out
    try:
        content = open(zed, encoding="utf-8", errors="replace").read()
    except Exception:
        return out
    for m in re.finditer(r"(sk-or-v1-[A-Za-z0-9\-]{20,}|sk-ant-[A-Za-z0-9\-_]{20,}|sk-proj-[A-Za-z0-9\-_]{20,})", content):
        token = m.group(1)
        provider = _classify_token(token)
        if provider:
            out.append(HarvestedToken(source="zed-settings", provider=provider, token=token))
    return out


def harvest_all() -> List[HarvestedToken]:
    tokens: List[HarvestedToken] = []
    tokens += harvest_env_tokens()
    tokens += harvest_github_cli()
    tokens += harvest_codex_config()
    tokens += harvest_zed_config()
    # de-duplicate by (provider, token)
    seen = set()
    unique: List[HarvestedToken] = []
    for t in tokens:
        key = (t.provider, t.token)
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


# ---------------------------------------------------------------------------
# Verify + inject
# ---------------------------------------------------------------------------

def verify_upstream(t: HarvestedToken) -> None:
    verifier = UPSTREAM_VERIFIERS.get(t.provider)
    if not verifier:
        t.note = "no upstream verifier for provider; not counted as harvested"
        return
    status = verifier(t.token)
    t.upstream_status = status
    t.upstream_verified = status == 200
    if t.upstream_verified:
        log(f"Upstream VERIFIED 200 OK: {t.provider} ({t.source}, {mask_token(t.token)})", "ok")
    else:
        log(f"Upstream NOT verified: {t.provider} status={status} ({t.source})", "warn")


def inject_verified(api: OmniRouteAPI, connections: List[Dict[str, Any]],
                     tokens: List[HarvestedToken], dry_run: bool = False) -> None:
    by_provider: Dict[str, List[Dict[str, Any]]] = {}
    for c in connections:
        by_provider.setdefault(c.get("provider", ""), []).append(c)

    for t in tokens:
        if not t.upstream_verified:
            continue
        candidates = by_provider.get(t.provider, [])
        apikey_conns = [c for c in candidates if c.get("authType") == "apikey"]
        if not apikey_conns:
            t.note = "no apikey connection in OmniRoute for provider; skipped (OAuth connections not touched)"
            log(f"{t.provider}: {t.note}", "skip")
            continue
        # prefer an existing connection for this provider
        conn = apikey_conns[0]
        cid = conn.get("id")
        if conn.get("isActive") and conn.get("testStatus") == "active" and conn.get("apiKey"):
            t.note = "connection already active with key; idempotent skip"
            t.injected_connection = cid
            log(f"{t.provider}: {t.note}", "skip")
            continue
        if dry_run:
            t.note = "dry-run: would inject"
            t.injected_connection = cid
            continue
        res = api.update_connection(cid, {"apiKey": t.token})
        t.injected_connection = cid
        t.injection_status = res.get("http_status")
        if t.injection_status == 200:
            log(f"Injected key into {t.provider} connection {str(cid)[:8]}...", "ok")
            test = api.test_connection(cid)
            result = test.get("result", {}) or {}
            t.test_valid = bool(result.get("valid"))
            t.note = f"test status={test.get('http_status')} valid={t.test_valid}"
            log(f"{t.provider} post-injection test: valid={t.test_valid}", "ok" if t.test_valid else "warn")
        else:
            t.note = f"injection failed HTTP {t.injection_status}"
            log(f"{t.provider}: {t.note}", "err")


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Tier 1 CLI token harvester")
    p.add_argument("--dry-run", action="store_true", help="verify only, no injection")
    args = p.parse_args()

    log("=== TIER 1: CLI & RUNTIME TOKEN HARVEST ===")
    tokens = harvest_all()
    log(f"Harvested {len(tokens)} unique candidate tokens from local stores")

    if not tokens:
        log("No local tokens found; nothing to do", "skip")
        save_json("harvest_result.json", {"tokens": [], "summary": {"harvested": 0}})
        return 0

    for t in tokens:
        verify_upstream(t)

    verified = [t for t in tokens if t.upstream_verified]
    log(f"Upstream-verified tokens: {len(verified)} / {len(tokens)}")

    injected = 0
    if verified:
        api = OmniRouteAPI()
        if api.login():
            connections = api.get_connections()
            log(f"OmniRoute connections: {len(connections)}")
            inject_verified(api, connections, tokens, dry_run=args.dry_run)
            injected = sum(1 for t in verified if t.test_valid)
        else:
            log("Management login unavailable; verification-only run", "warn")

    summary = {
        "harvested": len(tokens),
        "upstream_verified": len(verified),
        "injected_and_tested_ok": injected,
        "dry_run": args.dry_run,
    }
    save_json("harvest_result.json", {
        "summary": summary,
        "tokens": [t.redacted() for t in tokens],
    })
    log(f"Harvest complete: {json.dumps(summary)}", "ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
