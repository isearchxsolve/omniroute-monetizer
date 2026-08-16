#!/usr/bin/env python3
"""Insert worklog entry #34 above the END marker."""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WL = os.path.join(ROOT, "MASTER_WORKLOG.md")
MARKER = "<!-- END OF SESSION LOG — new entries are appended above this marker -->"

ENTRY = """### [2026-08-16 10:17] #34 — Session refresh COMPLETE: all 3 dashboards AUTHENTICATED via plain-Chrome + CDP export (Playwright-interactive abandoned — too slow on this hardware)
**What:** Completed the user-driven session refresh that entry #33 identified as the Tier B blocker. All three provider sessions are now live and verified. This unblocks autonomous DOM key-generation.

**The journey (shallow → deeper, each failure diagnosed before the next attempt):**
1. **Playwright persistent-context on our empty `state/browser_profile`** → opened a blank profile with no logins (expected — it was never the user's real profile). User flagged it.
2. **Playwright `channel="chrome"` on the REAL `User Data` dir** → Chrome hard-refused: "DevTools remote debugging requires a non-default data directory" (security restriction). Timed out at 180s. Root cause identified from the error log.
3. **Robocopy of the real profile (Profile 14 "Person 1") to `d:\\omniroute-chrome-profile`** → 6 GB copy; Playwright launched it but the browser was "dead slow" (user closed it twice).
4. **Slimmed the copy 6 GB → 73.5 MB** (removed 3 unused profiles, 393 MB `File System` blob store, and a **4 GB `OptGuideOnDeviceModel`** on-device AI model + 120 MB classifier + 115 MB screen_ai). Still slow under Playwright.
5. **Hardware diagnosis:** i5-3320M (2012, 4 threads), Intel HD 4000, 15.7 GB RAM / 4.1 GB free. Conclusion: Playwright's automation flags + software rendering are brutal on this machine; the user's NORMAL Chrome is fast. **Decision: abandon Playwright for the interactive part entirely.**
6. **Plain Chrome (no automation flags) on the slim profile copy** → fast, user logged in to Anthropic + GitHub + OpenRouter manually.
7. **CDP export:** relaunched plain Chrome with `--remote-debugging-port=9222` (allowed because non-default user-data-dir — the exact restriction from step 2), connected via `connect_over_cdp`, exported `ctx.storage_state()` → `state/browser_profile/storage_state.json` (94 cookies). No cookie values printed (T11).

**Verification (ground truth, headless read-only — `scratch/verify_sessions.py`):**
- openrouter: **AUTHENTICATED** → landed on `/workspaces/default/keys`
- anthropic: **AUTHENTICATED** → landed on `platform.claude.com/settings/keys` (note: console.anthropic.com now redirects to platform.claude.com)
- github: **AUTHENTICATED** → landed on `/settings/tokens`
- Saved: `state/dom_recon/session_verify.json`

**Key learnings (recorded for future sessions):**
- Chrome refuses remote debugging on its DEFAULT User Data dir — must use a copy/non-default `--user-data-dir`.
- On low-end hardware, Playwright-launched Chrome is unusably slow; plain Chrome + CDP attach (`connect_over_cdp`) is the working pattern for interactive-then-automate flows.
- Chrome profile copies carry a 4 GB+ on-device AI model (`OptGuideOnDeviceModel`) that is pure dead weight for automation.
- Force-killed profiles get `ExitType=Crashed` → restore bubble; clear `profile.exit_type`/`exited_cleanly` in Preferences before relaunch.

**Files touched:** `scratch/interactive_login.py` (updated for real-Chrome path, now superseded), `scratch/export_sessions_cdp.py` (new — the working export tool), `scratch/verify_sessions.py` (new), `state/browser_profile/storage_state.json` (refreshed, 94 cookies), `state/dom_recon/session_verify.json` (new), `d:\\omniroute-chrome-profile\\` (new slim profile copy, 73.5 MB).
**Status:** ✅ Tier B unblocked — all 3 sessions live and verified. Next: run the DOM key-generation adapters (`provider_key_adapters.py`) autonomously against the fresh sessions, then inject verified keys into OmniRoute.
"""

content = io.open(WL, encoding="utf-8").read()
if MARKER not in content:
    print("ERROR: END marker not found")
    sys.exit(1)
if "#34 —" in content:
    print("entry #34 already present; skipping")
    sys.exit(0)

new = content.replace(MARKER, ENTRY.rstrip() + "\n\n" + MARKER)
io.open(WL, "w", encoding="utf-8", newline="\n").write(new)
print("entry #34 inserted above marker OK")
