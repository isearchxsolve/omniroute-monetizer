# HANDOFF ADDENDUM — How oioi consumes the harness (chat + video endpoints)

**Append this to the main handoff prompt. It answers one question the previous handoff left open:**
*"how oioi will consume all of this — the chat and video — will it remain same endpoint?"*

Verified 2026-08-24 by reading source, not by inference. Line references are exact.

---

## 1. Answer: NO — two endpoints, and the split is deliberate

oioi is already wired for this. It has **two independent client paths** that must not be merged.

```
                    ┌─ CHAT ──────────────────────────────────────────────┐
oioi backend        │  backend/studio_pipeline/omniroute.py               │
  OmniRouteClient ──┤  DEFAULT_BASE_URL = "http://127.0.0.1:20128/v1" :29 │
                    │  POST /v1/chat/completions   (stream: false)        │
                    └─────────────────────────────────────────────────────┘

                    ┌─ VIDEO ─────────────────────────────────────────────┐
  OmniRouteVideo ───┤  OMNIROUTE_VIDEO_BASE_URL = "http://127.0.0.1:8189" │
    Adapter         │    backend/app/core/config.py:70                    │
                    │  POST /v1/videos/quote        (free, no spend)      │
                    │  POST /v1/videos/generations → job → mp4 bytes      │
                    └─────────────────────────────────────────────────────┘
```

**Exact call sites:**
- Chat client: `D:\god_ai\oioi\oioi\backend\studio_pipeline\omniroute.py`
  - `DEFAULT_BASE_URL` L29, `DEFAULT_MODEL = "frontier"` L30, `VIDEO_ROUTE_CANDIDATES` L33
  - `chat()` L185, `chat_json()` L253, `probe_chat()` L302, `probe_video()` L324, `generate_video()` L388
  - Env precedence: `OMNIROUTE_BASE_URL` → `OPENROUTER_API_BASE_URL` → `OPENAI_API_BASE` → default (L132)
- Video adapter construction: `backend/app/services/provider_service.py:73-78`
  ```python
  from providers.omniroute_video import OmniRouteVideoAdapter
  return OmniRouteVideoAdapter(
      base_url=settings.OMNIROUTE_VIDEO_BASE_URL,
      api_key=settings.OMNIROUTE_VIDEO_TOKEN,
      max_credits=settings.OMNIROUTE_VIDEO_MAX_CREDITS,
  )
  ```
  Availability gate: `return bool(settings.OMNIROUTE_VIDEO_BASE_URL)` at `provider_service.py:105`

### Why merging them costs real money

`backend/app/core/config.py:70` carries an explicit warning, and it is correct:
the video var is **not** named `OMNIROUTE_BASE_URL` on purpose. `probe_video()`
(`omniroute.py:324`) discovers routes by **POSTing a real generation request** against
`VIDEO_ROUTE_CANDIDATES`. Point the chat name at the video router and every capability probe
submits a genuine paid job, then abandons it after its 8-second timeout.

> **RULE: never set `OMNIROUTE_BASE_URL` to the video router's port. Ever.**

### The third face (`:8188`) — exists, do not use it from oioi

`scripts/automation/video_router.py` serves the same job engine behind two faces:
- `:8189` — the honest one. `POST /v1/videos/generations`, `GET` job, `GET` mp4 bytes, plus a
  **free** `POST /v1/videos/quote`. **This is the one the filmmaking app uses.**
- `:8188` — a ComfyUI costume (`POST /prompt`, `GET /history/{id}`, `GET /view?filename=`) so video
  is reachable *through* OmniRoute as a `comfyui/veo-3.1-fast` model string with zero OmniRoute code
  change. Two unfixable flaws recorded in that file: it labels **all** bytes `webp`, and it has **no
  error channel**, so failures surface as ~300s timeouts. That is why oioi should use `:8189`.

---

## 2. Video: oioi needs ZERO changes to gain a new provider

New providers plug in *behind* `:8189`. The endpoint oioi calls never changes.

