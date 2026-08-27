import pathlib, datetime
p = pathlib.Path("MASTER_WORKLOG.md")
entry = """

---

### [2026-08-28 01:15] #1113 — RUNTIME-CHROME IS AN ANTI-PATTERN: operator's correction accepted — a live Chrome tab per request serializes ALL calls through ONE global driver lock, defeating the breadth-not-depth spreader; implemented the opt-in "runtime: replay" graduation lever so seats are served by stateless HTTP replay (curl_cffi browser-TLS) instead of a live browser; 12 chat seats statically ready to graduate, 2 video blocked (no url/body/cookie)

**Operator correction (overrides the demand-paging proposal from #1112's follow-up):** "runtime requires hitting chrome is a real anti pattern and may cause race condition during concurrent request — exact premise we were trying to solve earlier." The demand-paging plan (wake/park Chrome on demand) is WITHDRAWN — it still left Chrome inside the request path. The correct doctrine: **Chrome is a capture / onboard / re-auth instrument, NOT a runtime server.**

**1. EVIDENCE — the concurrency anti-pattern is real and verifiable in code:**
- `chrome_replay_client.py:103`: `_DRIVER_LOCK = threading.Lock()  # held for the WHOLE call: one browser, one typist`. Every Chrome chat call holds a SINGLE global lock for its entire duration (up to 90s). Concurrent requests don't run in parallel — they serialize into a single-file queue behind one lock. Remove the lock and it's worse: two calls drive the same tab at once → interleaved typing, corrupted DOM, wrong answer read back. Either way, runtime-Chrome is structurally incapable of concurrent serving — the exact opposite of the breadth-not-depth load spreader built in #1109/#1110.
- `chrome_video_client.py:53` confirms the video path deliberately dodges that lock with raw CDP, but it's still one live tab per host driving a DOM — same ceiling.
- Chrome RAM cost (measured earlier): 139 chrome.exe processes, ~8.1 GB across ports 9222-9225.

**2. THE WAY OUT — stateless HTTP replay is already in-house and parallel-safe:**
- `universal_replay.py` / `video_universal_replay.py` replay the recorded genuine exchange server-side with the grabbed cookie via `curl_cffi` (Chrome TLS Client-Hello + HTTP/2 impersonation, Law 4). No browser in the request path → each call is an independent HTTP request → parallelizes cleanly across hosts. `curl_cffi 0.16.2` confirmed installed.
- The historical comment in `_client_for` said these hosts "fail requests replay (CORS/PoW/x-sign)" — but that evidence PREDATES curl_cffi's browser impersonation. So it must be RE-VERIFIED per seat, not assumed (Law 3: verification COMPUTED).

**3. ZERO-COST GRADUATION AUDIT (read seat files only, NO provider calls):**
- Chrome-backed seats WITH a recorded_exchange + cookie: 14 (12 chat + 2 video) → graduation candidates.
- Chrome-backed with NO recording: 21 → genuinely need Chrome, but only for CAPTURE, not runtime.
- Static validation of the 14 (url + method + body + cookie present):
  - READY for stateless replay (12 chat): api.1min.ai, api.cohere.com, api.groq.com, chat.cerebras.ai, chat.deepseek.com, chat.mistral.ai, chat.qwen.ai, chatglm.cn, chatx.ai, felo.ai, gemini.google.com, www.perplexity.ai.
  - BLOCKED (2 video): digen.ai (recorded_exchange has no url/body — different shape), labs.google (no url/body AND no cookie — needs re-auth first).

**4. FIX — the opt-in graduation lever in `session_pool.py::_client_for()`:**
- A seat that carries a `recorded_exchange` (or `recorded_job`) AND declares `"runtime": "replay"` is now dispatched to the stateless replay client BEFORE any Chrome dispatch. Opt-in per seat: nothing changes until a seat is explicitly graduated → safe by default.
- Dispatch precedence: api.kind (rtst/youcom) → runtime:replay (NEW) → video Chrome → CLIENTS substring → Chrome chat → universal fallback.
- `runtime:replay` with a `recorded_job` (and no exchange) or `modality=video` → VideoUniversalSessionClient; else UniversalSessionClient.

**5. OFFLINE PROOF (scratch_graduation_lever_test.py, 7 dispatch cases — ALL PASS):**
- graduated chat → UniversalSessionClient; graduated video (modality) → VideoUniversalSessionClient; graduated video (job-only) → VideoUniversalSessionClient;
- NOT graduated chat → ChromeReplayClient; NOT graduated video → ChromeVideoClient (no regression);
- runtime:replay but NO blueprint → falls back to ChromeReplayClient (safe);
- api.kind rtst wins over everything (precedence preserved).

**6. NEXT (not yet done — needs live verification, spends credits):**
- Live-verify each of the 12 ready chat seats with ONE call each via the replay client; graduate the passing ones by setting `"runtime": "replay"` in their seat files.
- Capture blueprints for the 21 chrome-only seats (Chrome as capture instrument).
- Prove concurrent throughput with the driver lock out of the path.

**Files changed:** scripts/automation/session_pool.py (graduation lever in _client_for)
**Files created (scratch, zero-cost audits):** scratch_graduation_audit.py, scratch_static_validate.py, scratch_graduation_lever_test.py
**Verdict:** operator's correction accepted and implemented as an opt-in lever. Runtime serving can now leave Chrome for any seat with a proven blueprint; Chrome is demoted to capture/onboard/re-auth. 12 seats ready to graduate pending one-call live verification each.
"""
with open(p, "a", encoding="utf-8", newline="\n") as f:
    f.write(entry)
print("appended #1113, new total lines:", len(p.read_text(encoding='utf-8').splitlines()))
