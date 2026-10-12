#!/usr/bin/env python3
"""
Kaggle Wire — Unified Startup Script for 5-Account Rotation Gateway

This script starts the complete Kaggle rotation infrastructure:
1. KaggleAccountManager — 5 accounts, 12h windows, staggered activation
2. KagglePoolGateway — Stable HTTP endpoint (port 20135) with seamless handoff
3. KaggleHealthMonitor — Observability, alerting, Prometheus metrics
4. Integration with chat_pool_server (port 20130) as fallback upstream

Architecture:
```
                    ┌─────────────────────────────────────┐
                    │         CLIENTS (OiiOii,            │
                    │         EmergentSH, OY,             │
                    │         Amazon.sh)                  │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │   chat_pool_server :20130           │
                    │  (Superset Gateway)                 │
                    │  • pool/* → local captured sessions │
                    │  • kaggle/* → Kaggle gateway :20135 │
                    │  • other → OmniRoute :20128         │
                    └──────────────┬──────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
       ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
       │  Kaggle     │      │  OmniRoute  │      │  Local Pool │
       │  Gateway    │      │  :20128     │      │  (captured  │
       │  :20135     │      │  (paid)     │      │  sessions)  │
       └──────┬──────┘      └─────────────┘      └─────────────┘
              │
       ┌──────┴──────┐
       │ 5 Kaggle    │
       │ Accounts    │
       │ (12h rota)  │
       └─────────────┘
```

Usage:
    python kaggle_wire.py start          # Start all components
    python kaggle_wire.py status         # Show health status
    python kaggle_wire.py metrics        # Prometheus metrics
    python kaggle_wire.py events         # Recent rotation events
    python kaggle_wire.py test           # Run integration test
"""
from __future__ import annotations
import json
import pathlib
import sys
import threading
import time
import signal
import atexit

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from kaggle_account_manager import (
    get_kaggle_manager, start_kaggle_rotation, stop_kaggle_rotation
)
from kaggle_pool_gateway import (
    get_kaggle_gateway, start_kaggle_gateway, stop_kaggle_gateway,
    KAGGLE_GATEWAY_PORT
)
from kaggle_health_monitor import (
    get_kaggle_monitor, start_kaggle_monitoring,
    handle_kaggle_health, handle_kaggle_metrics, handle_kaggle_events,
    emit_account_activated, emit_account_prewarmed, emit_account_expired,
    emit_failover, emit_no_healthy_accounts, emit_auth_failure
)
from kaggle_integration import (
    start_kaggle_integration, stop_kaggle_integration,
    get_kaggle_integration_status, patch_chat_pool_server_for_kaggle
)

# Global state
_running = False
_shutdown_event = threading.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _running
    print(f"\n[KaggleWire] Received signal {signum}, shutting down...")
    _running = False
    _shutdown_event.set()


def start_all() -> None:
    """Start all Kaggle wire components."""
    global _running
    
    if _running:
        print("[KaggleWire] Already running")
        return
    
    print("[KaggleWire] Starting Kaggle 5-account rotation wire...")
    print("=" * 60)
    
    # 1. Start account manager (rotation scheduler)
    print("[1/4] Starting KaggleAccountManager...")
    manager = start_kaggle_rotation()
    
    # 2. Start pool gateway (stable HTTP endpoint)
    print("[2/4] Starting KagglePoolGateway on port 20135...")
    gateway = start_kaggle_gateway()
    
    # 3. Start health monitoring
    print("[3/4] Starting KaggleHealthMonitor...")
    monitor = start_kaggle_monitoring()
    
    # 4. Start integration with chat_pool_server
    print("[4/4] Starting KaggleIntegration (chat_pool_server bridge)...")
    integration = start_kaggle_integration()
    
    # Register shutdown handlers
    atexit.register(stop_all)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    _running = True
    
    print("=" * 60)
    print("[KaggleWire] ALL COMPONENTS STARTED")
    print(f"  • Account Manager: Running (5 accounts, 12h windows)")
    print(f"  • Pool Gateway: http://127.0.0.1:{KAGGLE_GATEWAY_PORT}")
    print(f"  • Health Endpoint: http://127.0.0.1:{KAGGLE_GATEWAY_PORT}/health")
    print(f"  • Metrics Endpoint: http://127.0.0.1:{KAGGLE_GATEWAY_PORT}/metrics")
    print(f"  • Events Endpoint: http://127.0.0.1:{KAGGLE_GATEWAY_PORT}/events")
    print(f"  • chat_pool_server integration: Active")
    print("=" * 60)
    print("\nEndpoints for consumers:")
    print("  • OiiOii / EmergentSH: Configure to use chat_pool_server :20130")
    print("    - Models: kaggle/*, pool/kaggle-* (via Kaggle gateway)")
    print("    - Fallback: OmniRoute :20128 → Kaggle :20135 → Local Pool")
    print("  • Direct Kaggle access: POST http://127.0.0.1:20135/v1/chat/completions")
    print("\nPress Ctrl+C to stop all components\n")
    
    # Keep running
    try:
        while _running and not _shutdown_event.is_set():
            time.sleep(10)
            # Periodic health log
            status = handle_kaggle_health(monitor)
            print(f"[Heartbeat] Status: {status['status']} | "
                  f"Accounts: {status['metrics']['accounts']['active']} active, "
                  f"{status['metrics']['accounts']['healthy']} healthy | "
                  f"Requests: {status['metrics']['requests']['total']} total, "
                  f"{status['metrics']['requests']['success_rate']:.1%} success")
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()


