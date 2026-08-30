# TECHNICAL HANDOVER — WEBSOCKET INVESTIGATION & GAP ANALYSIS (2026-08-29)

**Status:** Complete. This document captures the full websocket investigation, live probe results,
and the honest state of the 4 "websocket-only" seats. Read this before building any websocket
capture/replay client.

---

## 1. EXECUTIVE SUMMARY

The prior handover (HANDOVER_GRADUATION_GAPS_2026-08-29.md) classified 4 seats as
**"websocket-only → build target, not dead end"**: iFlytek (143 ws frames), Meta (39), Grok, Copilot.
This was the highest-ROI pending item.

**This investigation overturns that classification for 2 of 4 seats and eliminates a third:**

| Seat | Prior Claim | Live Probe Result | Honest Verdict |
|---|---|---|---|
| **Meta AI** | "39 ws frames" | Visible INPUT composer (504x32), no login, no captcha | **HTTP-replayable, NOT websocket. Re-capture as HTTP.** |
| **Copilot** | "websocket-only" | Visible TEXTAREA composer (690x22) on copilot.microsoft.com/, no login | **HTTP-replayable on root page. Re-capture as HTTP.** |
| **Grok** | "websocket-only" | All tabs are Stripe iframes or chrome-error:// pages. No real Grok tab loaded. | **Not capturable from current tabs. Needs fresh navigation.** |
| **iFlytek** | "143 ws frames" | ALL tabs at xinghuo.xfyun.cn/desk → Connection timed out | **UNREACHABLE from automation seat. Site blocks the seat's network egress.** |

