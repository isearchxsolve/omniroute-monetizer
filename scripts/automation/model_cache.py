"""
ModelCatalogCache - TTL-based caching for /v1/models endpoint

Purpose: Reduce model catalog latency from 30-60s (uncached) to <100ms (cached).
Pattern: In-memory TTL cache with optional disk persistence for recovery.
Integration: Used by OmniRoute API client or orchestrator before calling /v1/models.

Usage:
    cache = ModelCatalogCache(ttl_seconds=60, cache_file="state/model_cache.json")
    
    # On first call, fetches from API
    models = cache.get_models(fetch_fn=omniroute_api.list_models)
    
    # On subsequent calls within TTL, returns cached result
    models = cache.get_models(fetch_fn=omniroute_api.list_models)
    
    # When combos are updated, invalidate
    cache.invalidate()
"""

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class ModelCatalogCache:
    """TTL-based cache for OmniRoute model catalog."""
    
    def __init__(self, ttl_seconds: int = 60, cache_file: Optional[Path] = None):
        """
        Args:
            ttl_seconds: Time-to-live for cached models (default 60 seconds)
            cache_file: Optional file path for persistent cache (e.g. "state/model_cache.json")
        """
        self.ttl = ttl_seconds
        self.data: List[Dict[str, Any]] = []
        self.last_update: float = 0
        self.cache_file = cache_file or Path("state/model_cache.json")
        self._load_cache()
    
    def is_valid(self) -> bool:
        """Check if cached data is still within TTL."""
        if not self.data:
            return False
        age = time.time() - self.last_update
        return age < self.ttl
    
    def get_models(self, fetch_fn: Callable[[], List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Get models from cache if valid, otherwise fetch and cache.
        
        Args:
            fetch_fn: Callable that fetches fresh model list from /v1/models
        
        Returns:
            List of model dictionaries
        """
        if self.is_valid():
            return self.data
        
        # Fetch fresh data
        try:
            self.data = fetch_fn()
            self.last_update = time.time()
            self._save_cache()
            return self.data
        except Exception as e:
            print(f"[MODEL_CACHE] Fetch failed: {e}; returning stale cache if available")
            return self.data  # Return stale cache as fallback
    
    def invalidate(self):
        """Clear cache (called after PUT /api/combos updates)."""
        self.data = []
        self.last_update = 0
        print(f"[MODEL_CACHE] Invalidated (TTL expired or combos updated)")
    
    def _save_cache(self):
        """Persist cache to disk for recovery across restarts."""
        try:
            if self.cache_file:
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_data = {
                    "timestamp": self.last_update,
                    "ttl": self.ttl,
                    "models": self.data
                }
                with open(self.cache_file, "w") as f:
                    json.dump(cache_data, f, indent=2)
                print(f"[MODEL_CACHE] Saved {len(self.data)} models to {self.cache_file}")
        except Exception as e:
            print(f"[MODEL_CACHE] Failed to save cache: {e}")
    
    def _load_cache(self):
        """Load cached models from disk if available."""
        try:
            if self.cache_file and self.cache_file.exists():
                with open(self.cache_file, "r") as f:
                    cache_data = json.load(f)
                    self.data = cache_data.get("models", [])
                    self.last_update = cache_data.get("timestamp", 0)
                    ttl = cache_data.get("ttl", self.ttl)
                    
                    age = time.time() - self.last_update
                    if age < ttl:
                        print(f"[MODEL_CACHE] Loaded {len(self.data)} valid cached models (age {age:.1f}s)")
                    else:
                        print(f"[MODEL_CACHE] Loaded cache but data stale (age {age:.1f}s > ttl {ttl}s); will refresh")
                        self.data = []  # Invalidate stale cache
        except Exception as e:
            print(f"[MODEL_CACHE] Failed to load cache: {e}")


# Integration example (add to omniroute_api.py or orchestrator):
"""
# At module level:
model_cache = ModelCatalogCache(ttl_seconds=60, cache_file=Path("state/model_cache.json"))

# Replace omniroute_api.list_models() calls with cached version:
def list_models_cached():
    return model_cache.get_models(fetch_fn=list_models)

# After updating combos (PUT /api/combos), invalidate:
def update_combo(combo_id: str, payload: Dict) -> bool:
    result = omniroute_api.update_combo(combo_id, payload)
    if result:
        model_cache.invalidate()  # Clear cache after combo update
    return result
"""