def stop_all() -> None:
    """Stop all components gracefully."""
    global _running
    
    if not _running:
        return
    
    print("\n[KaggleWire] Stopping all components...")
    
    stop_kaggle_integration()
    stop_kaggle_gateway()
    stop_kaggle_rotation()
    
    _running = False
    print("[KaggleWire] All components stopped")


def show_status() -> None:
    """Show current health status."""
    monitor = get_kaggle_monitor()
    status = handle_kaggle_health(monitor)
    print(json.dumps(status, indent=2, default=str))


def show_metrics() -> None:
    """Show Prometheus metrics."""
    monitor = get_kaggle_monitor()
    print(handle_kaggle_metrics(monitor))


def show_events(limit: int = 50) -> None:
    """Show recent rotation events."""
    monitor = get_kaggle_monitor()
    events = handle_kaggle_events(monitor, limit=limit)
    print(json.dumps(events, indent=2, default=str))


def show_integration_status() -> None:
    """Show integration status."""
    status = get_kaggle_integration_status()
    print(json.dumps(status, indent=2, default=str))


def run_test() -> None:
    """Run integration test."""
    print("[KaggleWire] Running integration test...")
    
    # Start components
    start_kaggle_rotation()
    gateway = start_kaggle_gateway()
    monitor = start_kaggle_monitoring()
    integration = start_kaggle_integration()
    
    # Wait for initialization
    time.sleep(3)
    
    # Test gateway health
    print("\n1. Testing gateway health...")
    health = gateway.handle_health()
    print(f"   Status: {health['status']}")
    print(f"   Active sessions: {health['gateway']['active_sessions']}")
    print(f"   Accounts: {health['kaggle_accounts']['summary']}")
    
    # Test models endpoint
    print("\n2. Testing /v1/models...")
    models = gateway.handle_models()
    print(f"   Models available: {len(models['data'])}")
    for m in models['data'][:5]:
        print(f"     - {m['id']}")
    
    # Test chat completions
    print("\n3. Testing /v1/chat/completions...")
    import requests
    try:
        resp = requests.post(
            f"http://127.0.0.1:{KAGGLE_GATEWAY_PORT}/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Say 'OK' and nothing else"}],
                "max_tokens": 10
            },
            timeout=30
        )
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            print(f"   Response: {content[:100]}")
        else:
            print(f"   Error: {resp.text[:200]}")
    except Exception as e:
        print(f"   Request failed: {e}")
    
    # Test integration status
    print("\n4. Testing integration status...")
    int_status = get_kaggle_integration_status()
    print(f"   Gateway running: {int_status['gateway']['running']}")
    print(f"   Models exposed: {int_status['integration']['models_exposed']}")
    print(f"   Fallback order: {int_status['integration']['fallback_order']}")
    
    # Test monitoring
    print("\n5. Testing health monitor...")
    mon_status = handle_kaggle_health(monitor)
    print(f"   Overall status: {mon_status['status']}")
    print(f"   Metrics: {mon_status['metrics']}")
    
    # Cleanup
    print("\n6. Stopping components...")
    stop_kaggle_integration()
    stop_kaggle_gateway()
    stop_kaggle_rotation()
    
    print("\n[KaggleWire] Integration test complete!")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1].lower()
    
    if command == "start":
        start_all()
    elif command == "status":
        show_status()
    elif command == "metrics":
        show_metrics()
    elif command == "events":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        show_events(limit)
    elif command == "integration":
        show_integration_status()
    elif command == "test":
        run_test()
    elif command == "stop":
        stop_all()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()