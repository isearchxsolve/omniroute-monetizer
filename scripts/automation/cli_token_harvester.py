import os
import json
import subprocess
import requests
import re
from typing import Dict, List, Optional

OMNIROUTE_API = "http://localhost:20128/api"
OMNIROUTE_V1 = "http://localhost:20128/v1"

def get_github_cli_token() -> Optional[str]:
    try:
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            token = res.stdout.strip()
            if token:
                return token
    except Exception:
        pass
    
    # Check hosts.yml fallback
    gh_hosts_path = os.path.expanduser("~/.config/gh/hosts.yml")
    if os.path.exists(gh_hosts_path):
        try:
            with open(gh_hosts_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "oauth_token:" in line:
                        return line.split("oauth_token:")[1].strip()
        except:
            pass
    return None

def get_zed_tokens() -> List[str]:
    tokens = []
    zed_settings_path = os.path.expandvars(r"%APPDATA%\Zed\settings.json")
    if os.path.exists(zed_settings_path):
        try:
            with open(zed_settings_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Find any raw tokens in settings (though Zed usually uses Windows Credential Manager)
                matches = re.findall(r'sk-[a-zA-Z0-9_\-]{20,}', content)
                tokens.extend(matches)
        except:
            pass
    return list(set(tokens))

def get_codex_tokens() -> List[str]:
    tokens = []
    codex_paths = [os.path.expanduser("~/.codex/config.json"), os.path.expanduser("~/.codex/config.toml")]
    for path in codex_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    matches = re.findall(r'sk-[a-zA-Z0-9_\-]{20,}', content)
                    tokens.extend(matches)
            except:
                pass
    return list(set(tokens))

def get_env_tokens() -> Dict[str, str]:
    tokens = {}
    target_envs = ["OPENROUTER_API_KEY", "NVIDIA_API_KEY", "OPENCODE_API_KEY", 
                   "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN", 
                   "CEREBRAS_API_KEY", "COHERE_API_KEY", "GROK_API_KEY"]
    for env in target_envs:
        val = os.environ.get(env)
        if val and len(val) > 10:
            tokens[env] = val
    return tokens

def harvest_all_tokens() -> List[str]:
    all_tokens = set()
    
    gh_token = get_github_cli_token()
    if gh_token:
        all_tokens.add(gh_token)
        
    for t in get_zed_tokens():
        all_tokens.add(t)
        
    for t in get_codex_tokens():
        all_tokens.add(t)
        
    for t in get_env_tokens().values():
        all_tokens.add(t)
        
    return list(all_tokens)

def identify_provider(token: str) -> Optional[str]:
    if token.startswith("ghp_") or token.startswith("gho_"):
        return "github"
    if token.startswith("sk-ant"):
        return "anthropic"
    if token.startswith("sk-or-"):
        return "openrouter"
    if token.startswith("sk-proj-"):
        return "openai"
    # Fallback to test against endpoints or manual mapping
    return None

def main():
    print("Starting CLI & Runtime Token Harvest (Tier 1)...")
    tokens = harvest_all_tokens()
    print(f"Harvested {len(tokens)} unique tokens from local runtime.")
    
    if not tokens:
        print("No tokens found via local zero-DOM path.")
        return
        
    print("\nNote: OmniRoute injection and verification logic would run here.")
    print("For safety during dry-run, we won't mutate OmniRoute state automatically.")
    
    for t in tokens:
        provider = identify_provider(t)
        masked = t[:6] + "..." + t[-4:] if len(t) > 10 else t
        print(f" - Found {masked} (Identified Provider: {provider or 'Unknown'})")

if __name__ == "__main__":
    main()
