"""Current non-spending eligibility, separate from historical video admission.

Read failures mean unavailable to this executor, never proof a provider is dead.
Browser seats need an owned executor integration; no operator browser is borrowed.
"""
from __future__ import annotations
import math
import threading
import time
import requests


class VideoSeatHealth:
    def __init__(self, ttl=60):
        self.ttl = ttl
        self._cache = {}
        self._lock = threading.RLock()

    def check(self, seat):
        try:
            key = (str(seat.path), seat.path.stat().st_mtime_ns)
        except OSError:
            return {"ready":False,"capacity_verified":False,"credits_remaining":None,
                    "clips_remaining":None,"reason":"seat_file_unavailable","checked_at":time.time()}
        with self._lock:
            old = self._cache.get(key)
            if old and time.monotonic() - old[0] < self.ttl:
                return dict(old[1])
            result = {"ready": False, "capacity_verified": False,
                      "credits_remaining": None, "clips_remaining": None}
            try:
                if not seat.stateless:
                    result["reason"] = "owned_browser_executor_not_verified"
                else:
                    client = seat.client()
                    if seat.host == "digen.ai":
                        r = requests.get("https://api.digen.ai/v1/credit/remain",
                                         headers=client._headers, timeout=10)
                        r.raise_for_status()
                        body = r.json()
                        data = body.get("data") or {}
                        # Never estimate a render count from an assumed per-clip cost.
                        values = [float(data[k]) for k in ("remained", "premiumRemained") if k in data]
                        if body.get("errCode") != 0 or not values or not all(math.isfinite(v) and v >= 0 for v in values):
                            raise ValueError("balance_schema")
                        balance = sum(values)
                        result.update(ready=balance > 0, credits_remaining=balance,
                                      reason="positive_balance_unquoted" if balance else "balance_exhausted")
                    elif seat.host == "rtst.ai":
                        data = client._call("/user/credits", timeout=10)
                        balance = float(data["credits"])
                        if not math.isfinite(balance) or balance < 0:
                            raise ValueError("balance_schema")
                        result.update(ready=balance > 0, credits_remaining=balance,
                                      reason="positive_balance_unquoted" if balance else "balance_exhausted")
                    elif seat.host == "lightricks-ltx-video-distilled.hf.space":
                        from gradio_space_client import GradioSpaceClient
                        info = GradioSpaceClient(client.base, timeout=10).info()
                        endpoint = (info.get("named_endpoints") or {}).get("/text_to_video")
                        ready = isinstance(endpoint, dict) and len(endpoint.get("parameters") or []) == 13
                        result.update(ready=ready, reason="endpoint_contract_read" if ready else "endpoint_contract_changed")
                    else:
                        result["reason"] = "readiness_contract_not_implemented"
            except Exception as exc:
                # Exception text can contain request headers or signed URLs. Keep only type/status.
                response = getattr(exc, "response", None)
                result.update(reason="readiness_read_failed", error_type=type(exc).__name__)
                if response is not None:
                    result["http_status"] = response.status_code
            result["checked_at"] = time.time()
            self._cache[key] = (time.monotonic(), dict(result))
            return result

    def invalidate(self, seat):
        with self._lock:
            for key in list(self._cache):
                if key[0] == str(seat.path):
                    self._cache.pop(key, None)