```
video_provider.py  — the seam (grep only, do not read in full)
  class Account   L169   "one provider login == one browser tab == one balance"
  class Step      L226
  class Provider  L236 → quote() L285  confirm() L295  probe() L312  submit() L318
  REGISTRY: dict[str, Provider]  L374
  register(p)                    L377
        ↑
  video_provider_flow.py (Google Flow / Veo 3.1), video_provider_rtst.py (Vidu Q2)
        ↑
  video_router.py — registry, rotation, jobs, self-heal, two faces, CLI
        ↑
   :8189  ← oioi's OMNIROUTE_VIDEO_BASE_URL, unchanged forever
```

Write `video_provider_digen.py`, `register()` it, done. Same for kling, capcut, openart, teamily,
topmediai, imagine.art. Rotation across accounts, per-account locking across submit+poll,
`confirm()`-before-spend, and **no-automatic-submit-retry** are already the router's responsibility —
inherit them, do not reimplement.

---

## 3. Chat: this is the one real gap

`scripts/automation/session_pool.py` has **no HTTP face**. Verified by grep: no `HTTPServer`, no
`FastAPI`, no `uvicorn`, no `do_POST`, no `chat/completions`. It is CLI-only —
`argparse` at L25, subparsers built at L227. So the veoaifree client and every swept chat provider
are reachable from a terminal and from nowhere else.

**What it does have** (the good part — this is the registry to build on):

```python
# session_pool.py:46
CLIENTS: Dict[str, Type[Any]] = {
    "veoaifree.com": VeoSessionClient,
    "digen.ai": DigenSessionClient,
}
```
Plus a real LRU load-spreader honouring breadth-not-depth: `PooledSession.modality` L86,
`live()` L142, `pick()` L149, `chat()` L156, `sweep()` L190, `DEFAULT_COOLDOWN = 20.0` L52,
and a per-host lock so the same host never gets a burst.

**The work:** put an OpenAI-compatible `/v1/chat/completions` shim in front of `SessionPool.chat()`,
mirroring exactly what `video_router.py:8189` does for video. Then oioi consumes it **unchanged**,
via either:

- **(a)** repoint `OMNIROUTE_BASE_URL` at the shim's port — one env var, no code change; or
- **(b)** register the shim as a provider *inside* OmniRoute so `:20128` fans out to it — oioi keeps
  talking to `:20128` and never learns the pool exists. **Prefer (b)**: it keeps OmniRoute's existing
  routing/failover and leaves oioi's default untouched.

Shim must honour what oioi's client already expects (documented in `omniroute.py`'s own docstring
from measured behaviour): send `stream` explicitly as `false`; responses may carry both `content`
and `reasoning_content` and **only `content` is the answer**.

---

## 4. CORRECTION to the previous handoff + the Digen adapter's real state

The previous handoff said the Digen adapter was not written. **That was wrong.**
`scripts/automation/digen_session_replay.py` exists (169 lines, newest file in the tree) and is
already registered at `session_pool.py:48`.

**What is true:** it is written, it is wired, and it has **never been executed.**
Evidence: `state/session_pool_state.json` contains only `{"session_veoaifree_com": ...}` — no
digen entry, and that file records every dispatch.

### What the adapter gets right
Lifts the `Digen-*` custom headers (not the cookie) from the recorded exchange; drops
`content-length` / `cookie` / `accept-encoding` and HTTP/2 pseudo-headers (`_DROP_HDR` L21, filter
L60); thread-local `requests.Session` for parallel safety (L22-29); raises `SessionExpired` on
401/403 (L96-97); re-serialises `scene_params` correctly as a JSON **string** (L86-88).

### Defects to fix before it runs — in priority order

1. **`code` idempotency key is replayed verbatim — LOAD-BEARING.** L83-88 swaps only
   `video_gen_prompt`; every other `scene_params` field, including
   `code = "<epoch_nanos>_<uuid4>"`, is the captured value. That field is a client-generated
   idempotency key. Replaying it either returns the **same cached video for every prompt** (silently
   wrong — you would not notice until you watched 2,160 identical clips) or is rejected outright.
   **Fix: synthesize `f"{time.time_ns()}_{uuid.uuid4()}"` per submit.**

2. **No spend guardrail at all.** Each `chat()` call burns 30 credits with no `quote()`, no
   `confirm()`, no ceiling, no pre-check of `GET /v1/credit/remain`. It bypasses the entire
   `video_provider.Provider` guardrail design by living in `session_pool.py` instead of behind
   `video_router.py`. **This is the argument for porting it to `video_provider_digen.py`.**

