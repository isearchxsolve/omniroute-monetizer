"""Append worklog entry #1126 (honest seat-tier audit) to MASTER_WORKLOG.md."""
import pathlib

p = pathlib.Path("MASTER_WORKLOG.md")

entry = """

### [2026-08-28 12:15] #1126 — HONEST SEAT-TIER AUDIT (operator asked to "confirm ALL tabs graduated to stateless chrome-independent"): CANNOT CONFIRM — it is not true. 33 of 56 seats are still CHROME-BACKED (the live signed-in tab IS the credential). Only 23 are stateless. BUT the film RUNWAY oioi needs is 100% stateless/chrome-independent (5 API seats = 110 clips), so the 2x3-min attempt does NOT depend on Chrome.

**1. THE AUDIT (scratch_seat_tiers.py, read-only, per-seat, against actual dispatch ground truth = client_cls, not assumption).** Classified every seat by TECHNOLOGY_TRANSFER §23 tiers:
  - STATELESS-REPLAY: file-backed recorded bytes replayed over pure HTTP (UniversalSessionClient / VideoUniversalSessionClient / ChatXReplayClient). No Chrome.
  - API-CREDENTIAL: bearer-token seat with a documented contract (RtstApiClient / FlowApiClient / YouComApiClient). No Chrome.
  - CHROME-BACKED: ChromeReplayClient / ChromeVideoClient — the live signed-in tab IS the credential; NEEDS a live seat Chrome (9222-9225).

**2. THE NUMBERS.**
  - CHAT: 32 seats -> 18 stateless (17 REPLAY + 1 API you.com) | 14 CHROME-BACKED.
  - VIDEO: 24 seats -> 5 stateless (ALL API: labs_google_flow + rtst x4) | 19 CHROME-BACKED.
  - TOTAL: 56 seats -> 23 stateless | 33 CHROME-BACKED.
  - ANSWER: NOT ALL seats are stateless chrome-independent. 33 still need a live seat Chrome.

**3. THE GRADUATION LEVER + WHY SOME SEATS WITH RECORDINGS STILL NEED CHROME.** session_pool._client_for has an explicit graduation lever (worklog #1113): a seat carrying `"runtime": "replay"` AND a recording is served by the stateless HTTP replay client (curl_cffi browser-TLS impersonation) INSTEAD of a live tab — checked BEFORE every Chrome dispatch. Only 8 seats carry it: 1min_ai, chatx, cohere_coral_web, felo_ai_web, groq_chat, mistral_le_chat, perplexity_free_web, qwen_chat. 17 more seats HAVE recordings but are NOT graduated:
  - 8 are routed to CHROME anyway because their host is in the CHROME_CLIENTS registry and Chrome dispatch is checked before universal replay: cerebras, deepseek, google_gemini_web, meta_ai_web, v0_app, zhipu_glm_chat, digen(video), labs.google(video). These were proven REPLAY_OK only THROUGH live Chrome — pure Python `requests` replay fails (CORS / PoW / x-sign / live bearer), so they MUST be driven in the attached browser even though bytes exist. They cannot go stateless without a protocol hand-replay, which the doctrine forbids ("BE CHROME, NOT THE PROVIDER").
  - 9 are served by universal replay anyway (not in CHROME_CLIENTS): aymo, chatgpt_free_web, chathub, huggingchat, inner_ai, monica, veoaifree x2, you_com_chat — these ARE effectively stateless even without the flag.

**4. WHAT THIS MEANS FOR THE FILM ATTEMPT (the thing oioi/Codex actually needs).** The 2x3-min runway (110 clips, #1124) is built ENTIRELY from the 5 stateless API seats: labs_google_flow (103 clips) + rtst x4 (7 clips). ZERO of the runway depends on Chrome. The 19 Chrome-backed video seats and 14 Chrome-backed chat seats are BONUS supply — upside if the 4 seat Chromes are alive — but they are NOT required for the attempt. So oioi/Codex can proceed; the film path is chrome-independent.

**5. FAILURE-HONESTY NOTE.** The operator's phrasing assumed a prior graduation was complete. Per the doctrine (anti-pattern: false greens; rule 14.5 "the bare word 'signed in' is banned"; "never mark broken work as done"), I am NOT confirming a green that isn't real. The accurate statement is: "the film runway is stateless/chrome-independent; the broader pool is 23/56 stateless, 33/56 still chrome-backed."

**Files added (scratch):** scratch_seat_tiers.py.
**Verdict:** NOT ALL tabs graduated. 23/56 stateless, 33/56 chrome-backed. Film runway (110 clips) is 100% stateless and chrome-independent — oioi/Codex clear to proceed. If the operator wants the 33 chrome-backed seats contributing too, the 4 seat Chromes (9222-9225) must be alive; they are bonus, not required.
"""

text = p.read_text(encoding="utf-8")
if "#1126" in text:
    print("ABORT: #1126 already present")
else:
    if not text.endswith("\n"):
        text += "\n"
    text += entry
    p.write_text(text, encoding="utf-8")
    print("appended #1126")
print("new line count:", len(p.read_text(encoding='utf-8').splitlines()))
