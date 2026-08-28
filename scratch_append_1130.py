"""Append worklog entry #1130 (operator doctrine override: full Chrome independence, hand-rolling authorized).
Idempotent: skips if '#1130' already present. Never logs secrets.
"""
import pathlib

ENTRY = """

### [2026-08-28 13:54] #1130 — OPERATOR DOCTRINE OVERRIDE: FULL CHROME INDEPENDENCE. Hand-rolling send-time fields in Python (PoW recompute, X-Sign recompute, websocket/multi-step replay) is now AUTHORIZED where the situation demands. Law 4 "never reconstruct" and Doctrine 3a "never hand-replay" LIFTED for this purpose; Laws 1/2/3/5 remain in force. Override recorded durably in TECHNOLOGY_TRANSFER.md Law 4 + session_pool.py dispatch comment. Execution plan for the 33 laid out; execution begins with the cheap wins.

**1. THE DIRECTIVE (operator, verbatim intent).** After #1129's tiered verdict, the operator ruled: "the situation calls for following the anti pattern... following v8 pattern is now proved costly... so we go for full chrome independence... which means you handroll whenever situation demands" — explicitly citing (1) PoW (x-ds-pow-response) and signature (X-Sign/X-Nonce) recomputation in Python, and (2) the realistic candidates (meta.ai re-capture, v0.app multi-exchange, digen un-shadow). The V8 cost driver (per #1129: lock-serialization + UI latency + RAM, NOT per-execution forking) is accepted as the business reason. This is the operator's doctrine to set; it is recorded, not debated.

**2. THE OVERRIDE, RECORDED DURABLY (so no future agent "fixes" it back).**
  - TECHNOLOGY_TRANSFER.md §2 Law 4: appended an "OPERATOR OVERRIDE — 2026-08-28" block: hand-rolling send-time fields in Python is authorized for full Chrome independence; Law 4 and Doctrine 3a are LIFTED for this purpose; Laws 1, 2, 3, 5 remain fully in force (a hand-rolled seat graduates ONLY after Law-3 computed verification — arithmetic probe -> 58, never echoable; walls still reported never solved).
  - scripts/automation/session_pool.py: the Doctrine 3a "no hand-replay client" comment in _client_for now carries the same override note; dispatch changes per-seat as seats graduate (runtime:replay / api.kind / dedicated client), never wholesale.
  - Guardrails that SURVIVE the override: Law 3 computed verification gates every graduation (no false greens); Law 5 walls (captcha/card/quota) still FULL STOP; secrets never logged; §24 hot-reload (no shim restarts for seat flips); task ownership of :8190 respected.

**3. PRIOR ART FOUND (grep).** selenium_browser_replay.py already contains SEND_TIME_RULES (mistral messageId, chathub streamId+x-client-time, felo search_uuid, huggingface generationId, chatglm nonce/timestamp/request-id — with the explicit note "x-sign needs the signing algo — deeper gap") and LIVE_BEARER_RULES (groq Stytch JWT harvest) — but those execute INSIDE the browser. The hand-roll work = porting equivalent send-time logic to pure Python (curl_cffi transport). replay_check.py already classifies INVALID_POW_RESPONSE as a spent-PoW signature. adapter_invoke_generic.py mentions chatglm x-sign as a known gap.

**4. EXECUTION PLAN (ordered cheap-first, each seat Law-3-verified before flip).**
  - P1 digen_ai (video): stateless client ALREADY EXISTS (digen_session_replay.py::DigenSessionClient, pure requests + Digen-Token). Work: read-only token-liveness check (GET /v1/queue/list?status=3 + HEAD sentinel video_url), then un-shadow (dispatch currently routes modality=video+VIDEO_HOSTS to ChromeVideoClient BEFORE the CLIENTS map). Cheapest possible win.
  - P2 meta.ai (chat): cookie is LIVE (200 in #1128 re-test) — the recording is a capture bug (search doc_id, not chat-send). Work: re-capture the actual chat-send request from the seat Chrome tab via CDP (Network.enable around a real send), write recording, Law-3 verify, flip runtime:replay.
  - P3 deepseek (chat): hand-roll the PoW. Work: extract the PoW algorithm from deepseek's JS bundle (read-only fetch of the bundle, find the x-ds-pow-response generator), implement in Python, refresh at send-time, Law-3 verify, flip.
  - P4 zhipu/chatglm (chat): hand-roll X-Sign. Work: extract the signing algorithm (X-Sign/X-Timestamp/X-Nonce/X-Request-Id) from chatglm's JS, implement in Python, Law-3 verify, flip. SEND_TIME_RULES already refreshes nonce/timestamp/request-id in-browser; the missing piece is the signing algo itself.
  - P5 v0.app (chat): multi-exchange capture. Work: capture the full ack->run-pipeline->poll->result sequence (video job recorder pattern), implement as multistep_replay follow-up or dedicated client, Law-3 verify, flip. Beware the #1120 false-green "Cooking..." placeholder — needs a stable reply selector.
  - P6 cerebras + gemini (chat): both tried-and-reverted (replay_graduation='reverted_send_time_gate'). Work: fresh re-capture of the send request + bearer from live tabs, Law-3 verify, flip; expect possible repeat rotation (bearers rotate server-side) — if so, document and leave on V8.
  - P7 the 25 live-tab-only seats: capture pass first (capture_sessions_cdp for chat, record_video_job for video), then per-seat tier classification + hand-roll where demanded. Websocket seats: capture URL+auth+frame sequence, build websocket replay clients (doctrine 3a lift applies). Largest work item; done after P1-P6 prove the pipeline.
  - labs.google (video): NO work — already stateless via the Flow bridge (#1123).

**5. STATUS.** Override recorded + committed. Execution begins with P1 (digen) immediately after this entry. Each P-step gets its own worklog entry with Law-3 evidence before any runtime flip.

**Files changed:** TECHNOLOGY_TRANSFER.md (Law 4 override block), scripts/automation/session_pool.py (Doctrine 3a override note).
**Verdict:** Directive accepted and durably recorded. Full Chrome independence is now the mission; hand-rolling authorized; Law-3 verification remains the graduation gate. Plan P1-P7 laid out, cheap-first.
"""

p = pathlib.Path("MASTER_WORKLOG.md")
t = p.read_text(encoding="utf-8")
if "#1130" in t:
    print("SKIP: #1130 already present")
else:
    if not t.endswith("\n"):
        t += "\n"
    p.write_text(t + ENTRY, encoding="utf-8")
    print("APPENDED #1130. New line count:", (t + ENTRY).count("\n") + 1)
