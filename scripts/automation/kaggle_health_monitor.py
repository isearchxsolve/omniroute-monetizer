#!/usr/bin/env python3
"""
Kaggle Health Monitoring & Alerting — Observability for 5-Account Rotation

Provides:
- Real-time health endpoint with detailed metrics
- Rotation event logging (activation, pre-warm, expiry, failover)
- Prometheus-compatible metrics export
- Alerting hooks for critical events (no healthy accounts, auth failures, etc.)
- Integration with existing OmniRoute monitoring
"""
from __future__ import annotations
import json
import pathlib
import threading
import time
import logging
from collections import deque
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
METRICS_FILE = STATE_DIR / "kaggle_metrics.json"
EVENT_LOG_FILE = STATE_DIR / "kaggle_events.jsonl"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("kaggle.monitor")


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RotationEventType(Enum):
    ACCOUNT_ACTIVATED = "account_activated"
    ACCOUNT_PREWARMED = "account_prewarmed"
    ACCOUNT_EXPIRED = "account_expired"
    ACCOUNT_ERROR = "account_error"
    ROTATION_COMPLETED = "rotation_completed"
    FAILOVER_TRIGGERED = "failover_triggered"
    NO_HEALTHY_ACCOUNTS = "no_healthy_accounts"
    AUTH_FAILURE = "auth_failure"
    RATE_LIMITED = "rate_limited"
    PREWARM_FAILED = "prewarm_failed"


@dataclass
class RotationEvent:
    """A single rotation lifecycle event."""
    event_type: RotationEventType
    account_id: str
    timestamp: float = field(default_factory=time.time)
    level: AlertLevel = AlertLevel.INFO
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['event_type'] = self.event_type.value
        d['level'] = self.level.value
        d['timestamp_iso'] = datetime.fromtimestamp(self.timestamp).isoformat()
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RotationEvent':
        data = data.copy()
        data['event_type'] = RotationEventType(data['event_type'])
        data['level'] = AlertLevel(data['level'])
        return cls(**data)


