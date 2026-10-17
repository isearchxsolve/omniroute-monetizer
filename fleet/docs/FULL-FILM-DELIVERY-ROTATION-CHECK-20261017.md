# Full film delivery and Kaggle rotation check — 17 October 2026

**Verdict: local retained download survives a local API restart; full film acceptance and Kaggle rotation survival do not pass.**

## What was actually exercised

The existing genuine graduated LTX film `film_6a88ff76a59b469796f06d413db6ec67` remains on disk. Its managed MP4 is 148,552 bytes, SHA-256 `2f29a8bb07113426d0caff59f47aa70af7a3d8284c4c586018ed0c48e1afa189`. The provider job is succeeded with `is_fallback=0`.

Using SQLite backups and byte-identical copies of the actual retained data (no simulated API, provider, account or film), the actual current FastAPI application was launched on loopback port 8111. Existing owner credentials were used privately. The first process authenticated and downloaded the film; it was stopped. A second real API process opened the same retained files and accepted the persisted authentication session. Both downloads returned HTTP200 video/mp4 and the exact same bytes/hash. Unauthenticated downloads returned HTTP401/403. Both owned processes were stopped; production services were not started or restarted.

Receipt: `state/retained_film_restart_1792227217/receipt.json`. Reproduction: `fleet/tools/prove_retained_film_restart.py` using the app's existing venv. This is explicitly a LOCAL restart test, not a Kaggle rotation test or a new render.

## Failed acceptance checks

1. **Duration:** actual film and shot records request 5 seconds. Fresh ffprobe reports H.264 1280x720 + AAC, duration **1.958334 seconds**. The MP4 is real but does not meet its requested duration. `HttpClipMaterializer` calls `media.normalize_clip(...duration=5)`. The silent-input fallback uses `-shortest`; its `-t 5` limits output but does not extend a short source. A duration-fit helper exists elsewhere but is not used here. No new motion should be claimed by stretching/looping existing frames without disclosure.
2. **Public delivery unavailable now:** the live permanent gateway returns no sessions; the tracked isearchxsolve film kernel is `CANCEL_ACKNOWLEDGED`. The repaired local film/shim services are parked. No public customer film request-to-download test can currently run through that deployment.
3. **Storage is local:** `film_jobs.sqlite3` holds artifact metadata and an object key; this artifact's database payload is **zero bytes**. The actual MP4 is in the local object directory. Both must be preserved together. `object://` is an application identifier, not proof of remote storage.
4. **No rotation restore:** the Kaggle bootstrap stages application code and starts Uvicorn; it has no shared film-job/object store, no checkpoint restore, and no restored-object hash check. Database account configuration alone would not preserve the independent film-job SQLite and video objects. Saved notebook outputs would require an explicit verified restore flow; none is wired here.
5. **No verified handover:** the rotator marks a successful kernel push as a new live session, without checking customer authentication and the same retained film download before handover. It does not transfer film records/media.
6. **Completion status can overstate delivery:** `_archive_completed_film` catches retention errors and still writes `completed` with an archive-pending error. A completed status alone is not sufficient delivery proof; retained object existence, authorization, media properties and hash must also pass.

The bootstrap starts the backend only; it does not start the customer frontend. Its local shim forwards inference requests to the permanent door, whose current `/v1/models` and `/v1/video/capacity` routes return not-found. The new graduated-provider rendering path is not fully deployed into that film notebook.

## What is required to earn a Kaggle rotation pass

- Connect durable accounts, film-job records, and private video objects outside the disposable serving session, or implement an explicit durable checkpoint/restore protocol.
- Start the actual film app and graduated provider supply; verify the requested duration and reject incomplete delivery rather than claiming a full film.
- On session A authenticate and deliver a real accepted film; record its identity, authorization behavior and hash.
- Bring up session B, restore or reconnect the same records/media, and verify that same authorized download. Route traffic only after those checks pass.
- Stop session A, then repeat the authenticated and unauthenticated checks through the permanent customer route. Record the unchanged artifact hash from B.

No Kaggle rotation, new model render, payment, credential change, or destructive operation was performed in this check. No synthetic evidence was created. The previous local real render remains genuine; it is not a full product/rotation acceptance pass.

Machine-readable audit: `state/full_delivery_storage_audit_20261017.json`.
