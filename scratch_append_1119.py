"""scratch_append_1119.py — append worklog entry #1119 (hard-provider graduation)."""
import pathlib, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENTRY = """

### [2026-08-28 22:55] #1119 — HARD-PROVIDER GRADUATION: copilot, meta.ai, claude.ai, v0.app ALL LIVE ("Omni") THROUGH THE CHROME-BLUEPRINT EVENT-LISTENER RUNTIME. Two operator corrections applied mid-flight: (1) the prompt is the HUMAN part of the play — deliver it through Chrome's input pipeline, never DOM text surgery; (2) NEVER POLL CHROME — listen for the right event (MutationObserver), no setInterval discovery.

**1. TAB SURVEY (todo 1).** scratch_hard_tabs.py enumerated all four seat Chromes (9222-9225). All four hard providers have live signed-in tabs on port 9222:
  - copilot.microsoft.com: 5 tabs (2x /pages/, 1x /tasks/preview, 2x /chats/) — /chats/ is the chat surface; /pages/ is a document tool (already in TAB_EXCLUDES).
  - www.meta.ai: 1 tab (/prompt/<uuid>).
  - claude.ai: 1 tab (/new?incognito=).
  - v0.app: 1 tab (/isearchxsolve-6191s-projects/chat/omni-jvPa7gqKGGu).
  - grok.com: 1 tab (the proven template).
  Ports 9223/9224/9225 hold no hard-provider tabs.

**2. COPILOT WS BLUEPRINT CAPTURED (todo 2, credit-free).** capture_websocket_cdp.py --port 9222 --match "copilot.microsoft.com/chats" --name "Copilot WS":
  - status CAPTURED_WS. wsUrl wss://copilot.microsoft.com/c/api/chat. wsPreexisting false (creation observed after reload). framesSent 3, framesRecv 7, sentinelFrame 2, httpPost false, cookieCount 20. submitStrategy js_click_send (Enter alone did not submit). Seat file state/secrets/session_copilot_ws.json (secret, gitignored).
  - This blueprint is Chrome-blueprint EVIDENCE (what Chrome does). Per the doctrine it is NOT used to build a hand-replay client — copilot is served by the Chrome-blueprint runtime where copilot's own JS plays by itself.

**3. META.AI CAPTURE → NO_SENTINEL_TRANSPORT, AND WHY THAT IS CORRECT.** capture_websocket_cdp.py --port 9222 --match "www.meta.ai" --name "Meta AI WS":
  - textLanded true, composer contenteditable div, 1 ws created, 4 ws frames sent, 13 received, 26 POSTs seen — but NO_SENTINEL_TRANSPORT (no plaintext sentinel match in any frame or POST body), so no seat file written.
  - scratch_meta_dump.py (Chrome-blueprint evidence, kept) dumped the raw traffic: meta.ai's send frame is BINARY — base64 of a JSON envelope {"req-id":..., "payload": base64(protobuf)}. The 21 POSTs were all graphql reads / telemetry / sentry, none carried the prompt. The answer came back over the same binary websocket: RECV frames contained the bytes "Omni" (protobuf field \\n\\x04Omni\\x12\\x04Omni plus a JSON stream {"seq":0,"type":"full","response":{...}}).
  - **OPERATOR PREMISE CORRECTION #1 (the encode/decode question):** the wire carries base64(protobuf) but the page renders plain "Omni" — WHO decoded? NOT Chrome. Meta's OWN JS did BOTH directions: it ENCODED the typed prompt into base64/protobuf before handing it to the websocket, and it DECODED the received frames and rendered "Omni" into the DOM. Encode + decode are 100% the provider's own JavaScript running on the V8 blueprint; the environment never decodes, it only hosts the JS.
  - Consequences applied: (a) NO_SENTINEL_TRANSPORT is NOT a bug and NOT a dead end — the text-match has_sentinel correctly cannot match an intentionally-encoded wire; only meta's JS understands that format. Adding a decoder to capture would be reverse-engineering the provider (playing the provider) — refused. (b) The hand-decode scratch files (scratch_meta_decode.py, scratch_meta_decode2.py, scratch_meta_inspect.py) were the WRONG LAYER and were DELETED. (c) The proof is already sufficient and doctrine-compliant: the page RENDERED "Omni" (done by meta's JS) — that DOM render IS the COMPUTED verification (Law 3). Premise persisted to /memories/repo/doctrine_architecture.md.

**4. CHROME-BLUEPRINT RUNTIME FIX #1 — THE PROMPT IS THE HUMAN PART OF THE PLAY.** First ChromeReplayClient run against meta.ai: ERR NO_ANSWER (90s). Root cause: INJECT_JS did DOM text surgery (value setter / textContent + synthetic input event). The composer is the HUMAN part of the play — meta's editor state machine (Lexical) only accepts input that arrives as genuine input events through Chrome's input pipeline; DOM-injected text shows in the DOM but meta's JS reads its own editor state (empty) and sends nothing. Neither meta nor Chrome was wrong — the prompt was being delivered at the wrong location. Fix: ChromeReplayClient now focuses the composer and delivers the prompt via CDP Input.insertText (the same IME-level edit the capture instrument uses, which had already proven meta accepts it), then reads back via JS_READ_ACTIVE and raises TEXT_REJECTED if the composer did not accept it. After the fix: meta.ai answered "Omni".

**5. CHROME-BLUEPRINT RUNTIME FIX #2 — NEVER POLL CHROME, LISTEN FOR THE RIGHT EVENT (operator correction).** The old POLL_JS scanned the DOM with setInterval every 800ms — polling: asking Chrome "is it there yet?" on a timer. Replaced with LISTEN_JS: a MutationObserver on document.body (childList + subtree + characterData) that fires exactly when the provider's own JS renders/updates the reply — the render IS the event; we listen, we never poll. Mutation bursts are coalesced into one check per requestAnimationFrame (still event-driven: it runs BECAUSE a mutation happened). Stream completion is a 1.2s quiet-debounce that only arms AFTER a render event and only fires when events go quiet — it confirms silence, it never discovers content. A hard timeout remains only as the final fallback (returns the best non-placeholder text seen, flagged unstable). The transient-placeholder guard (v0 "Thinking...", grok "Thinking about your request") is retained: placeholders are tracked but never delivered as the answer. Pre-send snapshot marking (data-crc-seen) and prompt-echo skipping unchanged.

**6. VERIFICATION — ALL FOUR HARD PROVIDERS LIVE THROUGH THE EVENT-LISTENER RUNTIME (Law 3, COMPUTED):**
  - www.meta.ai: OK 20995ms text='Omni' (meta's JS encoded the send, decoded the binary ws stream, rendered Omni; we read the DOM).
  - copilot.microsoft.com: OK 12515ms text='Omni'.
  - claude.ai: OK 13559ms text='Omni'.
  - v0.app: OK 57582ms text='Omni\\n\\nWorked for 8s\\n2:27 AM' — the listener correctly waited past the "Thinking..." placeholder (the old poll had returned the placeholder as the answer) and fired when the real answer rendered.
  All via scripts/automation/chrome_replay_client.py self-test CLI against the :9222 providers profile (automation's own seat Chrome, never the operator's).

**7. DOCTRINE COMPLIANCE.** BE CHROME, NOT THE PROVIDER: no provider protocol was hand-replayed this session; every answer was produced by the provider's own JS playing by itself on the V8 blueprint. Capture = Chrome blueprint (copilot ws blueprint kept as evidence). The two mid-flight corrections (human-part prompt delivery; listen-don't-poll) are both refinements of the same principle: we are the environment, the provider's JS is the contract, and we interact with Chrome the way a human and an event would — not the way a scraper would. Law 5 honored (no walls hit; none would be worked around). CHROME hard rules honored (seat Chromes 9222-9225 only, automation's own profiles).

**Files created:** scratch_hard_tabs.py, scratch_meta_dump.py (blueprint evidence), scratch_append_1119.py.
**Files deleted (wrong layer):** scratch_meta_decode.py, scratch_meta_decode2.py, scratch_meta_inspect.py.
**Files modified:** scripts/automation/chrome_replay_client.py (Input.insertText prompt delivery + read-back gate; POLL_JS replaced by LISTEN_JS MutationObserver event listener; comments updated).
**Seat file (secret, gitignored):** state/secrets/session_copilot_ws.json (copilot websocket blueprint — evidence only, not a replay source).
**Verdict:** copilot, meta.ai, claude.ai, v0.app GRADUATED — all four answer "Omni" through the Chrome-blueprint event-listener runtime. The hard-provider set named in doctrine 3a (grok, copilot, meta.ai, claude, v0) is now fully LIVE. Next: wire these seats into the pool dispatch sweep and run the full fleet verification.
"""

p = pathlib.Path(r"d:\omniroute-monetizer\MASTER_WORKLOG.md")
old = p.read_text(encoding="utf-8")
p.write_text(old + ENTRY, encoding="utf-8")
new = p.read_text(encoding="utf-8")
print("lines before:", old.count("\n"), "after:", new.count("\n"))
print("tail:", new[-200:])