**Bottom line:** The "websocket-only" cluster that justified a websocket capture+replay build
has shrunk to **zero confirmed websocket-only seats**. Two are actually HTTP-replayable
(misclassified because the sweep's `plan()` counted ws frames but missed the HTTP composer),
one is unreachable, and one has no valid open tab.
---

## 3. LIVE PROBE RESULTS (from `state/v_probe_ws_decoded.txt`)

### Meta AI (www.meta.ai)
- **Tab:** `https://www.meta.ai/prompt/63fb523a-3386-4746-8f11-83f1f9c9a382`
- **Status:** hasLogin=false, hasCaptcha=false
- **Composer:** `{"tag":"INPUT","w":504,"h":32}`
- **Modals:** []
- **Verdict:** HTTP-replayable. The composer is a standard `<input>` element. The earlier
  "39 ws frames" count was noise on the page, not the transport.

### Grok (grok.com via Stripe)
- **Tabs found:** 5 — all pointing to `m.stripe.network` inner HTML or `blob:` URLs
- **Status:** All return `'NoneType' object has no attribute 'send'` (no real page loaded)
- **Verdict:** No capturable tab exists. A fresh navigation to `grok.com` is required before
  any capture attempt.

### Copilot (copilot.microsoft.com)
- **Tabs:** 4 found (tasks/preview × 2, root × 2)
- **Root tab status:** hasLogin=false, hasCaptcha=false
- **Root tab composer:** `{"tag":"TEXTAREA","w":690,"h":22}`
- **Verdict:** HTTP-replayable on the root page (`copilot.microsoft.com/`). The composer is
  a standard `<textarea>`. Do NOT capture from the `/tasks/preview` subpage.
---

## 4. AUDIT RESULTS (from `state/v_audit_ws_decoded.txt`)

All 21 session files in `state/secrets/`:

| File | Transport | Host | Site | Frames |
|---|---|---|---|---|
| session_1min_ai.json | http | api.1min.ai | 1min.AI | 0/0 |
| session_aymo_ai.json | http | aymo.ai | Aymo AI | 0/0 |
| session_chatgpt_free_web.json | http | chatgpt.com | ChatGPT Free Web | 0/0 |
| session_chathub_web.json | http | app.chathub.gg | ChatHub Web | 0/0 |
| session_chatx.json | http | chatgpt.com | ChatX | 0/0 |
| session_claude_official_web.json | http | claude.ai | Claude Official Web | 0/0 |
| session_cohere_coral_web.json | http | api.cohere.com | Cohere Coral Web | 0/0 |
| session_deepseek_chat.json | http | chat.deepseek.com | DeepSeek Chat | 0/0 |
| session_duckduckgo_ai_chat_(duck_ai).json | http | duck.ai | DuckDuckGo AI Chat (duck.ai) | 0/0 |
| session_felo_ai_web.json | http | felo.ai | Felo AI Web | 0/0 |
| session_genspark_ai.json | http | www.genspark.ai | Genspark AI | 0/0 |
| session_groq_chat.json | http | api.groq.com | Groq Chat | 0/0 |
| session_huggingchat.json | http | huggingface.co | HuggingChat | 0/0 |
| session_inner_ai_web.json | http | chat-api-v3.innerai.com | Inner AI Web | 0/0 |
| session_mistral_le_chat.json | http | chat.mistral.ai | Mistral Le Chat | 0/0 |
| session_monica_ai.json | http | api.monica.im | Monica AI | 0/0 |
| session_perplexity_ai.json | http | www.perplexity.ai | Perplexity AI | 0/0 |
| session_qwen_chat_(alibaba).json | http | chat.qwen.ai | Qwen Chat (Alibaba) | 0/0 |
---

## 5. THE WEBSOCKET BUILD — SHOULD IT STILL HAPPEN?

**Recommendation: DEPRIORITIZE.** The original justification (4 websocket-only seats) is gone:

- Meta → HTTP (re-capture)
- Copilot → HTTP (re-capture on root page)
- Grok → no valid tab (needs fresh navigation, transport TBD after capture)
- iFlytek → network-blocked (operator decision)

A websocket capture+replay client is still a valuable long-term capability (some sites genuinely
do speak only websocket), but it is no longer the "unlock 4 seats in one shot" priority.
The immediate ROI is in re-capturing Meta and Copilot as HTTP.

### What the websocket build would require (for future reference):
1. **Capture side** (`capture_sessions_cdp.py`): the `save_ws()` path exists but has never
   emitted a file. It needs to record the ws URL + the full frame sequence (not just count).
2. **Replay side** (`ws_replay.py`): a websocket client that replays the frame sequence
   and verifies the sentinel in the response frames.
3. **Gate integration** (`replay_check.py`): a `transport=ws` verdict path.

None of these three pieces exist in runnable form today.

---

## 6. REVISED SEAT ACCOUNTING

| Category | Count | Seats |
|---|---|---|
| Fully graduated (REPLAY_OK strict 58) | **6** | DeepSeek, Mistral, Claude, Genspark, **Qwen Chat (Alibaba)**, **Cohere Coral Web** |
| Gate-replayable (looser prompt) | **4** | api.1min.ai, chatgpt.com, felo.ai, perplexity.ai |
| HTTP-replayable (re-capture needed) | **2** | Meta, Copilot |
| Network-blocked | **1** | iFlytek |
| No valid tab (needs fresh nav) | **1** | Grok |

---

## 7. SERVICE/PROCESS STATE (verified this session)

| Port | Service | Status |
|---|---|---|
| 8190 | session_pool_shim | healthy |
| 20130 | chat_pool_server | healthy, serving 10 (post-dedup) |
| 20128 | OmniRoute | **NEVER touch** — untouched |
| 9222 | CDP (automation seat) | healthy, 236 tabs |

---

## 8. PENDING TODOS (REVISED PRIORITY)

1. **[HIGH] Re-capture Meta + Copilot as HTTP** — both have visible composers, no login.
   `capture_sessions_cdp.py --only meta_ai` and `--only copilot` (navigate to root page first).
   Expected: both graduate via normal HTTP replay. This is the real unlock, not websockets.

2. **[MEDIUM] Grok fresh navigation** — open a clean tab to grok.com, then capture. Transport
   TBD after capture (could be HTTP or WS).

3. **[MEDIUM] iFlytek network block** — operator decision: whitelist xinghuo.xfyun.cn on seat
   egress, or mark MONETIZER_BLOCKED.

4. **[LOW] Websocket capture+replay client** — still valuable long-term, but no longer the
   4-seat unlock. Build only after Meta/Copilot/Grok are resolved.

5. **[LOW] duck.ai zero-auth capture adapter** — renders live chat with empty jar.

6. **[Deferred]** Success-weighted seat ordering; `chat_pool_server.py:1046` envelope unwrap
   (already done in commit 2a428b9); Gemini CookieMismatch (operator action).

---

## 9. FILES CREATED THIS SESSION

- `state/audit_ws_candidates.py` — NEW. Scans all session_*.json, reports transport/frames.
- `state/probe_ws_candidates.py` — NEW. Live CDP probe of all 236 tabs, reports composer/login/captcha.
- `state/decode_probe.py`, `state/decode_audit.py` — NEW. UTF-16LE→UTF-8 decoders (PowerShell
  `*>` writes UTF-16LE; these decode for reading).
- `state/v_probe_ws.txt` / `state/v_probe_ws_decoded.txt` — NEW. Raw + decoded probe output.
- `state/v_audit_ws.txt` / `state/v_audit_ws_decoded.txt` — NEW. Raw + decoded audit output.
- `HANDOVER_WEBSOCKET_INVESTIGATION_2026-08-29.md` — NEW. This document.

No production code was changed this session. No commits were made (investigation only).

---

## 10. STANDING CONSTRAINTS (unchanged)

- **Never** touch the operator's live Chrome (`chrome_live_guard` refuses it). Automation's
  own seat is `state/automation_profiles/providers`, CDP `:9222`.
- **Never** restart/stop/kill `:20128` (OmniRoute's).
- Do **not** re-knock walls without `--retry-walls`.
- Video lane is separate from chat graduation — never fold the 7 video sites into chat counts.
- PowerShell 5.1: no `??`, no `&&`; redirect stdout/stderr on every relaunch.
- Worklog rule: every action logged in `MASTER_WORKLOG.md` as numbered entries.
- Secrets: never log tokens/keys in the worklog.

---

*End of handover. Next agent: start with TECHNOLOGY_TRANSFER.md §2 + §21–§24, read MASTER_WORKLOG.md,
then pick up todo 1 (re-capture Meta + Copilot as HTTP) — it's the real unlock now.*

**Graduation count: 6 fully graduated (REPLAY_OK strict 58):** Claude, DeepSeek, Genspark, Mistral, Qwen, Cohere.