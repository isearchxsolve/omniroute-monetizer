# TECHNICAL HANDOVER — CHAT-SEAT GRADUATION PASS (2026-08-29)

**Status:** Session ended with the graduation pass complete-but-unlogged. This document is the
authoritative state transfer. Read this before touching `graduate_all_seats.py`, the gate, the
pool, or any seat transport.

---

## 1. WHAT GRADUATED (VERIFIED SUPPLY)

The graduation pass drives: **capture a real browser request → replay it independently from
Python → verify the numeric sentinel `58` comes back.** Only seats that finish all three steps
count as `REPLAY_OK`.

| Seat | Host | Verdict | Detail |
|---|---|---|---|
| DeepSeek Chat | chat.deepseek.com | **REPLAY_OK** | `58` |
| Mistral Le Chat | chat.mistral.ai | **REPLAY_OK** | `58` |
| Claude Official Web | claude.ai | **REPLAY_OK** | `58` |
| Genspark AI | www.genspark.ai | **REPLAY_OK** | `58` |

**Canonical gate (`state/replay_check.json`) has 11 REPLAY_OK rows across 10 hosts** (the stricter
gate prompt is `"the holy cow jumps over the stricks"`; graduation's strict prompt is `58`):

`api.1min.ai, api.cohere.com, chat.deepseek.com, chat.mistral.ai, chat.qwen.ai, chatgpt.com,
claude.ai, felo.ai, veoaifree.com, www.perplexity.ai`

Pool `:20130` (PID 34888, restarted 21:03:21) is **serving 12 providers, readyNow=12.**

### ⚠ PHANTOM DUPLICATES IN THE GATE
`chatgpt.com` and `veoaifree.com` each appear **twice** in `results[]`. Two of the 12 pool
providers are duplicates. Root cause: `replay_check.py` matched two session files for the same
host (e.g. `session_veoaifree.json` AND `session_veoaifree_chat_web.json` both exist). **Todo:**
dedupe the gate by host so the pool stops listing phantom duplicates.

---

## 2. THE 77 → 4 FUNNEL (WHY NOT ALL 77)

| Stage | Count | Note |
|---|---|---|
| Tabs in Chrome | ~75 | many duplicates (GLM alone had 4 tabs), login walls, docs, non-chat pages |
| Eligible chat sites | 32 | `classify_tab()` output |
| Video-lane sites | 7 | deliberately separate lane (HeyGen, MagicHour, Akool, NemoVideo, +) — **never part of chat graduation** |
| Fully graduated (REPLAY_OK strict `58`) | **4** | see §1 |
| Replayable in gate (looser prompt) | 10 | these work for the pool but failed the strict `58` check in-pass |
| Non-verifying verdicts | 28 | see §3 taxonomy |

The 77-tab number is **not** the right denominator — most tabs are duplicates/walls, and 7 are
video lane by design. The honest supply count today is **4 fully graduated + 10 gate-replayable.**

---

## 3. GAP TAXONOMY (28 NON-VERIFYING SEATS)

Verdict counts from `state/graduation_ledger.json` (32 seats tracked):

| Verdict | Count | Seats | What it means |
|---|---|---|---|
| FAIL | 15 | Together, Cerebras, Zhipu GLM, Copilot, Grok, Meta, iFlytek, Baichuan, Doubao, Coze, Pollinations, V0, Yuewen, duck.ai, 1min.AI | no visible composer OR websocket-only OR nothing submitted |
| NO_ANSWER | 7 | Qwen, Cohere, Felo, Perplexity, Monica, Aymo, Inner AI | HTTP 200 but reply isn't the sentinel `58` (often a real answer like `58what is 58 multiplied by 3is 58 a prime nu`, or an error body) |
| AUTH | 2 | ChatHub, Groq | cookie alone is not enough — server needs real auth beyond the jar |
| WALL | 3 | SambaNova, HuggingChat, You.com | login wall; **recorded once, never re-knocked** (policy) |
| UNPARSEABLE | 1 | ChatGPT Free | 200 but no recognized response shape |
| REPLAY_OK | 4 | DeepSeek, Mistral, Claude, Genspark | ✅ graduated |

### Websocket-only seats (the biggest unlockable cluster)
- **iFlytek SparkDesk** — 0 posts / **143 ws frames** → captured a websocket, not HTTP POST.
- **Meta AI Web** — 11 posts / **39 ws frames**.
- **Grok on X / Grok Web**, **Microsoft Copilot Web** — not replayable as HTTP.

Per the **Chrome-gap doctrine** these are **build targets, not dead ends**: Chrome speaks the
websocket, so a **websocket capture + replay client** unlocks iFlytek, Meta, Grok, Copilot in one
shot. This is the highest-ROI pending engineering item.

### No-visible-composer seats
Cerebras, Coze, Doubao, Pollinations, duck.ai — the sweep's `plan()` couldn't find the submit box.
duck.ai is a **zero-auth** site (declared `session_only` in readiness; renders live chat UI with
empty jar) so it's worth a dedicated capture adapter.

---

## 4. OPEN DEFECTS

### D1 — `graduate_all_seats.py` hangs after `restart_pool()` (⚠ CRITICAL)
Run 3 **completed all captures and rebuilt the gate**, then the process hung *after* the pool
restart and before the final `save_ledger()` + `append_worklog()`. Symptoms:
- Two `graduate_all_seats.py --apply` processes (PID 33600 venv + 30748 Python311) were still
  alive 40+ min after start with near-zero CPU.
- The pool DID restart (PID 34888 at 21:03:21) — so step 3's `restart_pool()` ran.
- `MASTER_WORKLOG.md` was last written 20:30:58 (run 1's NameError-era table). **Run 3's verdict
  table and `runs[]` entry were never appended.**
- The ledger `runs[]` still contains only run 1 (`planned: 25, graduated: []`).

**Cause hypothesis:** `restart_pool()` uses `urllib.request.urlopen(POOL_HEALTH)` with
`timeout=8` but no overall bound — a hung `/health` (or a `Start-Process` deadlock from
`run(["powershell", ...])` inheriting handles) can block indefinitely. The two-process spawn
(venv + system Python both running the same script) suggests a duplicate-invocation problem too.

**Fix (todo):** wrap step 3 in a hard overall timeout / run `restart_pool()` in a thread with a
bound; ensure the final `save_ledger`/`append_worklog` are in a `finally` block; guard against
double-spawn. **I killed the stuck processes** — the system is clean now, but run 3's log entry
still needs to be written (see §6).

### D2 — Missing scratch verdicts (7 session files with no replay verdict)
Scratch has 15 `replay_*.json`; **21** session files exist. These have no scratch verdict:
`session_1min_ai, session_chatx, session_duckduckgo_ai_chat_(duck_ai),
session_qwen_chat_(alibaba), session_v0_by_vercel_(v0_app), session_veoaifree,
session_veoaifree_chat_web`.
- duck.ai captured fine (890B `/duckchat/v1/chat`) but the scratch verdict never wrote —
  **slug mismatch**: `replay_duckduckgo_ai_chat_(duck_ai).json` (parentheses) vs the sweep's glob
  expectation. Verify the filename slug conversion in `scratch_report()` / `execute_one()`.
- Qwen, V0, 1min.AI similar — the run-3 log shows them captured but their scratch verdicts are
  absent (the hang may have cut them off).

### D3 — Run-3 results not in the worklog/ledger
Because of D1, the run-3 table (all 32 per-seat verdicts — see `state/grad_apply_run3.log`,
complete through `[31/31]` + `step 3 graduate -- 4 seat(s) replayed clean: DeepSeek Chat, Mistral
Le Chat, Claude Official Web, Genspark AI` + `canonical gate rebuilt: True {'REPLAY_OK': 11,
'NO_ANSWER': 6, 'AUTH': 2, 'WALL': 2}`) was never appended. **Todo:** write the run-3 entry
manually or re-run a post-hoc `append_worklog()` against the ledger.

### D4 — First-run guard per-seat fix (COMPILED, UNTESTED IN FLIGHT)
`graduate_all_seats.py` guard changed from whole-ledger-empty to per-seat:
```python
if (site not in ledger["seats"] and t.get("latestReplayVerdict") == "REPLAY_OK"
    and not args.redo_passed):
    skipped.append((site, "manifest verdict REPLAY_OK (not in ledger, proven supply)"))
```
This applies to **future** runs (run 3 loaded old code). Next `--apply` should now skip the 7
proven REPLAY_OK seats instead of re-capturing them.

### D5 — Captured-session NameError (FIXED, VERIFY)
`capture_sessions_cdp.py:794` `assert_safe_cdp_port(port)` → `assert_safe_cdp_port(a.port)`.
This fixed the run-1 crash that failed all 25 seats. Verified: single-site duck.ai capture works.

---

## 5. SERVICE/PROCESS STATE (verified clean)

| Port | Service | PID | Started | Status |
|---|---|---|---|---|
| 8190 | session_pool_shim (our task-owned) | 19016 | 18:33 | healthy, `GET /v1/models` → 200 |
| 20130 | chat_pool_server (Anthropic-face pool) | 34888 | 21:03 | healthy, served 12 / readyNow 12 |
| 20128 | **OmniRoute (NEVER touch)** | 22364 | — | untouched |

**⚠ Two shim processes exist (12596 venv + 19016 Python311) — both are `session_pool_shim.py 8190`;
19016 owns the port. Same for chat_pool_server (34088 + 34888); 34888 owns 20130. The non-owner
twins are leftover double-spawns. Todo: identify and clean the non-listening duplicates.**

---

## 6. PENDING TODOS (PRIORITIZED)

1. **[D1] Fix the post-restart hang** in `graduate_all_seats.py` (bound `restart_pool`, `finally`
   the ledger/worklog write, guard double-spawn).
2. **[D3] Write run-3 worklog entry** (table from `state/grad_apply_run3.log`) + record the run in
   `ledger["runs"]` — the data exists, only the append is missing.
3. **[D2] Fix scratch-slug mismatch** so every captured session gets a verdict file
   (parentheses/underscore normalization).
4. **[D1-dupe] Clean the duplicate shim/pool processes** (non-port-owner twins).
5. **[Phantom dupe] Dedupe the gate by host** so the pool stops listing `chatgpt.com`/`veoaifree.com` twice.
6. **[High ROI] Websocket capture+replay client** → unlocks iFlytek, Meta, Grok, Copilot (4 FAIL seats in one shot).
7. **[Zero-auth] duck.ai dedicated capture adapter** (renders live chat with empty jar).
8. **[Deferred] Success-weighted seat ordering** in `session_pool.py` `pick()` (~line 556-563).
9. **[Deferred] `chat_pool_server.py:1046` defect #8** — unwrap `{"tool": null, "text": ...}` envelope gated on tools present.
10. **[Operator] Gemini CookieMismatch** — `accounts.google.com` blocked by `UNSUITABLE_HOSTS`; needs manual Google session repair on the automation seat (flagged, not automated).

---

## 7. STANDING CONSTRAINTS (DO NOT RE-LEARN)

- **Never** touch the operator's live Chrome (`chrome_live_guard` refuses it). Automation's own
  seat is `state/automation_profiles/providers`, CDP `:9222`.
- **Never** restart/stop/kill `:20128` (OmniRoute's).
- Do **not** re-knock walls without `--retry-walls`; do **not** raise try ceilings on `:8190`.
- Video lane is separate from chat graduation — never fold the 7 video sites into chat counts.
- PowerShell 5.1: no `??`, no `&&`; redirect stdout/stderr on every relaunch; `OMNI_VIDEO_CONFIRM_SPEND=1` on shim launch.
- Worklog rule: every action logged in `MASTER_WORKLOG.md` as numbered `### [timestamp] #N — title`; incremental commits (rule 2) — none were made for this session's changes yet.
- Secrets: never log tokens/keys in the worklog (redact).

---

## 8. FILES THAT CHANGED THIS SESSION

- `scripts/automation/harness_all_tabs.py` — NEW (tab harness: navigate/probe/SSO/verdict; report → `state/tab_harness_report.json`).
- `scripts/automation/capture_sessions_cdp.py` — FIXED `assert_safe_cdp_port(a.port)`.
- `scripts/automation/graduate_all_seats.py` — per-seat first-run guard (D4).
- `scripts/automation/seat_readiness_audit.py` — VIDEO_TARGETS +4 (HeyGen, MagicHour, Akool, NemoVideo).
- `scripts/automation/tab_graduation_sweep.py` — CHAT_SURFACE_PREFIX, HARNESS_NAVIGATE, ZERO_AUTH_SITES (duck.ai, yuewen.cn), VIDEO_SITES +4.
- `state/free_llm_chat_sites.json` — +3 harness-discovered chat groups, +1 video generators group.
- `HANDOVER_8190_SHIM_2026-08-29.md` — prior shim handover (read it too).
- `MASTER_WORKLOG.md` — #1155 logged; run-1 table present; **run-3 table MISSING (todo D3)**.
- `state/graduation_ledger.json` — 32 seats tracked; `runs[]` has run 1 only.
- `state/replay_check.json` — canonical gate, 11 REPLAY_OK (with phantom dupes, §1).
- `state/grad_apply_run3.log` — complete run-3 transcript (the source for todo D3).

---

*End of handover. Next agent: start with `TECHNOLOGY_TRANSFER.md` §2 + §21–§24, read `MASTER_WORKLOG.md`,
then pick up todo 1 (D1 hang fix) — it's the blocker for every future graduation run.*