@dataclass
class HealthMetrics:
    """Aggregated health metrics for Prometheus export."""
    # Account states
    total_accounts: int = 0
    active_accounts: int = 0
    healthy_accounts: int = 0
    pending_accounts: int = 0
    error_accounts: int = 0
    
    # Request metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    auth_failures: int = 0
    rate_limits: int = 0
    
    # Rotation metrics
    rotations_completed: int = 0
    prewarms_initiated: int = 0
    prewarms_failed: int = 0
    failovers_triggered: int = 0
    
    # Latency metrics (seconds)
    avg_request_latency: float = 0.0
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    
    # Window metrics
    avg_window_utilization: float = 0.0  # fraction of 12h window used
    min_time_remaining: float = 0.0  # seconds
    
    # Timestamp
    updated_at: float = field(default_factory=time.time)
    
    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = [
            "# HELP kaggle_total_accounts Total number of configured accounts",
            "# TYPE kaggle_total_accounts gauge",
            f"kaggle_total_accounts {self.total_accounts}",
            "",
            "# HELP kaggle_active_accounts Number of currently active accounts",
            "# TYPE kaggle_active_accounts gauge",
            f"kaggle_active_accounts {self.active_accounts}",
            "",
            "# HELP kaggle_healthy_accounts Number of healthy accounts (active + prewarming + expiring)",
            "# TYPE kaggle_healthy_accounts gauge",
            f"kaggle_healthy_accounts {self.healthy_accounts}",
            "",
            "# HELP kaggle_pending_accounts Number of pending accounts",
            "# TYPE kaggle_pending_accounts gauge",
            f"kaggle_pending_accounts {self.pending_accounts}",
            "",
            "# HELP kaggle_error_accounts Number of accounts in error state",
            "# TYPE kaggle_error_accounts gauge",
            f"kaggle_error_accounts {self.error_accounts}",
            "",
            "# HELP kaggle_total_requests_total Total requests served",
            "# TYPE kaggle_total_requests_total counter",
            f"kaggle_total_requests_total {self.total_requests}",
            "",
            "# HELP kaggle_successful_requests_total Successful requests",
            "# TYPE kaggle_successful_requests_total counter",
            f"kaggle_successful_requests_total {self.successful_requests}",
            "",
            "# HELP kaggle_failed_requests_total Failed requests",
            "# TYPE kaggle_failed_requests_total counter",
            f"kaggle_failed_requests_total {self.failed_requests}",
            "",
            "# HELP kaggle_auth_failures_total Authentication failures",
            "# TYPE kaggle_auth_failures_total counter",
            f"kaggle_auth_failures_total {self.auth_failures}",
            "",
            "# HELP kaggle_rate_limits_total Rate limit hits",
            "# TYPE kaggle_rate_limits_total counter",
            f"kaggle_rate_limits_total {self.rate_limits}",
            "",
            "# HELP kaggle_rotations_completed_total Completed rotations",
            "# TYPE kaggle_rotations_completed_total counter",
            f"kaggle_rotations_completed_total {self.rotations_completed}",
            "",
            "# HELP kaggle_prewarms_initiated_total Pre-warm operations initiated",
            "# TYPE kaggle_prewarms_initiated_total counter",
            f"kaggle_prewarms_initiated_total {self.prewarms_initiated}",
            "",
            "# HELP kaggle_prewarms_failed_total Failed pre-warms",
            "# TYPE kaggle_prewarms_failed_total counter",
            f"kaggle_prewarms_failed_total {self.prewarms_failed}",
            "",
            "# HELP kaggle_failovers_triggered_total Failover events",
            "# TYPE kaggle_failovers_triggered_total counter",
            f"kaggle_failovers_triggered_total {self.failovers_triggered}",
            "",
            "# HELP kaggle_avg_request_latency_seconds Average request latency",
            "# TYPE kaggle_avg_request_latency_seconds gauge",
            f"kaggle_avg_request_latency_seconds {self.avg_request_latency:.4f}",
            "",
            "# HELP kaggle_p50_latency_seconds P50 request latency",
            "# TYPE kaggle_p50_latency_seconds gauge",
            f"kaggle_p50_latency_seconds {self.p50_latency:.4f}",
            "",
            "# HELP kaggle_p95_latency_seconds P95 request latency",
            "# TYPE kaggle_p95_latency_seconds gauge",
            f"kaggle_p95_latency_seconds {self.p95_latency:.4f}",
            "",
            "# HELP kaggle_p99_latency_seconds P99 request latency",
            "# TYPE kaggle_p99_latency_seconds gauge",
            f"kaggle_p99_latency_seconds {self.p99_latency:.4f}",
            "",
            "# HELP kaggle_avg_window_utilization Average window utilization (0-1)",
            "# TYPE kaggle_avg_window_utilization gauge",
            f"kaggle_avg_window_utilization {self.avg_window_utilization:.4f}",
            "",
            "# HELP kaggle_min_time_remaining_seconds Minimum time remaining on any active account",
            "# TYPE kaggle_min_time_remaining_seconds gauge",
            f"kaggle_min_time_remaining_seconds {self.min_time_remaining:.1f}",
        ]
        return "\n".join(lines)


class AlertHandler:
    """Base class for alert handlers."""
    
    def handle_alert(self, event: RotationEvent) -> None:
        raise NotImplementedError


class LogAlertHandler(AlertHandler):
    """Log alerts to structured log file."""
    
    def __init__(self, log_file: pathlib.Path = EVENT_LOG_FILE):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def handle_alert(self, event: RotationEvent) -> None:
        log_entry = {
            "timestamp": event.timestamp,
            "timestamp_iso": datetime.fromtimestamp(event.timestamp).isoformat(),
            "event_type": event.event_type.value,
            "level": event.level.value,
            "account_id": event.account_id,
            "message": event.message,
            "metadata": event.metadata,
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + "\n")


class ConsoleAlertHandler(AlertHandler):
    """Print alerts to console with color coding."""
    
    COLORS = {
        AlertLevel.INFO: "\033[92m",      # Green
        AlertLevel.WARNING: "\033[93m",   # Yellow
        AlertLevel.CRITICAL: "\033[91m",  # Red
    }
    RESET = "\033[0m"
    
    def handle_alert(self, event: RotationEvent) -> None:
        color = self.COLORS.get(event.level, "")
        print(f"{color}[KAGGLE-{event.level.value.upper()}] {event.event_type.value} "
              f"account={event.account_id} msg={event.message}{self.RESET}")


class WebhookAlertHandler(AlertHandler):
    """Send alerts to a webhook URL."""
    
    def __init__(self, webhook_url: str, timeout: float = 10.0):
        self.webhook_url = webhook_url
        self.timeout = timeout
    
    def handle_alert(self, event: RotationEvent) -> None:
        import requests
        try:
            payload = event.to_dict()
            requests.post(self.webhook_url, json=payload, timeout=self.timeout)
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")


