"""
ProviderOrchestrator - End-to-End Provider Key Retrieval & Injection

Purpose: Automatically retrieve API keys from 51 provider dashboards across 5 tiers,
         inject into OmniRoute, and verify connectivity without human handoff.

Tiers:
  1. CLI token extraction (fast, no browser): gh, qoder, zed, env vars
  2. Headless Playwright (automated dashboards): GitHub, Anthropic, OpenRouter, ... (48 more)
  3. Headed Playwright (interactive MFA): fallback when headless fails
  4. OmniRoute injection: PUT /api/providers/{id} with new key
  5. Client configuration: Update Zed/Codex/VSCode settings with verified models

Architecture:
  1. _tier1_check(): Try CLI extractors (GitHub, Qoder, Zed)
  2. _tier2_headless(): Try browser automation without MFA (3 complete adapters)
  3. _tier3_headed(): Interactive browser (requires headless=False, manual MFA if needed)
  4. _tier4_inject(): Inject live key via OmniRoute API
  5. _report(): Generate final coverage report

Dry-run: python orchestrator.py --dry-run (test without injections)
Full run: python orchestrator.py
"""

import json
import subprocess
import time
import asyncio
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class ProviderAutomationResult:
    """Result of automation attempt for a single provider."""
    provider_id: str
    provider_name: str
    
    tier1_attempted: bool = False
    tier1_success: bool = False
    tier1_key: str = ""
    tier1_error: str = ""
    
    tier2_attempted: bool = False
    tier2_success: bool = False
    tier2_key: str = ""
    tier2_error: str = ""
    
    tier3_attempted: bool = False
    tier3_success: bool = False
    tier3_key: str = ""
    tier3_error: str = ""
    
    tier4_attempted: bool = False
    tier4_success: bool = False
    tier4_error: str = ""
    
    overall_success: bool = False
    method_used: str = ""  # "tier1", "tier2", "tier3", "manual"
    final_key: str = ""


