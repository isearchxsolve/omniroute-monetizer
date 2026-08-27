# -*- coding: utf-8 -*-
"""Append worklog entry #1105 (tab-coverage sweep) to MASTER_WORKLOG.md."""
import pathlib

ENTRY = """

### [2026-08-27 23:30] #1105 — TAB-COVERAGE SWEEP: 9 signed-in-but-unwired tabs found; 4 wired LIVE via Chrome bridge (claude.ai, grok.com, copilot.microsoft.com, v0.app), 3 retired honestly (duck.ai CAPTCHA, genspark/yi.baichuan DOM misfires), 2 video tabs deferred to video-capture path

**Trigger:** operator question "So all tabs covered". Answer was NO — a coverage
audit found 9 signed-in tabs with no seat and no bridge entry. This entry wires the
chat-capable ones into the pool and retires the ones that cannot be served honestly.

**1. Coverage audit (`scratch_tab_coverage.py`):** 30 unique open-tab hosts in the
:9222 providers profile; 20 covered, 10 uncovered. `app.innerai.com` was initially
flagged uncovered but is actually covered — its seat host is the API origin
`chat-api-v3.innerai.com` (seat `session_inner_ai_web.json`, dispatchable via
UniversalSessionClient; `selenium_browser_replay.py::API_ORIGIN_TO_TAB_ORIGIN` maps
the API origin to the `app.innerai.com` tab). Genuinely uncovered: copilot.microsoft.com,
claude.ai, grok.com, duck.ai, genspark.ai, v0.app, yi.baichuan-ai.com (chat), plus
labs.google (Flow) and nemovideo.com (video).

**2. Sign-in verification (`scratch_probe_uncovered.py`):** all 9 uncovered tabs
probed read-only — every one shows a composer and NO login CTA → all signed in.
Per the Adapter Thesis (#1094), a signed-in tab IS the credential.

**3. Wiring:** 7 chat hosts added to `CHROME_CLIENTS` in `chrome_replay_client.py`
(copilot.microsoft.com, claude.ai, grok.com, duck.ai, genspark.ai, v0.app,
yi.baichuan-ai.com→substring baichuan-ai.com). 7 chrome-backed seat files created in
`state/secrets/` (`scratch_create_chrome_seats.py`): session_copilot_msft.json,
session_claude_ai.json, session_grok_com.json, session_duck_ai.json,
session_genspark_ai.json, session_v0_app.json, session_yi_baichuan.json. Pool check:
35 seats / 33 dispatchable, all 7 DISPATCHABLE (chrome-backed seats need no recording).

**4. DOM diagnosis (`scratch_diag_new_tabs.py`, read-only):** predicted bridge
compatibility per host before spending any operator chat turns:
- claude.ai: contenteditable composer + 56 response containers (sentinel "Omni" in
  `font-claude-response-body`) → compatible.
- grok.com: contenteditable composer + 10 containers (`response-content-markdown`) →
  compatible.
- copilot.microsoft.com: `textarea#userInput` + 5 containers → test.
- v0.app: contenteditable composer + 9 containers → test.
- genspark.ai: only visible textarea is the agent's "Additional details (optional)"
  field — NOT a chat composer → misfire, retired without testing.
- yi.baichuan-ai.com: ZERO containers match the generic poll selectors even with
  existing content → NO_ANSWER certain, retired without testing.
- duck.ai: 0 containers (see CAPTCHA below).

**5. Retirements (honest, via the pool's own status mechanism — alive:false flip,
never file deletion):**
- **duck.ai** (`scratch_retire_duckai.py`): the bridge test triggered DuckDuckGo's
  bot-detection CAPTCHA ("Select all squares containing a duck") — the NO_ANSWER was
  the reply being blocked by the challenge. **CAPTCHA bypass is prohibited**
  (AGENTS.md rule 7 / CHROME_RULES). A CAPTCHA wall is a correct, reportable outcome.
  Recovery: operator solves the challenge manually once in the tab, then flip alive:true.
- **genspark.ai + yi.baichuan-ai.com** (`scratch_retire_misfires.py`): DOM misfires
  (wrong composer / no matching response DOM). Both need provider-specific adapters
  (custom composer + response selectors), not the generic bridge. Requirement documented
  in the seat status for future recovery.

**6. Bridge fixes (class-(a) fixable send-time/selector gaps, per Chrome Gap Doctrine):**
- **Per-host response-selector override** (`RESPONSE_SELECTORS`): Copilot's generic
  poll grabbed the "Edit in a page" toolbar (matches `[class*="message"]`) instead of
  the reply. DOM diagnosis found the clean reply node `[data-testid="ai-message-body"]`.
  SNAP_JS and POLL_JS now share a parameterized selector set with per-host overrides.
- **Per-host tab exclusion** (`TAB_EXCLUDES`): Copilot has 5 tabs — 1x `/pages/`
  (document tool: composer id `_r_ia_`, no chat DOM) + 4x `/chats/`. The bridge focused
  the FIRST matching tab, which was `/pages/`, typed into the document tool, and polled
  forever (NO_ANSWER). `_focus_tab` now skips excluded URL substrings
  (`copilot.microsoft.com` → exclude `/pages/`).
- **Grok counter false-positive:** the generic poll returned `2 / 2` (a pagination
  counter appearing after the reply in DOM order) instead of the answer. Added
  `grok.com` → `[class*="response-content-markdown"]` override.

**7. Verification (sentinel "Reply with exactly one word: Omni."):**
Direct bridge calls: claude.ai `OK 18520ms 'Omni'`; grok.com `OK 12933ms 'Omni'`;
copilot.microsoft.com `OK 15636ms 'Omni'` (after both fixes); v0.app `OK 114486ms
'Omni'` (with footer noise "Worked for 5s").
End-to-end through the shim HTTP face (`scratch_e2e_new_hosts.py`, model `<host>/auto`):
claude.ai `OK 23366ms 'Omni'`; copilot.microsoft.com `OK 'Omni'` (first attempt 500 —
transient, tab mid-reply from prior call; retry clean); v0.app `OK 29038ms 'Omni'`;
grok.com `OK 98813ms 'Omni'` after the markdown-selector fix (was `2 / 2` before).
Shim restarted twice to pick up code changes; `GET :8190/v1/models` = 32 models, lists
all 4 live hosts, correctly excludes the 3 retired ones.

**8. Deferred (video path, NOT the chat bridge):** labs.google (Flow — "PRO Daily
Bonus: 50 extra credits until August 31st") and nemovideo.com are video tools. They
need the video-capture path (`record_video_job.py` / VideoUniversalSessionClient), not
CHROME_CLIENTS. Separate work item.

**Net supply change:** +4 live chat seats (claude.ai, grok.com, copilot.microsoft.com,
v0.app) — all free, all signed-in, all verified end-to-end. 3 retired honestly with
documented recovery paths. Zero CAPTCHA bypasses, zero operator-profile touches.

**Artifacts:** `scratch_tab_coverage.py`, `scratch_probe_uncovered.py`,
`scratch_create_chrome_seats.py`, `scratch_diag_new_tabs.py`, `scratch_retire_duckai.py`,
`scratch_retire_misfires.py`, `scratch_diag_copilot.py`, `scratch_diag_copilot2.py`,
`scratch_diag_copilot_tabs.py`, `scratch_e2e_new_hosts.py`.
"""

p = pathlib.Path("MASTER_WORKLOG.md")
t = p.read_text(encoding="utf-8")
if "#1105" in t:
    print("ABORT: #1105 already present")
else:
    p.write_text(t.rstrip() + ENTRY, encoding="utf-8")
    print("appended #1105. new line count:", len((t.rstrip() + ENTRY).splitlines()))
