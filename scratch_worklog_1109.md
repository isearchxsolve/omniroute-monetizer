

### [2026-08-27 22:10] #1109 — FULL-POOL LOAD BALANCING FIXED: exception class-identity bug killed rotation after first 429; unified ChatError/SessionExpired across all adapters; chat (25) + video (23) pools now rotate with proven fall-through; final consumer endpoint documented

**Objective (user directive):** "loadbalancing both chat and video...give the final consumer endpoint" — confirm/fix that the single :8190 endpoint spreads load across the FULL pool of sessions (chat + video), not just the first one.

**1. ROOT CAUSE FOUND — the balancer existed but was silently defeated by an exception class-identity bug.**

`session_pool.py` `chat()` has a correct fall-through loop: on `ChatError`/`SessionExpired` it cools/marks-dead the session and `continue`s to the next LRU candidate. BUT it catches the CANONICAL classes imported from `veoaifree_chat_client.ChatError` / `veo_session_replay.SessionExpired`. Meanwhile `universal_replay.py` defined its OWN lookalike `class ChatError(Exception)` and `class SessionExpired(Exception)` (lines 28-33). Python `except` matches by class identity, so a 429 raised by any universal-replay seat (`raise ChatError("HTTP_ERROR", str(e))`) was a DIFFERENT class and escaped the pool's `except ChatError` — propagating straight out after ONE attempt. This is exactly what `scratch_trace_balancer.py` observed: 25 live sessions, 1 pick (session_aymo_ai), then `ChatError: ('HTTP_ERROR', 'HTTP Error 429: ')` surfaced.

**Second bug in the same family:** the canonical `SessionExpired(kind, message)` requires TWO args, but four adapters raised it with ONE arg (`raise SessionExpired("Auth rejected: ...")`). At raise-time that throws `TypeError: __init__() missing 1 required positional argument`, which ALSO escapes the pool's catch and kills rotation.

**2. FIX — unified exception identity across all 5 offending files (multi_replace, one pass):**

- `universal_replay.py`: DELETED the local `class SessionExpired` / `class ChatError` definitions; now `from veoaifree_chat_client import ChatError` and `from veo_session_replay import SessionExpired` (the exact classes the pool catches). Fixed the 2 single-arg raises: `SessionExpired("AUTH", "Auth rejected: ...")`, and converted the two long single-string `ChatError(f"EMPTY_BODY: ...")` / `ChatError(f"SENTINEL_NOT_FOUND: ...")` raises to the canonical 2-arg `(kind, message)` form.
- `video_universal_replay.py`: fixed `SessionExpired("Auth rejected: ...")` -> `SessionExpired("AUTH", ...)` (it already imported the canonical classes from universal_replay, which now re-export the real ones).
- `rtst_api_client.py`: 2 single-arg `SessionExpired` raises -> 2-arg `("NO_TOKEN", ...)` / `("AUTH", ...)`.
- `youcom_api_client.py`: same 2 fixes.
- `session_pool_shim.py`: added non-standard `provider` + `session` fields to the OpenAI response so rotation is OBSERVABLE by the consumer (harmless to OpenAI clients).
- No circular-import risk verified: `veoaifree_chat_client` imports only `cdp`; `veo_session_replay` imports only `veoaifree_chat_client`; neither imports `universal_replay`.

**3. VERIFICATION — all proofs green:**

- `scratch_verify_exc_identity.py`: 16/16 class-identity checks OK — every adapter (universal_replay, video_universal_replay, chrome_replay_client, chrome_video_client, digen_session_replay, rtst_api_client, youcom_api_client, session_pool) now references the SAME `veoaifree_chat_client.ChatError` and `veo_session_replay.SessionExpired`; `SessionExpired` is a subclass of `ChatError`; a simulated universal_replay 429 IS caught by `session_pool`'s `except ChatError`. RESULT: ALL_UNIFIED.
- `py_compile` on all 5 modified files: SYNTAX_OK.
- `scratch_prove_fallthrough.py` (in-process, stubbed clients, no network): pool of 25 live chat sessions; first 4 stubs raise `ChatError("HTTP_ERROR","429")`; `pool.chat()` attempted 5 DISTINCT sessions in LRU order (app.chathub.gg -> api.groq.com -> huggingface.co -> chat-api-v3.innerai.com -> www.meta.ai) and SUCCEEDED on the 5th. VERDICT: FALL_THROUGH_WORKS. SessionExpired path: first session marked `dead=True`, rotation continued to the next. VERDICT: EXPIRED_FALLTHROUGH_WORKS.
- `scratch_prove_video_pool.py`: 23 live VIDEO sessions enumerated (ChromeVideoClient for all UI hosts, RtstApiClient for the 4 rtst.ai API seats); stubbed first video session raising WALL -> pool fell through to labs.google. VERDICT: VIDEO_FALLTHROUGH_WORKS.
- Shim :8190 restarted (killed PID 13020, relaunched via task `session_pool_shim`); `/v1/models` returns 50 models incl. `session-pool/auto`, `video/auto`, and per-host chat + video routes. NOTE: `Invoke-WebRequest`/`localhost` failed due to a system proxy intercepting loopback; `curl.exe --noproxy "*"` against `127.0.0.1:8190` works — consumers should use 127.0.0.1 or set no-proxy.

**4. FINAL CONSUMER ENDPOINT (the one URL for both chat and video):**

- Base: `http://127.0.0.1:8190/v1` (OpenAI-compatible). Use `127.0.0.1`, not `localhost` (proxy intercepts loopback on this box).
- Chat (load-balanced across all 25 chat sessions): `POST /v1/chat/completions` with `{"model": "session-pool/auto", "messages": [...]}`.
- Video (load-balanced across all 23 video sessions): `POST /v1/chat/completions` with `{"model": "video/auto", "messages": [{"role":"user","content":"<video prompt>"}]}`; response carries `video_url` in the text/label and `provider`/`session` fields.
- Pin a single provider: `model = "<host>/auto"` (chat) or `video/<host>/auto"` (video), e.g. `video/labs.google/auto`.
- Discover routes: `GET /v1/models`.
- Response now includes `provider` + `session` so the consumer can verify load is actually spreading.
- Persistence: already covered by Windows scheduled task "OmniRoute Session Pool Shim (keepalive)" + `omni_supervisor.py` (health probe `/v1/models`, restarts on crash/reboot). No new service needed.

**Files changed:** universal_replay.py, video_universal_replay.py, rtst_api_client.py, youcom_api_client.py, session_pool_shim.py
**Files created (scratch proofs):** scratch_verify_exc_identity.py, scratch_prove_fallthrough.py, scratch_prove_video_pool.py, scratch_prove_rotation.py
**Services:** shim :8190 restarted with the fix; keepalive task unchanged (already Running).
