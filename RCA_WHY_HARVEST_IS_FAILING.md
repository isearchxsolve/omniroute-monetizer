# RCA — Why Harvest Is Failing (Deep-Dive)

**Date:** 2026-08-27
**Scope:** Full funnel from the 36 prepared tabs on seat1 (`:9222`, `providers` profile)
through capture (`capture_sessions_cdp.py`) to replay (`universal_replay.py` /
`browser_replay.py`). Ground truth taken from `state/capture_report_9222.json`,
`state/replay_check.json`, `state/browser_replay.json`, and the 27 files in
`state/secrets/`.

---

## 0. The funnel (the real story)

```
36 tabs prepared
  └─> 14 captured as HTTP exchanges        (capture phase)
        + 2 walls, 2 websocket-only, 7 never-captured, 2 video-skipped
  └─> 27 session_*.json on disk            (14 fresh + older captures)
        └─> 3–5 REPLAY_OK                  (replay phase)
```

**Supply is being lost at THREE distinct gates, not one.** Fixing only the replay
transport (the impersonator-vs-browser debate) addresses gate 3. Gates 1 and 2 are
where most of the 36 tabs actually die.

| Gate | Loss | Count |
|------|------|-------|
| Gate 1 — Capture never records a usable exchange | NO_REQUEST / WEBSOCKET / NO_TAB / VIDEO_SKIPPED | 11 of 36 tabs |
| Gate 2 — Capture records the WRONG exchange | multi-step handshake grabbed instead of inference call | 2 (chatgpt, meta) |
| Gate 3 — Replay of a correct exchange fails | auth / rate / wall / single-use / schema / false-negative | rest |

---

## 1. GATE 1 — Capture never records a usable exchange (11 tabs)

From `capture_report_9222.json` `summary.failed` + `websocketOnly` + `walls`:

### 1a. WebSocket-only providers — structurally not HTTP-replayable (2)
- **Microsoft Copilot Web** — `WEBSOCKET`, 105 ws frames, sentinel left over a frame.
- **Grok on X / Grok Web** — `WEBSOCKET`, 178 ws frames.

The capture tool *correctly* detects this and refuses to save a fake HTTP session
(this is honest, per Law 5). But these two are **permanently lost to HTTP replay**.
The only way to harvest them is a WebSocket replay engine (re-send the frame over a
live WS), which does not exist yet. **This is a capability gap, not a bug.**

### 1b. NO_REQUEST — all 4 submit strategies fired, zero matching POSTs (3)
- **Claude Official Web** — 32 req / 9 posts / 0 ws, but none carried the sentinel.
- **Meta AI Web** — 18 req / 8 posts / 28 ws, none matched (see also Gate 2).
- **Baichuan Web** — 28 req / 7 posts / 0 ws, `retypeLanded:false`.

Root cause is one of:
- The composer text never actually reached the app's internal document
  (ProseMirror/Lexical model-backed editors), so the submit guard saw an empty
  composer and emitted a request WITHOUT the sentinel. `retypeLanded:false` on
  Baichuan confirms the text never landed.
- The sentinel went out over a channel the scanner doesn't match (e.g. a POST whose
  body is the sentinel but URL-encoded / base64 / split, so `has_sentinel(body)`
  misses it).

### 1c. NO_TAB — the site directory expects a tab that isn't open (2)
- **V0 by Vercel** (`v0.dev`), **DuckDuckGo AI Chat** (`duckduckgo.com`).
The tab list on `:9222` has `v0.app` and `duck.ai`, but the directory keys them under
different domains. **Domain-name mismatch between the site directory and the live
tabs.** Pure config bug — trivially fixable.

### 1d. VIDEO_PROVIDER_SKIPPED (2)
- **rtst.ai**, **Google Flow (labs.google)** — deliberately skipped by the chat
  capture path because they are video providers. Correct behavior, but they are then
  only half-captured (see Gate 3, class F).

---

## 2. GATE 2 — Capture records the WRONG exchange (the silent killer)

