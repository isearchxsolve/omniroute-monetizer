#!/usr/bin/env python3
"""
Kaggle Account Rotation Manager — Zero-Downtime 12-Hour Window Rotation

Strategy:
- 5 Kaggle accounts, each with a 12-hour session window
- Staggered activation so at least 2-3 accounts are always live
- Pre-warm next account 45 minutes before current expires
- Seamless handoff via stable gateway endpoint
- Persistent state survives restarts
"""
from __future__ import annotations
import json
import pathlib
import threading
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from enum import Enum

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
KAGGLE_STATE_FILE = STATE_DIR / "kaggle_rotation_state.json"
KAGGLE_ACCOUNTS_FILE = STATE_DIR / "kaggle_accounts.json"

WINDOW_HOURS = 12
PREWARM_MINUTES = 45
MIN_ACTIVE_ACCOUNTS = 2
STAGGER_HOURS = WINDOW_HOURS // 5  # ~2.4 hours between account activations


class AccountStatus(Enum):
    PENDING = "pending"       # Not yet activated
    PREWARMING = "prewarming" # Being warmed up
    ACTIVE = "active"         # Serving traffic
    EXPIRING = "expiring"     # In final 45 min, prewarming next
    EXPIRED = "expired"       # Window ended, cooling down
    ERROR = "error"           # Failed to activate/prewarm


@dataclass
class KaggleAccount:
    account_id: str
    email: str
    # Credentials stored separately (Windows Credential Manager / env vars)
    # session_cookie: str  # Kaggle session cookie
    # user_agent: str
    
    # Rotation state
    window_start: Optional[float] = None      # Unix timestamp when window started
    window_end: Optional[float] = None        # Unix timestamp when window ends
    status: AccountStatus = AccountStatus.PENDING
    last_heartbeat: Optional[float] = None
    consecutive_failures: int = 0
    total_requests_served: int = 0
    
    # Metadata
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def is_active(self) -> bool:
        return self.status == AccountStatus.ACTIVE
    
    def is_healthy(self) -> bool:
        return self.status in (AccountStatus.ACTIVE, AccountStatus.EXPIRING, AccountStatus.PREWARMING)
    
    def time_remaining(self) -> float:
        if self.window_end is None:
            return 0.0
        return max(0.0, self.window_end - time.time())
    
    def time_until_prewarm(self) -> float:
        if self.window_end is None:
            return float('inf')
        prewarm_start = self.window_end - (PREWARM_MINUTES * 60)
        return max(0.0, prewarm_start - time.time())
    
    def should_prewarm(self) -> bool:
        return (self.status == AccountStatus.ACTIVE and 
                self.time_remaining() <= PREWARM_MINUTES * 60 and
                self.time_remaining() > 0)
    
    def is_expired(self) -> bool:
        if self.window_end is None:
            return False
        return time.time() >= self.window_end
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['status'] = self.status.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KaggleAccount':
        data = data.copy()
        data['status'] = AccountStatus(data['status'])
        return cls(**data)


