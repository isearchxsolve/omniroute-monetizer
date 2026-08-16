"""
ProviderHealthChecker - Background health monitoring for provider credentials

Purpose: Detect stale/inactive provider credentials before inference requests fail.
Pattern: Background daemon thread that periodically tests all providers and marks stale ones.
Integration: Started by orchestrator.run_all() or app startup; runs continuously in background.

Usage:
    health_checker = ProviderHealthChecker(
        api_client=omniroute_api,
        check_interval_seconds=60,
        timeout_seconds=5
    )
    health_checker.start()
    
    # ... later, check if provider is stale:
    if "nvidia_provider_id" in health_checker.get_stale_providers():
        print("NVIDIA is inactive; needs key rotation")
    
    health_checker.stop()
"""

import threading
import time
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import json
from pathlib import Path


@dataclass
class ProviderHealthStatus:
    """Status of a single provider's health check."""
    provider_id: str
    provider_name: str
    last_check: float  # timestamp
    is_healthy: bool
    error_message: str = ""
    test_latency_ms: float = 0.0
    consecutive_failures: int = 0


class ProviderHealthChecker:
    """Monitor provider health in background thread."""
    
    def __init__(
        self,
        api_client,
        check_interval_seconds: int = 60,
        timeout_seconds: int = 5,
        max_consecutive_failures: int = 3,
        health_log_file: Optional[Path] = None
    ):
        """
        Args:
            api_client: OmniRoute API client (omniroute_api.OmniRouteAPI)
            check_interval_seconds: How often to check each provider (default 60s)
            timeout_seconds: Test timeout per provider (default 5s)
            max_consecutive_failures: Mark as stale after N consecutive test failures
            health_log_file: Optional file to persist health history (e.g. "state/health_log.json")
        """
        self.api_client = api_client
        self.check_interval = check_interval_seconds
        self.timeout = timeout_seconds
        self.max_failures = max_consecutive_failures
        self.health_log_file = health_log_file or Path("state/health_log.json")
        
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.health_status: Dict[str, ProviderHealthStatus] = {}
        self.stale_providers: Set[str] = set()
        self.lock = threading.Lock()
    
    def start(self):
        """Start background health check thread."""
        if self.running:
            print("[HEALTH_CHECKER] Already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print("[HEALTH_CHECKER] Started background health monitoring")
    
    def stop(self):
        """Stop background health check thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("[HEALTH_CHECKER] Stopped")
    
    def get_stale_providers(self) -> Set[str]:
        """Get set of provider IDs that are currently unhealthy."""
        with self.lock:
            return self.stale_providers.copy()
    
    def get_health_status(self, provider_id: str) -> Optional[ProviderHealthStatus]:
        """Get detailed health status for a single provider."""
        with self.lock:
            return self.health_status.get(provider_id)
    
    def get_all_health(self) -> Dict[str, ProviderHealthStatus]:
        """Get health status for all providers."""
        with self.lock:
            return {pid: asdict(status) for pid, status in self.health_status.items()}
    
    def _loop(self):
        """Background health check loop (runs in daemon thread)."""
        print("[HEALTH_CHECKER] Health check loop started")
        
        while self.running:
            try:
                # Get all providers
                connections = self.api_client.get_connections()
                if not connections:
                    time.sleep(self.check_interval)
                    continue
                
                # Test each provider
                for conn in connections:
                    if not self.running:
                        break
                    
                    provider_id = conn.get("id")
                    provider_name = conn.get("provider", "unknown")
                    
                    self._test_provider(provider_id, provider_name, conn)
                
                # Save health log
                self._save_health_log()
                
            except Exception as e:
                print(f"[HEALTH_CHECKER] Loop error: {e}")
            
            time.sleep(self.check_interval)
    
    def _test_provider(self, provider_id: str, provider_name: str, connection: Dict):
        """Test a single provider connection."""
        try:
            start = time.time()
            
            # Call provider test endpoint
            is_valid = self.api_client.test_connection(provider_id, timeout=self.timeout)
            
            latency_ms = (time.time() - start) * 1000
            
            with self.lock:
                if provider_id not in self.health_status:
                    self.health_status[provider_id] = ProviderHealthStatus(
                        provider_id=provider_id,
                        provider_name=provider_name,
                        last_check=time.time(),
                        is_healthy=False
                    )
                
                status = self.health_status[provider_id]
                status.last_check = time.time()
                status.test_latency_ms = latency_ms
                
                if is_valid:
                    # Health check passed
                    status.is_healthy = True
                    status.consecutive_failures = 0
                    if provider_id in self.stale_providers:
                        print(f"[HEALTH_CHECKER] {provider_name} recovered (now healthy)")
                        self.stale_providers.discard(provider_id)
                else:
                    # Health check failed
                    status.consecutive_failures += 1
                    if status.consecutive_failures >= self.max_failures:
                        status.is_healthy = False
                        if provider_id not in self.stale_providers:
                            print(f"[HEALTH_CHECKER] {provider_name} marked STALE (after {self.max_failures} failures)")
                            self.stale_providers.add(provider_id)
        
        except Exception as e:
            with self.lock:
                if provider_id not in self.health_status:
                    self.health_status[provider_id] = ProviderHealthStatus(
                        provider_id=provider_id,
                        provider_name=provider_name,
                        last_check=time.time(),
                        is_healthy=False,
                        error_message=str(e)
                    )
                else:
                    self.health_status[provider_id].error_message = str(e)
                    self.health_status[provider_id].consecutive_failures += 1
                    
                    if self.health_status[provider_id].consecutive_failures >= self.max_failures:
                        self.stale_providers.add(provider_id)
                        print(f"[HEALTH_CHECKER] {provider_name} exception after {self.max_failures} attempts: {e}")
    
    def _save_health_log(self):
        """Persist health status to disk."""
        try:
            with self.lock:
                health_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "stale_providers": list(self.stale_providers),
                    "all_status": {
                        pid: asdict(status)
                        for pid, status in self.health_status.items()
                    }
                }
            
            self.health_log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.health_log_file, "w") as f:
                json.dump(health_data, f, indent=2)
        
        except Exception as e:
            print(f"[HEALTH_CHECKER] Failed to save health log: {e}")


# Integration example (add to orchestrator.py):
"""
# At module level:
health_checker = None

def start_health_monitoring():
    global health_checker
    health_checker = ProviderHealthChecker(
        api_client=omniroute_api,
        check_interval_seconds=60,
        timeout_seconds=5
    )
    health_checker.start()

def stop_health_monitoring():
    global health_checker
    if health_checker:
        health_checker.stop()

# In run_all():
start_health_monitoring()
try:
    # ... do automation work ...
finally:
    stop_health_monitoring()

# Before injecting a model into combo, check if provider is stale:
stale = health_checker.get_stale_providers()
if provider_id in stale:
    print(f"Warning: {provider_name} is stale; may skip or attempt recovery")
"""
