import os
import sys
from pathlib import Path

# Add project root to sys.path so we can import scripts
sys.path.append(r"D:\omniroute-monetizer")

from scripts.automation.provider_browser_engine import ProviderBrowserEngine

def fix_providers():
    print("=== FORCING RE-AUTH VIA BROWSER ENGINE ===")
    
    artifact_dir = Path(r"D:\omniroute-monetizer\state\browser_automation")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    engine = ProviderBrowserEngine(artifact_dir=artifact_dir, headless=True)
    
    providers_to_fix = [
        "lmarena", 
        "qoder", 
        "codex", 
        "amazon-q", 
        "cerebras", 
        "zai-web", 
        "antigravity"
    ]
    
    success_count = 0
    for p in providers_to_fix:
        print(f"\n[*] Initiating browser repair for: {p}")
        try:
            # safe_reauth_probe orchestrates the browser to re-login / fetch new cookies
            result = engine.safe_reauth_probe(p)
            sanitized = result.sanitized()
            status = sanitized.get('status')
            stage = sanitized.get('stage')
            
            if status in ["DISCOVERED", "HANDOFF"]:
                print(f"[+] SUCCESS! {p} is fixed. Status: {status} at stage: {stage}")
                success_count += 1
            else:
                print(f"[-] FAILED to fix {p}. Status: {status} at stage: {stage}")
                print(f"    Details: {sanitized.get('error', 'Unknown')}")
        except Exception as e:
            print(f"[-] ERROR during browser repair of {p}: {e}")

    print(f"\n=== BROWSER REPAIR COMPLETE. Fixed {success_count}/{len(providers_to_fix)} providers. ===")

if __name__ == "__main__":
    fix_providers()
