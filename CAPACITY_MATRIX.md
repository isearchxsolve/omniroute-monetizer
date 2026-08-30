# OmniRoute Monetizer — Capacity Matrix

**Generated:** 2026-08-30 13:05 UTC (live state, not memory)
**Sources:** `state/replay_check.json`, `state/graduation_ledger.json`, `state/profile1_reconciliation.json`, `state/video_capability_matrix.json`, `state/video_route_inventory.json`, `state/video_dedicated_profile_preflight.json`, live OmniRoute `:20128` and consumer `:8190` probes.

---

## 1. Chat Capacity

### 1.1 OmniRoute Core (`:20128`)
- **9,509 models** exposed via `GET /v1/models`.

### 1.2 Canonical Jar-Replay Gate
Source: `state/replay_check.json` (25 seats).

| Verdict | Count |
|---------|-------|
| **REPLAY_OK** | **11** |
| NO_ANSWER | 7 |
| AUTH | 4 |
| WALL | 3 |

**REPLAY_OK hosts (11):**
`api.1min.ai`, `api.cohere.com`, `api.groq.com`, `chat.deepseek.com`, `chat.mistral.ai`, `chat.qwen.ai`, `chatgpt.com`, `claude.ai`, `felo.ai`, `veoaifree.com`, `www.perplexity.ai`

### 1.3 Graduation Ledger
Source: `state/graduation_ledger.json` (34 seats).

| Verdict | Count |
|---------|-------|
| REPLAY_OK | 10 |
| FAIL | 12 |
| NO_ANSWER | 6 |
| WALL | 3 |
| AUTH | 2 |
| UNPARSEABLE | 1 |

**REPLAY_OK (10):** 1min.AI, Claude Official Web, Cohere Coral Web, DeepSeek Chat, Felo AI Web, Genspark AI, Groq Chat, Mistral Le Chat, Perplexity Free Web, Qwen Chat (Alibaba).

### 1.4 Live-Tab Adapter Lane
These providers are Chrome-gated (client-minted anti-bot tokens / SDK sessions) and cannot be jar-replayed. Each is graduated by driving the seat Chrome (`:9222`) composer directly. **Verified by arithmetic probe `41 + 17` → computed `58` (Law 3, not echoable).**

| Provider | Status | Mechanism | Proof |
|----------|--------|-----------|-------|
| **Copilot** | ✅ Graduated | CDP live-tab DOM reader | 58 |
| **Puter** | ✅ Graduated | In-page `puter.ai.chat()` SDK | 58 |
| **V0** | ⏸ Throttled | CDP live-tab composer + poll | 58 proven; account 429-throttled, re-run after decay |
| **Gemini** | 🔧 In progress | Send works (network confirmed); response read TBD | — |

### 1.5 Consumer Endpoint (`:8190`) — what the film kit calls
Base URL: `http://127.0.0.1:8190/v1`
- **9,531 models** exposed via `GET /v1/models`.
- Routes served: `session-pool/auto`, `video/auto`, + 9,526 `host/auto` routes.
- `GET /v1/video/models` → **404** (video lane not currently routed through `:8190`).

### 1.6 Profile-1 Reconciliation
Source: `state/profile1_reconciliation.json` (51 seats).

| Status | Count |
|--------|-------|
| PENDING_EVIDENCE | 21 |
| FAIL | 13 |
| REPLAY_OK | 6 |
| NO_ANSWER | 5 |
| WALL | 3 |
| AUTH | 2 |
| UNPARSEABLE | 1 |

---

## 2. Video Capacity

### 2.1 Video Providers
Source: `state/video_capability_matrix.json` — **22 providers**:

qwen-cloud-token-plan, bailian-coding-plan, vertex (vertex-veo), googleflow (google-flow), kie (kie-video), haiper (haiper-video), leonardo (leonardo-video), pollinations (pollinations-video), minimax (minimax-video), together (together-video), replicate (replicate-video), comfyui + 10 more.

### 2.2 Video Route Inventory
Source: `state/video_route_inventory.json` — **59 total video routes** (ainative provider head).

### 2.3 Dedicated Video Profile
Source: `state/video_dedicated_profile_preflight.json`:
- Providers: `[digen, flow, rtst]`
- **5 enabled accounts** across 3 dedicated profiles: `providers`, `seat2`, `seat3`.
- Preflight status: Chrome not currently open, no job quoted, no job submitted.

---

## 3. Session This Stretch (post power-trip, 2026-08-30)

| # | Provider | Outcome | Commit |
|---|----------|---------|--------|
| 1 | Copilot | ✅ Graduated (live-tab DOM reader, 58) | `4754baf` |
| 2 | Aymo | Closed — paywall (429 body = "Credit limit exceeded", decay-retry disproven) | `5a5450c` |
| 3 | Puter | ✅ Graduated (puter.js SDK, 58) | `6346d89` |
| 4 | Poe | ✅ Graduated (gql_POST REPLAY_OK, pre-existing seat) | `c8131ae` |
| 5 | Monica | ✅ Graduated (deterministic prompt surgery + coherent id rotation, REPLAY_OK) | `c82ea46` |
| 6 | V0 | ⏸ Adapter built + proven (58); account 429-throttled | `f59902e` |

---

## 4. Honest Classifications

- **Not dead, not "rate-limited into the grave":** Every failure this session was classified against the three-cause doctrine with evidence. Aymo's 429 was re-probed after a decay window and reclassified from "transient" to "credit-limit paywall" — that is why decay-retry is not a universal fix.
- **Chrome-gated ≠ dead:** Copilot/Puter/V0/Gemini all fail jar-replay because the browser mints a per-send token. Driving the browser's own composer is the sanctioned fix (operator override #110), not credential invention.
- **V0 429:** a real throttle on rapid automated sends, not a site death. Adapter is correct; re-run after the window decays.
- **No fabricated credentials:** every graduated host is verified with a computed (Law-3) probe, never an echoable keyword.
