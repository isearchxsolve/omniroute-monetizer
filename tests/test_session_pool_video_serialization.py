"""Regression coverage for the credit-spending :8190 video dispatcher."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

import session_pool_shim as shim  # noqa: E402


class FakeJobs:
    def __init__(self, job_ids: list[str]) -> None:
        self.records = {job_id: {"status": "queued"} for job_id in job_ids}
        self._lock = threading.Lock()

    def get(self, job_id: str):
        with self._lock:
            return dict(self.records[job_id])

    def update(self, job_id: str, **changes) -> None:
        with self._lock:
            self.records[job_id].update(changes)


class FakePool:
    cooldown = 0.0

    def __init__(self, seats) -> None:
        self.seats = list(seats)
        self.host_lock = threading.Lock()
        self._lock = threading.Lock()
        self.persisted = 0

    def live(self, modality=None, host=None):
        assert modality == "video"
        return self.seats

    def reserve(self, modality=None, host=None):
        assert modality == "video"
        with self._lock:
            return (self.seats.pop(0), time.time()) if self.seats else None

    def _host_lock(self, host):
        assert host == "labs.google"
        return self.host_lock

    def _persist(self):
        self.persisted += 1


def test_video_workers_serialize_distinct_seats_of_the_same_provider(monkeypatch):
    """A second Flow seat must wait; otherwise two submits can spend together."""
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    active = 0
    max_active = 0
    counter_lock = threading.Lock()

    def make_seat(key: str, wait: bool):
        seat = SimpleNamespace(host="labs.google", key=key, last_used=0.0,
                               cooldown_until=0.0, dead=False, last_error=None)

        def chat(_messages, model=None):
            nonlocal active, max_active
            with counter_lock:
                active += 1
                max_active = max(max_active, active)
            if wait:
                first_started.set()
                assert release_first.wait(2), "test never released the first submit"
            else:
                second_started.set()
            with counter_lock:
                active -= 1
            return {"video_url": f"https://example.test/{key}.mp4"}

        seat.chat = chat
        return seat

    jobs = FakeJobs(["job-a", "job-b"])
    pool = FakePool([make_seat("seat-a", True), make_seat("seat-b", False)])
    monkeypatch.setattr(shim, "JOBS", jobs)
    monkeypatch.setattr(shim, "pool", pool)

    first = threading.Thread(target=shim._video_worker,
                             args=("job-a", [{"role": "user", "content": "a"}]))
    second = threading.Thread(target=shim._video_worker,
                              args=("job-b", [{"role": "user", "content": "b"}]))
    first.start()
    assert first_started.wait(1)
    second.start()
    time.sleep(0.08)

    # The second reservation happened, but it cannot send until the first
    # provider exchange leaves the shared host lock.
    assert not second_started.is_set()
    release_first.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert second_started.is_set()
    assert max_active == 1
    assert jobs.records["job-a"]["status"] == "succeeded"
    assert jobs.records["job-b"]["status"] == "succeeded"