This is the most important finding. Two "captured" sessions are actually useless
because the capture tool grabbed a **preparatory/handshake POST**, not the inference
call. The capture logic (`scan()` in `capture_sessions_cdp.py`) saves the **first**
POST/PUT/PATCH whose body contains the sentinel. For multi-step flows, the first such
POST is a setup step.

### 2a. chatgpt.com → captured `/backend-api/f/conversation/prepare`
The recorded body is:
```json
{"action":"next","parent_message_id":"client-created-root", ...,
 "partial_query":{... "parts":["Reply exactly one word: Omni."]}, ...}
```
`/conversation/prepare` is a **handshake** that returns a `conduit_token`
(386-byte JSON). The actual answer streams from a DIFFERENT endpoint
(`/backend-api/conversation`, EventStream). Replaying `prepare` can **never** return
the phrase — it returns a token. This is why chatgpt is `NO_ANSWER` with a
`conduit_token` body **every single time, on every transport**. The session is not
dead; the capture is pointed at the wrong step.

### 2b. meta.ai → captured a `searchconversations` GraphQL query
The recorded body is `{"doc_id":"c42ec1c7...","variables":{"query":"Reply exactly
one word: Omni."}}` but the replay returns
`{"data":{"searchconversations":{"edges":[],...}}}` — a **search** result, not a chat
completion. The real chat mutation uses a different `doc_id`. Same class of bug:
first-sentinel-POST wins, and the first one was a search/lookup, not the generation
call.

**Fix direction:** the capture must not save the first sentinel POST blindly. It must
either (a) prefer the POST whose RESPONSE is a streaming/EventStream body, or
(b) record ALL sentinel-bearing POSTs in the flow and let replay pick the one that
actually produces tokens, or (c) per-site override table mapping site → correct
inference endpoint (a `CHAT_URL_OVERRIDES` already exists in the capture tool — it
just needs these two entries).

---

## 3. GATE 3 — Replay of a correct exchange fails

Classified across `replay_check.json` (requests/curl_cffi transport) and
`browser_replay.json` (in-browser fetch). Note the two transports disagree on several
providers — that disagreement is itself diagnostic.

### Class A — Auth / token expired or insufficient (4)
- **groq** `api.groq.com` → 401 on both transports. Bearer token in the recorded
  headers has expired.
- **veoaifree** → 403.
- **cerebras** → 400 `"not a valid request"` on browser, `AUTH` on requests. The
  recorded request is missing a live auth token / the body shape is rejected.
- **gemini** → `AUTH` on requests transport but **REPLAY_OK on in-browser fetch**.
  This is the transient case: the cookie is alive in the browser's jar but the
  exported `cookie_header` alone is insufficient (needs `at` token / `_reqid`
  freshness). Confirms gemini IS harvestable if replayed from the real browser.

### Class B — Rate limit / quota exhausted (4)
- **aymo** → 429, capture already flagged `wall:"insufficient credits"`.
- **chathub** → 429.
- **mistral** → 429 on requests, 409 `already` on browser (message-id reuse).
- **innerai** → 402 Payment Required.
These are free-tier exhaustion. Not a tooling bug — the account is dry. Law 5: report,
don't hammer.

### Class C — Login/paywall walls (3)
- **chatx**, **huggingface**, **veoaifree_chat** → wall text in reply. Correct
  reportable outcome.

### Class D — Single-use / proof-of-work (1)
- **deepseek** → `SINGLE_USE`, matched `pow`. The completion is bound to a one-time
  proof-of-work challenge; replaying the recorded request re-hits a consumed challenge.

### Class E — Empty / proxy dead (1)
- **you.com** (`api.cr-proxy.com`) → 200 but 0-byte body. The proxy accepted the
  request and returned nothing. Upstream is dead or the site id is stale.