class KaggleAccountManager:
    """
    Manages 5 Kaggle accounts with 12-hour rotating windows.
    Ensures zero-downtime by pre-warming next account before current expires.
    """
    
    def __init__(self, accounts_file: pathlib.Path = KAGGLE_ACCOUNTS_FILE, 
                 state_file: pathlib.Path = KAGGLE_STATE_FILE):
        self.accounts_file = accounts_file
        self.state_file = state_file
        self.accounts: Dict[str, KaggleAccount] = {}
        self._lock = threading.RLock()
        self._rotation_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._load_accounts()
        self._load_state()
    
    def _load_accounts(self) -> None:
        """Load account definitions from config file."""
        if not self.accounts_file.exists():
            self._create_default_accounts_file()
            return
        
        try:
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for acc_data in data.get('accounts', []):
                acc = KaggleAccount.from_dict(acc_data)
                self.accounts[acc.account_id] = acc
        except Exception as e:
            print(f"[KaggleManager] Failed to load accounts: {e}")
            self._create_default_accounts_file()
    
    def _create_default_accounts_file(self) -> None:
        """Create template accounts file for operator to fill in."""
        template = {
            "accounts": [
                {
                    "account_id": "kaggle-01",
                    "email": "kaggle-account-01@example.com",
                    "window_start": None,
                    "window_end": None,
                    "status": "pending",
                    "last_heartbeat": None,
                    "consecutive_failures": 0,
                    "total_requests_served": 0,
                    "created_at": time.time(),
                    "updated_at": time.time()
                },
                {
                    "account_id": "kaggle-02",
                    "email": "kaggle-account-02@example.com",
                    "window_start": None,
                    "window_end": None,
                    "status": "pending",
                    "last_heartbeat": None,
                    "consecutive_failures": 0,
                    "total_requests_served": 0,
                    "created_at": time.time(),
                    "updated_at": time.time()
                },
                {
                    "account_id": "kaggle-03",
                    "email": "kaggle-account-03@example.com",
                    "window_start": None,
                    "window_end": None,
                    "status": "pending",
                    "last_heartbeat": None,
                    "consecutive_failures": 0,
                    "total_requests_served": 0,
                    "created_at": time.time(),
                    "updated_at": time.time()
                },
                {
                    "account_id": "kaggle-04",
                    "email": "kaggle-account-04@example.com",
                    "window_start": None,
                    "window_end": None,
                    "status": "pending",
                    "last_heartbeat": None,
                    "consecutive_failures": 0,
                    "total_requests_served": 0,
                    "created_at": time.time(),
                    "updated_at": time.time()
                },
                {
                    "account_id": "kaggle-05",
                    "email": "kaggle-account-05@example.com",
                    "window_start": None,
                    "window_end": None,
                    "status": "pending",
                    "last_heartbeat": None,
                    "consecutive_failures": 0,
                    "total_requests_served": 0,
                    "created_at": time.time(),
                    "updated_at": time.time()
                }
            ],
            "config": {
                "window_hours": WINDOW_HOURS,
                "prewarm_minutes": PREWARM_MINUTES,
                "min_active_accounts": MIN_ACTIVE_ACCOUNTS,
                "stagger_hours": STAGGER_HOURS
            }
        }
        self.accounts_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.accounts_file, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2)
        print(f"[KaggleManager] Created template accounts file at {self.accounts_file}")
        print("[KaggleManager] Fill in the 5 Kaggle account emails, then restart.")
    
    def _load_state(self) -> None:
        """Load rotation state (window timestamps, statuses)."""
        if not self.state_file.exists():
            return
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for acc_data in data.get('accounts', []):
                acc_id = acc_data.get('account_id')
                if acc_id in self.accounts:
                    # Only restore rotation state, not config
                    self.accounts[acc_id].window_start = acc_data.get('window_start')
                    self.accounts[acc_id].window_end = acc_data.get('window_end')
                    self.accounts[acc_id].status = AccountStatus(acc_data.get('status', 'pending'))
                    self.accounts[acc_id].last_heartbeat = acc_data.get('last_heartbeat')
                    self.accounts[acc_id].consecutive_failures = acc_data.get('consecutive_failures', 0)
                    self.accounts[acc_id].total_requests_served = acc_data.get('total_requests_served', 0)
        except Exception as e:
            print(f"[KaggleManager] Failed to load state: {e}")
    
    def _save_state(self) -> None:
        """Persist rotation state to disk."""
        try:
            data = {
                'accounts': [acc.to_dict() for acc in self.accounts.values()],
                'updated_at': time.time()
            }
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[KaggleManager] Failed to save state: {e}")
    
    def _save_accounts(self) -> None:
        """Persist account definitions (including updated timestamps)."""
        try:
            data = {
                'accounts': [acc.to_dict() for acc in self.accounts.values()],
                'config': {
                    "window_hours": WINDOW_HOURS,
                    "prewarm_minutes": PREWARM_MINUTES,
                    "min_active_accounts": MIN_ACTIVE_ACCOUNTS,
                    "stagger_hours": STAGGER_HOURS
                }
            }
            with open(self.accounts_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[KaggleManager] Failed to save accounts: {e}")
    
    def start_rotation(self) -> None:
        """Start the rotation manager background thread."""
        if self._rotation_thread and self._rotation_thread.is_alive():
            return
        
        self._stop_event.clear()
        self._rotation_thread = threading.Thread(target=self._rotation_loop, daemon=True, name="kaggle-rotation")
        self._rotation_thread.start()
        print("[KaggleManager] Rotation manager started")
    
    def stop_rotation(self) -> None:
        """Stop the rotation manager background thread."""
        self._stop_event.set()
        if self._rotation_thread:
            self._rotation_thread.join(timeout=5.0)
        print("[KaggleManager] Rotation manager stopped")
    
    def _rotation_loop(self) -> None:
        """Main rotation loop - checks every 30 seconds."""
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    self._check_rotation()
                    self._save_state()
            except Exception as e:
                print(f"[KaggleManager] Rotation loop error: {e}")
            
            # Check every 30 seconds
            self._stop_event.wait(30.0)
    
    def _check_rotation(self) -> None:
        """Check and execute rotation logic."""
        now = time.time()
        active_accounts = [a for a in self.accounts.values() if a.is_active()]
        healthy_accounts = [a for a in self.accounts.values() if a.is_healthy()]
        
        # 1. Activate initial accounts if none active
        if not active_accounts:
            self._activate_initial_accounts()
            return
        
        # 2. Check for accounts that need pre-warming
        for acc in active_accounts:
            if acc.should_prewarm() and acc.status == AccountStatus.ACTIVE:
                acc.status = AccountStatus.EXPIRING
                self._prewarm_next_account(excluding={acc.account_id})
        
        # 3. Check for expired accounts
        for acc in active_accounts:
            if acc.is_expired():
                self._expire_account(acc)
        
        # 4. Ensure minimum active accounts
        current_active = len([a for a in self.accounts.values() if a.is_active()])
        if current_active < MIN_ACTIVE_ACCOUNTS:
            self._activate_additional_accounts(MIN_ACTIVE_ACCOUNTS - current_active)
        
        # 5. Clean up old expired accounts (keep them for history but mark properly)
        for acc in self.accounts.values():
            if acc.status == AccountStatus.EXPIRED and acc.window_end:
                if now - acc.window_end > 3600:  # 1 hour after expiry
                    acc.status = AccountStatus.PENDING
                    acc.window_start = None
                    acc.window_end = None
                    acc.consecutive_failures = 0
    
    def _activate_initial_accounts(self) -> None:
        """Activate first batch of accounts with staggered windows."""
        pending = [a for a in self.accounts.values() if a.status == AccountStatus.PENDING]
        if not pending:
            return
        
        # Sort by account_id for deterministic ordering
        pending.sort(key=lambda a: a.account_id)
        
        # Activate first MIN_ACTIVE_ACCOUNTS with stagger
        now = time.time()
        for i, acc in enumerate(pending[:MIN_ACTIVE_ACCOUNTS]):
            stagger_offset = i * STAGGER_HOURS * 3600
            self._activate_account(acc, now + stagger_offset)
        
        print(f"[KaggleManager] Activated {MIN_ACTIVE_ACCOUNTS} initial accounts with stagger")
    
    def _activate_additional_accounts(self, count: int) -> None:
        """Activate additional accounts to maintain minimum."""
        pending = [a for a in self.accounts.values() if a.status == AccountStatus.PENDING]
        if not pending:
            return
        
        pending.sort(key=lambda a: a.account_id)
        now = time.time()
        
        for acc in pending[:count]:
            self._activate_account(acc, now)
    
    def _activate_account(self, account: KaggleAccount, window_start: float) -> bool:
        """
        Activate a Kaggle account - this is where the actual Kaggle session
        establishment happens. Returns True if successful.
        """
        try:
            # TODO: Implement actual Kaggle session activation
            # This would involve:
            # 1. Load credentials from Windows Credential Manager / env vars
            # 2. Authenticate with Kaggle (if needed)
            # 3. Establish session cookie
            # 4. Verify the session works with a test request
            # 5. Store session cookie for use by the gateway
            
            # For now, simulate successful activation
            account.window_start = window_start
            account.window_end = window_start + (WINDOW_HOURS * 3600)
            account.status = AccountStatus.ACTIVE
            account.last_heartbeat = time.time()
            account.consecutive_failures = 0
            account.updated_at = time.time()
            
            print(f"[KaggleManager] Activated {account.account_id} ({account.email}) "
                  f"window: {datetime.fromtimestamp(window_start).strftime('%H:%M:%S')} - "
                  f"{datetime.fromtimestamp(account.window_end).strftime('%H:%M:%S')}")
            return True
            
        except Exception as e:
            print(f"[KaggleManager] Failed to activate {account.account_id}: {e}")
            account.status = AccountStatus.ERROR
            account.consecutive_failures += 1
            account.updated_at = time.time()
            return False
    
    def _prewarm_next_account(self, excluding: Set[str] = None) -> Optional[KaggleAccount]:
        """Pre-warm the next available account."""
        excluding = excluding or set()
        candidates = [
            a for a in self.accounts.values() 
            if a.status == AccountStatus.PENDING and a.account_id not in excluding
        ]
        if not candidates:
            return None
        
        candidates.sort(key=lambda a: a.account_id)
        next_acc = candidates[0]
        
        next_acc.status = AccountStatus.PREWARMING
        next_acc.updated_at = time.time()
        
        # Activate with a window starting slightly before current expires
        # This ensures overlap
        now = time.time()
        if self._activate_account(next_acc, now):
            return next_acc
        return None
    
    def _expire_account(self, account: KaggleAccount) -> None:
        """Mark an account as expired and clean up."""
        print(f"[KaggleManager] Account {account.account_id} expired after "
              f"{account.total_requests_served} requests")
        account.status = AccountStatus.EXPIRED
        account.updated_at = time.time()
    
    def get_active_accounts(self) -> List[KaggleAccount]:
        """Get all currently active accounts."""
        with self._lock:
            return [a for a in self.accounts.values() if a.is_active()]
    
    def get_healthy_accounts(self) -> List[KaggleAccount]:
        """Get all healthy accounts (active + prewarming + expiring)."""
        with self._lock:
            return [a for a in self.accounts.values() if a.is_healthy()]
    
    def get_best_account(self) -> Optional[KaggleAccount]:
        """
        Get the best account to use for a new request.
        Prefers accounts with most time remaining.
        """
        with self._lock:
            active = [a for a in self.accounts.values() if a.is_active()]
            if not active:
                return None
            # Prefer account with most time remaining (least likely to expire mid-request)
            return max(active, key=lambda a: a.time_remaining())
    
    def record_request(self, account_id: str, success: bool = True) -> None:
        """Record a request outcome for an account."""
        with self._lock:
            if account_id in self.accounts:
                acc = self.accounts[account_id]
                if success:
                    acc.total_requests_served += 1
                    acc.consecutive_failures = 0
                    acc.last_heartbeat = time.time()
                else:
                    acc.consecutive_failures += 1
                    if acc.consecutive_failures >= 3:
                        acc.status = AccountStatus.ERROR
                acc.updated_at = time.time()
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status for monitoring."""
        with self._lock:
            return {
                'accounts': [acc.to_dict() for acc in self.accounts.values()],
                'summary': {
                    'total': len(self.accounts),
                    'active': len([a for a in self.accounts.values() if a.is_active()]),
                    'healthy': len([a for a in self.accounts.values() if a.is_healthy()]),
                    'pending': len([a for a in self.accounts.values() if a.status == AccountStatus.PENDING]),
                    'error': len([a for a in self.accounts.values() if a.status == AccountStatus.ERROR]),
                },
                'config': {
                    'window_hours': WINDOW_HOURS,
                    'prewarm_minutes': PREWARM_MINUTES,
                    'min_active_accounts': MIN_ACTIVE_ACCOUNTS,
                },
                'timestamp': time.time()
            }


# Global manager instance
_manager: Optional[KaggleAccountManager] = None
_manager_lock = threading.Lock()


def get_kaggle_manager() -> KaggleAccountManager:
    """Get or create the global Kaggle account manager."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = KaggleAccountManager()
        return _manager


def start_kaggle_rotation() -> KaggleAccountManager:
    """Start the global Kaggle rotation manager."""
    mgr = get_kaggle_manager()
    mgr.start_rotation()
    return mgr


def stop_kaggle_rotation() -> None:
    """Stop the global Kaggle rotation manager."""
    global _manager
    with _manager_lock:
        if _manager:
            _manager.stop_rotation()
            _manager = None


if __name__ == "__main__":
    # CLI for testing
    import sys
    
    mgr = get_kaggle_manager()
    
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        status = mgr.get_status()
        print(json.dumps(status, indent=2, default=str))
    elif len(sys.argv) > 1 and sys.argv[1] == "start":
        mgr.start_rotation()
        print("Rotation started. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(10)
                status = mgr.get_status()
                print(f"Active: {status['summary']['active']}, Healthy: {status['summary']['healthy']}")
        except KeyboardInterrupt:
            mgr.stop_rotation()
    else:
        print("Usage: python kaggle_account_manager.py [status|start]")