class KaggleHealthMonitor:
    """
    Health monitoring and alerting for Kaggle account rotation.
    
    Features:
    - Real-time health metrics collection
    - Rotation event logging and alerting
    - Prometheus metrics export
    - Configurable alert handlers
    - Integration with existing OmniRoute health endpoints
    """
    
    def __init__(
        self,
        metrics_file: pathlib.Path = METRICS_FILE,
        event_log_file: pathlib.Path = EVENT_LOG_FILE,
        alert_handlers: Optional[List[AlertHandler]] = None,
    ):
        self.metrics_file = metrics_file
        self.event_log_file = event_log_file
        
        # Default handlers
        self.alert_handlers: List[AlertHandler] = alert_handlers or [
            LogAlertHandler(event_log_file),
            ConsoleAlertHandler(),
        ]
        
        # Event buffer for recent events (in-memory, last 1000)
        self._event_buffer: deque = deque(maxlen=1000)
        
        # Latency tracking (rolling window)
        self._latencies: deque = deque(maxlen=1000)
        
        # Metrics
        self.metrics = HealthMetrics()
        
        # Locks
        self._lock = threading.RLock()
        
        # Load persisted metrics
        self._load_metrics()
    
    def _load_metrics(self) -> None:
        """Load persisted metrics from disk."""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Only load counter-type metrics, not gauges
                for key in ('total_requests', 'successful_requests', 'failed_requests',
                           'auth_failures', 'rate_limits', 'rotations_completed',
                           'prewarms_initiated', 'prewarms_failed', 'failovers_triggered'):
                    if key in data:
                        setattr(self.metrics, key, data[key])
            except Exception as e:
                logger.warning(f"Failed to load metrics: {e}")
    
    def _save_metrics(self) -> None:
        """Persist metrics to disk."""
        try:
            data = {
                'total_requests': self.metrics.total_requests,
                'successful_requests': self.metrics.successful_requests,
                'failed_requests': self.metrics.failed_requests,
                'auth_failures': self.metrics.auth_failures,
                'rate_limits': self.metrics.rate_limits,
                'rotations_completed': self.metrics.rotations_completed,
                'prewarms_initiated': self.metrics.prewarms_initiated,
                'prewarms_failed': self.metrics.prewarms_failed,
                'failovers_triggered': self.metrics.failovers_triggered,
                'updated_at': time.time(),
            }
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.metrics_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    def record_event(self, event: RotationEvent) -> None:
        """Record a rotation event and trigger alerts."""
        with self._lock:
            self._event_buffer.append(event)
            
            # Update metrics based on event type
            if event.event_type == RotationEventType.ROTATION_COMPLETED:
                self.metrics.rotations_completed += 1
            elif event.event_type == RotationEventType.ACCOUNT_PREWARMED:
                self.metrics.prewarms_initiated += 1
                if event.level == AlertLevel.CRITICAL:
                    self.metrics.prewarms_failed += 1
            elif event.event_type == RotationEventType.FAILOVER_TRIGGERED:
                self.metrics.failovers_triggered += 1
            elif event.event_type == RotationEventType.AUTH_FAILURE:
                self.metrics.auth_failures += 1
            elif event.event_type == RotationEventType.RATE_LIMITED:
                self.metrics.rate_limits += 1
            
            # Save metrics periodically
            if self.metrics.rotations_completed % 10 == 0:
                self._save_metrics()
        
        # Trigger alerts (outside lock)
        for handler in self.alert_handlers:
            try:
                handler.handle_alert(event)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")
    
    def record_request(self, account_id: str, success: bool, latency: float, 
                       error_type: Optional[str] = None) -> None:
        """Record a request outcome for metrics."""
        with self._lock:
            self.metrics.total_requests += 1
            self._latencies.append(latency)
            
            if success:
                self.metrics.successful_requests += 1
            else:
                self.metrics.failed_requests += 1
                if error_type == "auth":
                    self.metrics.auth_failures += 1
                elif error_type == "rate_limit":
                    self.metrics.rate_limits += 1
            
            # Update latency percentiles
            self._update_latency_metrics()
    
    def _update_latency_metrics(self) -> None:
        """Update latency percentile metrics from rolling window."""
        if not self._latencies:
            return
        
        sorted_lat = sorted(self._latencies)
        n = len(sorted_lat)
        
        self.metrics.avg_request_latency = sum(sorted_lat) / n
        self.metrics.p50_latency = sorted_lat[int(n * 0.5)]
        self.metrics.p95_latency = sorted_lat[int(n * 0.95)] if n > 20 else sorted_lat[-1]
        self.metrics.p99_latency = sorted_lat[int(n * 0.99)] if n > 100 else sorted_lat[-1]
    
    def update_account_metrics(self, accounts: List[Any]) -> None:
        """Update account state metrics from account list."""
        with self._lock:
            self.metrics.total_accounts = len(accounts)
            self.metrics.active_accounts = sum(1 for a in accounts if a.is_active())
            self.metrics.healthy_accounts = sum(1 for a in accounts if a.is_healthy())
            self.metrics.pending_accounts = sum(1 for a in accounts if a.status.value == "pending")
            self.metrics.error_accounts = sum(1 for a in accounts if a.status.value == "error")
            
            # Window utilization
            active = [a for a in accounts if a.is_active() and a.window_end]
            if active:
                now = time.time()
                utilizations = []
                time_remaining_list = []
                
                for a in active:
                    if a.window_start and a.window_end:
                        elapsed = now - a.window_start
                        total = a.window_end - a.window_start
                        if total > 0:
                            utilizations.append(min(1.0, elapsed / total))
                    time_remaining_list.append(a.time_remaining())
                
                if utilizations:
                    self.metrics.avg_window_utilization = sum(utilizations) / len(utilizations)
                if time_remaining_list:
                    self.metrics.min_time_remaining = min(time_remaining_list)
            else:
                self.metrics.avg_window_utilization = 0.0
                self.metrics.min_time_remaining = 0.0
            
            self.metrics.updated_at = time.time()
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status for /health endpoint."""
        with self._lock:
            return {
                "status": self._compute_overall_status(),
                "metrics": {
                    "accounts": {
                        "total": self.metrics.total_accounts,
                        "active": self.metrics.active_accounts,
                        "healthy": self.metrics.healthy_accounts,
                        "pending": self.metrics.pending_accounts,
                        "error": self.metrics.error_accounts,
                    },
                    "requests": {
                        "total": self.metrics.total_requests,
                        "successful": self.metrics.successful_requests,
                        "failed": self.metrics.failed_requests,
                        "success_rate": (
                            self.metrics.successful_requests / self.metrics.total_requests 
                            if self.metrics.total_requests > 0 else 1.0
                        ),
                    },
                    "errors": {
                        "auth_failures": self.metrics.auth_failures,
                        "rate_limits": self.metrics.rate_limits,
                    },
                    "rotation": {
                        "completed": self.metrics.rotations_completed,
                        "prewarms_initiated": self.metrics.prewarms_initiated,
                        "prewarms_failed": self.metrics.prewarms_failed,
                        "failovers_triggered": self.metrics.failovers_triggered,
                    },
                    "latency_seconds": {
                        "avg": round(self.metrics.avg_request_latency, 4),
                        "p50": round(self.metrics.p50_latency, 4),
                        "p95": round(self.metrics.p95_latency, 4),
                        "p99": round(self.metrics.p99_latency, 4),
                    },
                    "window": {
                        "avg_utilization": round(self.metrics.avg_window_utilization, 4),
                        "min_time_remaining_seconds": round(self.metrics.min_time_remaining, 1),
                    },
                },
                "recent_events": [e.to_dict() for e in list(self._event_buffer)[-10:]],
                "updated_at": self.metrics.updated_at,
            }
    
    def _compute_overall_status(self) -> str:
        """Compute overall health status."""
        if self.metrics.healthy_accounts == 0:
            return "critical"
        if self.metrics.error_accounts > 0:
            return "degraded"
        if self.metrics.active_accounts < 2:  # MIN_ACTIVE_ACCOUNTS
            return "degraded"
        if self.metrics.min_time_remaining < 300:  # Less than 5 min on any account
            return "degraded"
        return "healthy"
    
    def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        with self._lock:
            return self.metrics.to_prometheus()
    
    def get_recent_events(self, limit: int = 50, 
                          event_type: Optional[RotationEventType] = None,
                          level: Optional[AlertLevel] = None) -> List[Dict[str, Any]]:
        """Get recent events with optional filtering."""
        with self._lock:
            events = list(self._event_buffer)
        
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if level:
            events = [e for e in events if e.level == level]
        
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return [e.to_dict() for e in events[:limit]]


# Convenience functions for common events
def emit_account_activated(monitor: KaggleHealthMonitor, account_id: str, 
                           window_start: float, window_end: float) -> None:
    """Emit account activated event."""
    event = RotationEvent(
        event_type=RotationEventType.ACCOUNT_ACTIVATED,
        account_id=account_id,
        level=AlertLevel.INFO,
        message=f"Account activated, window: {datetime.fromtimestamp(window_start).strftime('%H:%M')} - {datetime.fromtimestamp(window_end).strftime('%H:%M')}",
        metadata={"window_start": window_start, "window_end": window_end}
    )
    monitor.record_event(event)


def emit_account_prewarmed(monitor: KaggleHealthMonitor, account_id: str, 
                           success: bool, message: str = "") -> None:
    """Emit account pre-warmed event."""
    event = RotationEvent(
        event_type=RotationEventType.ACCOUNT_PREWARMED,
        account_id=account_id,
        level=AlertLevel.INFO if success else AlertLevel.CRITICAL,
        message=message or ("Pre-warm successful" if success else "Pre-warm failed"),
        metadata={"success": success}
    )
    monitor.record_event(event)


def emit_account_expired(monitor: KaggleHealthMonitor, account_id: str, 
                         requests_served: int) -> None:
    """Emit account expired event."""
    event = RotationEvent(
        event_type=RotationEventType.ACCOUNT_EXPIRED,
        account_id=account_id,
        level=AlertLevel.INFO,
        message=f"Account expired after {requests_served} requests",
        metadata={"requests_served": requests_served}
    )
    monitor.record_event(event)


def emit_no_healthy_accounts(monitor: KaggleHealthMonitor) -> None:
    """Emit critical alert: no healthy accounts available."""
    event = RotationEvent(
        event_type=RotationEventType.NO_HEALTHY_ACCOUNTS,
        account_id="",
        level=AlertLevel.CRITICAL,
        message="NO HEALTHY KAGGLE ACCOUNTS AVAILABLE - Service degraded",
        metadata={}
    )
    monitor.record_event(event)


def emit_failover(monitor: KaggleHealthMonitor, from_account: str, to_account: str, 
                  reason: str) -> None:
    """Emit failover event."""
    event = RotationEvent(
        event_type=RotationEventType.FAILOVER_TRIGGERED,
        account_id=to_account,
        level=AlertLevel.WARNING,
        message=f"Failover from {from_account} to {to_account}: {reason}",
        metadata={"from_account": from_account, "reason": reason}
    )
    monitor.record_event(event)


def emit_auth_failure(monitor: KaggleHealthMonitor, account_id: str, 
                      details: str) -> None:
    """Emit auth failure event."""
    event = RotationEvent(
        event_type=RotationEventType.AUTH_FAILURE,
        account_id=account_id,
        level=AlertLevel.CRITICAL,
        message=f"Authentication failure: {details}",
        metadata={"details": details}
    )
    monitor.record_event(event)


# Global monitor instance
_monitor: Optional[KaggleHealthMonitor] = None
_monitor_lock = threading.Lock()


def get_kaggle_monitor() -> KaggleHealthMonitor:
    """Get or create the global health monitor."""
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = KaggleHealthMonitor()
        return _monitor


def start_kaggle_monitoring(alert_webhook: Optional[str] = None) -> KaggleHealthMonitor:
    """Start health monitoring with optional webhook alerting."""
    global _monitor
    with _monitor_lock:
        handlers = [LogAlertHandler(), ConsoleAlertHandler()]
        if alert_webhook:
            handlers.append(WebhookAlertHandler(alert_webhook))
        _monitor = KaggleHealthMonitor(alert_handlers=handlers)
        return _monitor


# HTTP endpoint handlers for integration
def handle_kaggle_health(monitor: KaggleHealthMonitor) -> Dict[str, Any]:
    """Handler for /health endpoint."""
    return monitor.get_health_status()


def handle_kaggle_metrics(monitor: KaggleHealthMonitor) -> str:
    """Handler for /metrics endpoint (Prometheus format)."""
    return monitor.get_prometheus_metrics()


def handle_kaggle_events(monitor: KaggleHealthMonitor, limit: int = 50) -> List[Dict[str, Any]]:
    """Handler for /events endpoint."""
    return monitor.get_recent_events(limit=limit)


if __name__ == "__main__":
    import sys
    
    monitor = start_kaggle_monitoring()
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Simulate some events
        emit_account_activated(monitor, "kaggle-01", time.time(), time.time() + 12*3600)
        emit_account_activated(monitor, "kaggle-02", time.time() + 2*3600, time.time() + 14*3600)
        emit_account_prewarmed(monitor, "kaggle-03", True)
        emit_failover(monitor, "kaggle-01", "kaggle-03", "window expiring")
        
        # Simulate requests
        for i in range(10):
            monitor.record_request("kaggle-01", True, 0.5 + i*0.1)
        monitor.record_request("kaggle-01", False, 2.0, "auth")
        
        # Print status
        print(json.dumps(monitor.get_health_status(), indent=2, default=str))
        print("\n--- Prometheus Metrics ---")
        print(monitor.get_prometheus_metrics())
    else:
        print("Usage: python kaggle_health_monitor.py test")