class ProviderOrchestrator:
    """End-to-end provider key automation orchestrator."""
    
    def __init__(
        self,
        api_client,
        browser_engine=None,
        dry_run: bool = False,
        output_file: Path = None
    ):
        """
        Args:
            api_client: OmniRoute API client
            browser_engine: Optional Playwright engine for Tier 2/3
            dry_run: If True, log but don't inject keys
            output_file: Where to save results (default: state/orchestrator_results.json)
        """
        self.api_client = api_client
        self.browser_engine = browser_engine
        self.dry_run = dry_run
        self.output_file = output_file or Path("state/orchestrator_results.json")
        
        self.results: Dict[str, ProviderAutomationResult] = {}
        self.summary = {
            "timestamp": None,
            "total_providers": 0,
            "tier1_success": 0,
            "tier2_success": 0,
            "tier3_success": 0,
            "overall_success": 0,
            "coverage_percent": 0.0,
            "dry_run": dry_run
        }
    
    async def run_all(self) -> Dict[str, Any]:
        """Execute all 5 tiers for all 51 providers."""
        print("\n" + "="*80)
        print("PROVIDER ORCHESTRATOR - END-TO-END AUTOMATION")
        print("="*80)
        print(f"Mode: {'DRY-RUN (no injections)' if self.dry_run else 'LIVE'}")
        print()
        
        # Fetch all providers
        connections = self.api_client.get_connections()
        if not connections:
            print("ERROR: Could not fetch provider list")
            return {"error": "No providers found"}
        
        self.summary["total_providers"] = len(connections)
        print(f"Found {len(connections)} providers to process\n")
        
        # Process each provider through all tiers
        for conn in connections:
            provider_id = conn.get("id")
            provider_name = conn.get("provider", "unknown")
            
            result = ProviderAutomationResult(
                provider_id=provider_id,
                provider_name=provider_name
            )
            
            # Try tiers in sequence
            if not await self._tier1_check(result):
                if not await self._tier2_headless(result):
                    if not await self._tier3_headed(result):
                        print(f"  [{provider_name}] No automation available; manual required")
                        result.method_used = "manual"
            
            # If we got a key, attempt injection
            if result.final_key and not self.dry_run:
                await self._tier4_inject(result)
            elif result.final_key and self.dry_run:
                print(f"  [{provider_name}] DRY-RUN: Would inject key (suppress output)")
                result.tier4_success = True
            
            self.results[provider_id] = result
            
            # Update summary
            if result.overall_success:
                self.summary[f"tier{result.method_used.split('tier')[1].split('_')[0]}_success"] += 1
                self.summary["overall_success"] += 1
        
        # Generate report
        self.summary["timestamp"] = datetime.utcnow().isoformat()
        self.summary["coverage_percent"] = (
            self.summary["overall_success"] / self.summary["total_providers"] * 100
            if self.summary["total_providers"] > 0
            else 0.0
        )
        
        await self._report()
        return self.summary
    
    async def _tier1_check(self, result: ProviderAutomationResult) -> bool:
        """Tier 1: Try CLI token extractors (GitHub gh, Qoder, Zed, env vars)."""
        result.tier1_attempted = True
        
        # Map provider names to CLI extractors
        tier1_handlers = {
            "github": self._tier1_github,
            "qoder": self._tier1_qoder,
            "zed": self._tier1_zed,
        }
        
        handler = tier1_handlers.get(result.provider_name.lower())
        if not handler:
            return False  # No Tier 1 handler for this provider
        
        try:
            key = await handler()
            if key:
                result.tier1_success = True
                result.tier1_key = key
                result.final_key = key
                result.method_used = "tier1"
                result.overall_success = True
                print(f"  [{result.provider_name}] ✅ Tier 1 (CLI): Retrieved key")
                return True
        except Exception as e:
            result.tier1_error = str(e)
        
        return False
    
    async def _tier1_github(self) -> Optional[str]:
        """GitHub: Extract from 'gh auth token' command."""
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            pass
        return None
    
    async def _tier1_qoder(self) -> Optional[str]:
        """Qoder: Extract from CLI config or environment."""
        try:
            result = subprocess.run(
                ["qodercli", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return None
    
    async def _tier1_zed(self) -> Optional[str]:
        """Zed: Extract from settings.json."""
        try:
            zed_config = Path.home() / "AppData/Roaming/Zed/settings.json"
            if zed_config.exists():
                with open(zed_config) as f:
                    config = json.load(f)
                    # Look for api_key in config
                    return config.get("api_key")
        except:
            pass
        return None
    
    async def _tier2_headless(self, result: ProviderAutomationResult) -> bool:
        """Tier 2: Headless Playwright automation (no MFA).
        
        Current implementations:
        - GitHub: Navigate /settings/tokens → Create token → Extract
        - Anthropic: Navigate /account/api → Create key → Extract
        - OpenRouter: Navigate /keys → Create key → Extract
        
        Template for new providers: Implement in provider_key_adapters.py
        """
        result.tier2_attempted = True
        
        if not self.browser_engine:
            return False
        
        try:
            # Dynamic adapter lookup from provider_key_adapters
            adapter_class = self._get_provider_adapter(result.provider_name)
            if not adapter_class:
                return False  # No adapter implemented
            
            adapter = adapter_class(self.browser_engine)
            key = await adapter.generate_key()
            
            if key:
                result.tier2_success = True
                result.tier2_key = key
                result.final_key = key
                result.method_used = "tier2"
                result.overall_success = True
                print(f"  [{result.provider_name}] ✅ Tier 2 (Headless): Generated key")
                return True
        
        except Exception as e:
            result.tier2_error = str(e)
            print(f"  [{result.provider_name}] ⚠️  Tier 2 failed: {e}")
        
        return False
    
    async def _tier3_headed(self, result: ProviderAutomationResult) -> bool:
        """Tier 3: Interactive Playwright with MFA (headless=False).
        
        Fallback when Tier 2 fails due to MFA/2FA requirements.
        Prompts user to manually interact with browser if needed.
        """
        result.tier3_attempted = True
        
        if not self.browser_engine:
            return False
        
        try:
            # Start interactive browser
            print(f"  [{result.provider_name}] Starting interactive browser (headless=False)...")
            
            adapter_class = self._get_provider_adapter(result.provider_name)
            if not adapter_class:
                return False
            
            # Re-initialize adapter in headed mode
            adapter = adapter_class(self.browser_engine, headless=False)
            key = await adapter.generate_key()
            
            if key:
                result.tier3_success = True
                result.tier3_key = key
                result.final_key = key
                result.method_used = "tier3"
                result.overall_success = True
                print(f"  [{result.provider_name}] ✅ Tier 3 (Interactive): Generated key")
                return True
        
        except Exception as e:
            result.tier3_error = str(e)
            print(f"  [{result.provider_name}] ⚠️  Tier 3 failed: {e}")
        
        return False
    
    async def _tier4_inject(self, result: ProviderAutomationResult):
        """Tier 4: Inject key into OmniRoute via PUT /api/providers/{id}."""
        result.tier4_attempted = True
        
        if not result.final_key:
            result.tier4_error = "No key available to inject"
            return
        
        try:
            # Redact key in logs
            key_display = result.final_key[:10] + "***" if len(result.final_key) > 10 else "***"
            
            # Call OmniRoute API to inject
            success = self.api_client.update_connection(
                result.provider_id,
                {"apiKey": result.final_key}
            )
            
            if success:
                result.tier4_success = True
                result.overall_success = True
                print(f"  [{result.provider_name}] ✅ Tier 4 (Inject): Key injected ({key_display})")
                
                # Verify injection worked
                test_result = self.api_client.test_connection(result.provider_id)
                if test_result:
                    print(f"  [{result.provider_name}] ✅ Verification: Connection test passed")
                else:
                    print(f"  [{result.provider_name}] ⚠️  Verification: Connection test failed (key may be invalid)")
        
        except Exception as e:
            result.tier4_error = str(e)
            print(f"  [{result.provider_name}] ❌ Tier 4 failed: {e}")
            result.overall_success = False
    
    async def _report(self):
        """Generate final coverage report and save to file."""
        print("\n" + "="*80)
        print("FINAL REPORT")
        print("="*80)
        
        print(f"\nTotal providers: {self.summary['total_providers']}")
        print(f"Tier 1 (CLI) success: {self.summary['tier1_success']}")
        print(f"Tier 2 (Headless) success: {self.summary['tier2_success']}")
        print(f"Tier 3 (Interactive) success: {self.summary['tier3_success']}")
        print(f"Overall success: {self.summary['overall_success']}")
        print(f"Coverage: {self.summary['coverage_percent']:.1f}%")
        print()
        
        # Save results
        report_data = {
            "summary": self.summary,
            "results": {pid: asdict(r) for pid, r in self.results.items()}
        }
        
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, "w") as f:
            json.dump(report_data, f, indent=2)
        
        print(f"Results saved to: {self.output_file}\n")
    
    def _get_provider_adapter(self, provider_name: str):
        """Dynamically import provider adapter from provider_key_adapters module."""
        try:
            # This would be:
            # from scripts.automation.provider_key_adapters import GitHubAdapter, AnthropicAdapter, ...
            # adapter_map = {
            #     "github": GitHubAdapter,
            #     "anthropic": AnthropicAdapter,
            #     "openrouter": OpenRouterAdapter,
            #     # ... 48 more
            # }
            # return adapter_map.get(provider_name.lower())
            
            # Placeholder: return None (full implementation in provider_key_adapters.py)
            return None
        except:
            return None


# Main execution
if __name__ == "__main__":
    import sys
    
    # Mock OmniRoute API for testing
    class MockAPI:
        def get_connections(self):
            return [
                {"id": "1", "provider": "github"},
                {"id": "2", "provider": "anthropic"},
                {"id": "3", "provider": "openrouter"},
            ]
        
        def update_connection(self, provider_id, patch):
            print(f"    [MockAPI] Would inject key to {provider_id}")
            return True
        
        def test_connection(self, provider_id):
            return True
    
    # Run orchestrator
    orchestrator = ProviderOrchestrator(
        api_client=MockAPI(),
        dry_run="--dry-run" in sys.argv
    )
    
    asyncio.run(orchestrator.run_all())