### Class F — Schema mismatch: video providers captured as token-API, not HTTP exchange (5)
- **rtst.ai ×4** (`session_rtst_ai*.json`) and **digen.ai**.
These files have `api.token` / `recorded_job` but **no `recorded_exchange`** and no
sentinel in a replayable body. `universal_replay.py` raises
`No recorded_exchange found`. They were captured by a different (token-harvest) path
than the HTTP-exchange path. **They need a video-specific replay client, not the
universal HTTP one.** digen's body uses `video_gen_prompt` (not a chat sentinel), so
even the prompt-injection has no anchor.

### Class G — FALSE NEGATIVES: actually replayable, verdict logic misses it (3)
This is the class that inflates the failure count and is the most fixable:
- **monica** → `NO_ANSWER` but the detail is literally `"omni."` — the model
  **answered the original sentinel**. The replay worked; the prompt-injection did NOT
  substitute (the new phrase never went in), so the keyword check for the new phrase
  failed. Two sub-bugs: (1) injection missed monica's body shape, (2) verdict should
  also accept the ORIGINAL sentinel as proof of life.
- **cohere** → `REPLAY_OK` on requests transport, `NO_ANSWER` on in-browser fetch.
  The answer is present but split across SSE `thinking`/`content-delta` frames. The
  in-browser fetch's early-exit + raw-text keyword match misses it when the phrase is
  fragmented across chunks. Aggregation (already proven in `replay_check`) fixes it.
- **qwen** → same as cohere: `REPLAY_OK` on requests, `NO_ANSWER` on browser fetch
  (answer split across `thinking_summary` SSE frames).

---

## 4. Root-cause ranking (by supply lost)

| # | Root cause | Tabs/sessions lost | Fixable? |
|---|-----------|--------------------|----------|
| 1 | **Gate 2: wrong-exchange capture** (chatgpt, meta) | 2 high-value chat providers | YES — endpoint override / prefer-streaming-response |
| 2 | **Gate 1b: NO_REQUEST** (Claude, Meta, Baichuan) | 3 | PARTIAL — editor-landing + sentinel-match hardening |
| 3 | **Class F: video schema mismatch** (rtst×4, digen) | 5 files | YES — video replay client |
| 4 | **Class G: false negatives** (monica, cohere, qwen) | 3 | YES — verdict + injection fix (pure software) |
| 5 | **Gate 1a: WebSocket-only** (Copilot, Grok) | 2 | ONLY with a WS replay engine |
| 6 | **Class A: auth expiry** (groq, veoaifree, cerebras, gemini) | 4 | RE-CAPTURE (fresh tokens); gemini fixed by browser replay |
| 7 | **Class B/C/D/E: rate, wall, single-use, dead proxy** | 9 | NOT fixable by tooling — account-level / Law 5 |
| 8 | **Gate 1c: NO_TAB domain mismatch** (v0, duck) | 2 | YES — trivial config fix |

---

## 5. The one-sentence answer

> Harvest is failing mostly at **capture**, not at replay: the tool either never
> records a usable exchange (websocket-only, text-never-landed, wrong tab domain), or
> records the **wrong step** of a multi-step flow (chatgpt `prepare`, meta
> `searchconversations`), and a further batch of "failures" are **false negatives**
> (monica/cohere/qwen) where the replay actually works but the verdict/injection logic
> misses it. Only a minority are genuinely dead (rate/wall/single-use/expired-auth).

## 6. Recommended next actions (in ROI order)

1. **Fix the 3 false negatives (Class G)** — pure software, immediate +3 supply:
   accept original-sentinel-as-alive, aggregate SSE frames, fix monica injection.
2. **Add Gate-2 endpoint overrides** for chatgpt (`/backend-api/conversation`) and
   meta (chat mutation `doc_id`) — immediate +2 high-value providers.
3. **Fix NO_TAB domain mapping** (v0.app, duck.ai) — +2 tabs enter the funnel.
4. **Re-capture the 4 auth-expired** (groq, veoaifree, cerebras, gemini) fresh.
5. **Harden NO_REQUEST** (Claude, Baichuan) — editor-landing verification before
   declaring submit.
6. **Build a video replay client** for the 5 token-API files (rtst×4, digen).
7. **Decide on a WebSocket replay engine** for Copilot + Grok (capability gap).