3. **`sweep` will spend money — LIVE LANDMINE.** `session_digen_ai.json` has **no `modality` key**
   (verified: top-level keys are `captured_at, context, cookie_header, cookies, host, likely_authed,
   match, recorded_job`), and `session_pool.py:86` defaults missing modality to `"chat"`. So
   `python session_pool.py sweep` — with or without `--modality chat` — will class digen.ai as a chat
   provider and fire a **real 30-credit video generation**, blocking up to 120s, as its "one light
   call." **Do not run a sweep until this is fixed.** Fix either way: add `"modality": "video"` to
   the session file, or make modality inference explicit rather than defaulted.

4. **No error channel — cannot ever report a failure.** The poll URL hardcodes the server-side
   filter `status=2` (L110), so a job only appears in the list once it is already DONE. A **failed**
   job never appears at all, so the loop can only ever exhaust its budget and raise `TIMEOUT`
   (L138). Same flaw as the `:8188` ComfyUI face. Fix: poll unfiltered and branch on the real status
   value.

5. **Dead fallback branch raises `AttributeError`.** In `reload()`, if `recorded_job` is absent but
   `recorded_exchange` is present, L46 assigns a **local** `exchanges` and never sets
   `self._exchanges`; L56 then dereferences `self._exchanges`. Fix or delete the branch.

6. **`self.timeout` does double duty** (L92 per-request AND L113 total poll budget). Measured render
   was ~50s against a 120s budget — thin, and a slow submit eats the poll window. Split into
   `request_timeout` and `poll_budget`.

7. **`cid` (space id) replayed verbatim.** Correct for this account only; a new account must supply
   its own from its own capture. Same for `scene_id`.

8. **`videoURLV1` fallback (L124) is a guess** — the capture only ever showed `videoUrl`. Harmless,
   but it is not evidence-backed; label it as such.

---

## 5. Spend-guardrail collision — decide this before building the pipeline

```
OMNIROUTE_VIDEO_MAX_CREDITS_PER_RUN = 60     # config.py, oioi's per-run ceiling
Digen measured cost                 = 30     # credits per 5s clip
                                    → 2 clips per pipeline run
```

Against a 2,160-clip / 3-hour-film target this guardrail will hard-stop the pipeline on clip 3.
It was calibrated before Digen's price was known (Flow 8s/720p = 20 credits, rtst 3s/540p = 6;
whole rtst balance is 18, Flow's 930). Raising it is a **real spend decision, not a config typo** —
it is flagged here, deliberately unchanged.

---

## 6. Recommended build order

1. **Fix defect #3 first** (the sweep landmine) — it costs credits on a command that looks free.
2. **Fix defect #1** (idempotency key) — without it, a "working" pipeline silently emits duplicates.
3. **Port Digen to `video_provider_digen.py`** behind `:8189`, inheriting `quote`/`confirm`/rotation/
   no-retry. This proves replay end-to-end on **one** provider and gives oioi the provider for free.
4. **Then** build the chat `/v1/chat/completions` shim over `SessionPool.chat()` and register it
   inside OmniRoute (option **b** above). Do this second — it generalises over ~95 hosts, and it is
   worth generalising only after the pattern is proven on one.
5. Resolve the credit-ceiling decision (§5) with the operator before any multi-clip run.

---

## 7. What is NOT claimed

- No shim exists. No `video_provider_digen.py` exists.
- `digen_session_replay.py` has **never run**; nothing has been replayed server-side against Digen.
  Its correctness is unverified by execution — the defect list above is from reading, and there may
  be more that only a live call reveals.
- The 8 defects are unfixed. The sweep landmine (#3) is live right now.
- Only text-to-video was captured for Digen. No image-to-video generation has been recorded, so the
  character-image relay slots (`image_url`, `last_image_url`, `middle_image_url`, `lora_id`) are
  captured **empty** and their populated wire shape is unknown.
- Chat-side capture is proven for veoaifree only. The ~95 swept chat providers have shapes that are
  **listed, not proven** — `session_pool.py` deliberately refuses to blind-replay a host with no
  `CLIENTS` entry, and that rule stands.
- Nothing in oioi was modified while producing this document. Read-only.
