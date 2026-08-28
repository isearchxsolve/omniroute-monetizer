"""Append worklog entry #1127 (seat Chrome liveness verification) to MASTER_WORKLOG.md."""
import pathlib

p = pathlib.Path("MASTER_WORKLOG.md")

entry = """

### [2026-08-28 12:35] #1127 — SEAT CHROME LIVENESS VERIFIED (operator option b): all 4 seat Chromes ALIVE on CDP 9222-9225; 33/33 chrome-backed seats have live tabs. Honest caveats: tab-open != signed-in != has-credits — the known paywalled/rate-limited seats from #1122 still cannot generate despite open tabs.

**1. THE 4 SEAT CHROMES ARE ALIVE.** GET /json/version on each CDP port:
  - :9222 ALIVE (Chrome/151.0.7922.174) — providers profile, 38 live page targets.
  - :9223 ALIVE (Chrome/151.0.7922.174) — niloy profile, 10 live page targets.
  - :9224 ALIVE (Chrome/151.0.7922.174) — seat2 profile, 1 live page target.
  - :9225 ALIVE (Chrome/151.0.7922.174) — seat3 profile, 12 live page targets.

**2. 33/33 CHROME-BACKED SEATS HAVE LIVE TABS (scratch_chrome_seat_liveness.py, read-only — only GET /json/list, no typing/generation/spend).** For each chrome-backed seat I computed its tab substring exactly the way its client does (chat: inline chrome.tab else CHROME_CLIENTS.get(host, host); video: VIDEO_HOSTS[host]['tab'] else inline) and matched against live page targets on 9222-9225:
  - 14/14 chat seats LIVE (cerebras, claude.ai, copilot x2, deepseek, duck.ai, genspark, gemini, grok x2, meta.ai, v0.app, yi_baichuan, zhipu_glm) — all on :9222.
  - 19/19 video seats LIVE (digen x2, labs.google x3, akool, chatglm, creen, gemini, giz, grok, heygen, magichour, meta, nemovideo, qwen, veoaifree x3) — spread across 9222/9223/9224/9225.
  - 0 seats with NO_TAB.

**3. HONEST CAVEATS (tab-open is NOT the same as usable — §14.5 naming the state verified).**
  - What IS verified: the tab is OPEN in a live seat Chrome (the credential surface is present). This is the "tab is open" state, enforced at call time by the clients (NO_TAB -> failover).
  - What is NOT verified here: (a) signed-in state per tab (would need a per-host doctor probe — heavier, not done); (b) whether the account still has credits. Per #1122, these seats have OPEN TABS but are KNOWN capacity-dead: akool, digen, creen, nemovideo (zero-credit paywalls, Law 5), veoaifree x3 (rate-limited). Their tabs being open does NOT restore their ability to generate.
  - So the accurate statement: 33/33 chrome-backed seats have live tabs (the bonus supply is WIRED and reachable), but the subset that can actually still generate is smaller — the #1122 paywall/rate-limit findings stand.

**4. NET POSITION FOR OIOI/CODEX.** The film runway (110 clips) remains 100% stateless/chrome-independent (5 API seats). The 33 chrome-backed seats are now confirmed WIRED (live tabs on live Chromes) and will contribute as bonus supply to the extent their accounts still have allowance — the pool's failover handles the paywalled/rate-limited ones at call time (wall reported, never retried, Law 5).

**Files added (scratch):** scratch_chrome_seat_liveness.py.
**Verdict:** 4/4 seat Chromes ALIVE; 33/33 chrome-backed seats have live tabs (bonus supply wired). Runway (110 clips) unchanged and chrome-independent. oioi/Codex clear to proceed; bonus seats additive.
"""

text = p.read_text(encoding="utf-8")
if "#1127" in text:
    print("ABORT: #1127 already present")
else:
    if not text.endswith("\n"):
        text += "\n"
    text += entry
    p.write_text(text, encoding="utf-8")
    print("appended #1127")
print("new line count:", len(p.read_text(encoding='utf-8').splitlines()))
