"""Regression tests for the :8190 session-file keepalive."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "scripts" / "automation"
sys.path.insert(0, str(AUTOMATION))

from session_pool_shim import SessionPoolHeartbeat  # noqa: E402


class FakeLock:
    def __init__(self):
        self.locked = False

    def acquire(self, blocking=True):
        if self.locked and not blocking:
            return False
        self.locked = True
        return True

    def release(self):
        self.locked = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_args):
        self.release()


class FakePool:
    cooldown = 20.0

    def __init__(self, session):
        self.session = session
        self._lock = FakeLock()
        self.persisted = 0

    def live(self, modality=None):
        return [self.session] if modality == "chat" else []

    def _host_lock(self, host):
        return self.host_lock

    def _persist(self):
        self.persisted += 1


def fake_session(*, stateless=True, text="58"):
    s = SimpleNamespace(host="example.test", stateless=stateless,
                        cooldown_until=0.0, last_used=time.time() - 10_000,
                        dispatchable=True, dead=False, last_error=None,
                        path=Path(__file__), chat_calls=0)
    def chat(messages):
        s.chat_calls += 1
        return {"text": text}
    s.chat = chat
    return s


def test_heartbeat_touches_one_due_stateless_chat_and_persists():
    s = fake_session()
    pool = FakePool(s)
    pool.host_lock = FakeLock()
    hb = SessionPoolHeartbeat(pool, idle_hours=0.001)

    assert hb.beat_once() is True
    assert s.chat_calls == 1
    assert hb.beats == 1
    assert pool.persisted == 1
    assert s.last_error is None


def test_heartbeat_never_touches_chrome_backed_or_video_candidates():
    s = fake_session(stateless=False)
    pool = FakePool(s)
    pool.host_lock = FakeLock()
    hb = SessionPoolHeartbeat(pool, idle_hours=0.001)

    assert hb.beat_once() is False
    assert s.chat_calls == 0


def test_heartbeat_stands_down_a_wall_without_retrying():
    s = fake_session(text="upgrade to continue")
    pool = FakePool(s)
    pool.host_lock = FakeLock()
    hb = SessionPoolHeartbeat(pool, idle_hours=0.001)

    assert hb.beat_once() is False
    assert hb.failures == 1
    assert s.last_error.startswith("wall:")
    assert s.cooldown_until > time.time() + 3000
