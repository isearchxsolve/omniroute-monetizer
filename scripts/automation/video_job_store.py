"""video_job_store.py — durable video-job ledger behind the :8190 receipt contract.

Worklog #1134 (2026-08-28) — the OiiOii live E2E (LIVE_E2E_REPORT_2026-08-28.md) proved the
old shim's fatal gap: a video POST rendered SYNCHRONOUSLY inside the HTTP handler (up to
VIDEO_TIMEOUT_S=420s), so the consumer's 180s receipt budget expired, the consumer quarantined
the attempt as VideoSubmissionUnknown, and WE had no record of the job either — four paid
renders with no receipt and no reconciliation path on either side.

This store is the permanent correction: every video submit creates a durable job record BEFORE
any render work starts, keyed by both an internal job_id and the consumer's durable job_key
(idempotency). Records survive shim restarts; on load, any job caught mid-flight by a restart
is marked failed with an honest "remote spend state unknown" error — never left silently
queued/running forever.

The file lives under state/ (gitignored). It stores prompts and provenance, never secrets.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time
import uuid
from typing import Any, Dict, Optional, Tuple

DEFAULT_PATH = pathlib.Path(r"D:\omniroute-monetizer\state\video_jobs_8190.json")


class VideoJobStore:
    """Thread-safe, crash-durable job ledger. Atomic writes via temp-file + os.replace."""

    def __init__(self, path: pathlib.Path = DEFAULT_PATH):
        self.path = pathlib.Path(path)
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}      # job_id -> record
        self._by_key: Dict[str, str] = {}               # consumer job_key -> job_id
        self._load()

    # ------------------------------------------------------------ persistence ----
    def _load(self) -> None:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception:
            return                                       # first run or unreadable: start empty
        touched = False
        for j in d.get("jobs", []):
            jid = j.get("job_id")
            if not jid:
                continue
            # Startup reconciliation: a job caught mid-flight by a shim restart has no worker
            # thread anymore. Mark it failed with an honest unknown-spend error — leaving it
            # "queued"/"running" forever is exactly the silent-state sin this store exists to kill.
            if j.get("status") in ("queued", "running"):
                j["status"] = "failed"
                j["error"] = "interrupted by shim restart; remote spend state unknown"
                j["finished"] = j.get("finished") or time.time()
                j["updated"] = time.time()
                touched = True
            self._jobs[jid] = j
            k = j.get("job_key")
            if k:
                self._by_key[k] = jid
        if touched:
            try:
                self._save()
            except Exception:
                pass

    def _save(self) -> None:
        """Caller must hold self._lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"jobs": list(self._jobs.values())}, indent=1),
                       encoding="utf-8")
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ API ----
    def create(self, *, job_key: Optional[str], prompt: str, model: str,
               host: Optional[str], tenant: Optional[str]) -> Tuple[Dict[str, Any], bool]:
        """Create a job record, or return the EXISTING one for this job_key (idempotent replay).

        Returns (record, created). A replayed key NEVER triggers a second render or spend —
        that is the whole point of durable reconciliation for a billing-aware consumer.
        """
        with self._lock:
            if job_key and job_key in self._by_key:
                return self._jobs[self._by_key[job_key]], False
            jid = uuid.uuid4().hex
            now = time.time()
            rec: Dict[str, Any] = {
                "job_id": jid,
                "job_key": job_key or None,
                "status": "queued",                       # queued -> running -> succeeded|failed|cancelled
                "provider": None,                         # filled when a seat is reserved
                "session": None,
                "tenant": tenant,
                "model": model,
                "host": host,                             # pinned host or None for video/auto
                "prompt": prompt,
                "url": None,
                "error": None,
                "progress": 0.0,
                "credits_spent": 0.0,
                "created": now,
                "updated": now,
                "started": None,
                "finished": None,
            }
            self._jobs[jid] = rec
            if job_key:
                self._by_key[job_key] = jid
            self._save()
            return rec, True

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._jobs.get(job_id)
            return dict(rec) if rec else None

    def get_by_key(self, job_key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            jid = self._by_key.get(job_key)
            rec = self._jobs.get(jid) if jid else None
            return dict(rec) if rec else None

    def all(self) -> list:
        with self._lock:
            return [dict(j) for j in self._jobs.values()]

    def update(self, job_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None:
                return None
            rec.update(fields)
            rec["updated"] = time.time()
            self._save()
            return dict(rec)

    def cancel(self, job_id: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Cancel a job. Guaranteed only while status=queued (nothing spent upstream yet).

        Returns (cancelled, record). A running job has already been submitted to the upstream
        provider — the caller must report that honestly instead of claiming cancellation.
        """
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None:
                return False, None
            if rec["status"] == "queued":
                rec["status"] = "cancelled"
                rec["finished"] = time.time()
                rec["updated"] = time.time()
                self._save()
                return True, dict(rec)
            return False, dict(rec)
