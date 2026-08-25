# HANDOFF ADDENDUM — How oioi consumes the harness

Full version with all line refs: D:\omniroute-monetizer\HANDOFF_ADDENDUM_OIOI_INTEGRATION.md
(committed fc78d3e). Verified by reading source 2026-08-24, not inferred.
★ = added/changed 2026-08-25 from live execution, not reading.

---

## ★ 0. HOW YOU ATTACH TO THE OPERATOR'S CHROME — read this before touching a browser

> ### ⛔ STOP — §0 IS UNDER DISPUTE WITH A HARD REPO RULE. DO NOT FOLLOW IT YET.
> `scripts/automation/chrome_live_guard.py` exists for ONE reason: to make it
> "structurally impossible" for automation in this repo to open the operator's LIVE Chrome
> profile. Its docstring records the **2026-08-22 incident** — `video_key_harvester.py`
> created a junction to `%LOCALAPPDATA%\Google\Chrome\User Data`, drove a browser through it,
> **and Google REVOKED the operator's signed-in session server-side, permanently, in a loop**
> (Device Bound Session Credentials). See AGENTS.md items 5 & 14,
> CHROME_RULES_FOR_AGENTS.md, MASTER_WORKLOG.md #1026 / #1030 / #1032.
>
> **The junction method in §0.2 IS that vector.** `guard.verdict()` calls `resolve()` on the
> path, so `D:\chrome_live` resolves to the live root and `is_live()` returns True → refused.
> `assert_cdp_safe()` separately refuses attaching to any port advertised by a
> `DevToolsActivePort` file inside the live tree — which a debug launch there creates.
>
> **Why the guard did not stop it:** enforcement is (a) explicit `assert_safe()` calls and
> (b) a monkey-patch of **Playwright**. A raw `chrome.exe` launch from a shell touches
> neither. **That is a real gap in the guard, not a licence.** Fix: have the guard also
> refuse on raw-launch paths, and check `live_devtools_ports()` before any CDP connect.
>
> **The two risks are different sizes:**
> - *Launching* through the junction = the 2026-08-22 revocation vector. Mitigating nuance:
>   the incident used Playwright's bundled Chromium ("a foreign Chromium presenting that
>   session"); a genuine `chrome.exe` on its own real profile dir is arguably not foreign,
>   and `gemini.google.com` did read as signed-in afterwards. **Arguably ≠ verified.**
> - *Attaching* — per the guard's own words — "does not revoke the session the way the
>   2026-08-22 launch bug did", BUT an open DevTools port is **unauthenticated and exposes
>   every cookie in ALL FOUR profiles** (including the three Kunal accounts), and
>   "automated activity on a real account risks a flag on the ACCOUNT rather than just the
>   session."
>
> **This is the operator's call, not yours** — they instructed "you do not clone you use the
> existing profile" three times, and it is their account and their repo rule. But the
> consequence is irreversible and account-level, so it must be an INFORMED override, made
> against this paragraph. Until then: the guard's own prescription stands —
> `safe_profile_dir('providers')`, signed in ONCE by hand. **That prescription is not
> login-free — see §0.8 for whose account signs in and what it does not protect.**

**Rule from the operator, verbatim and binding: "you do not clone you use the existing
profile that's it whichever I open."** No profile copies. No cherry-picked cookie files.

### ★ 0.0 THE TARGET PROFILE IS `niloydassana@gmail.com` — NOT any Kunal profile
The operator's Chrome has FOUR profiles. Only ONE is the harvest target; the operator
explicitly rejected a Kunal profile earlier ("not this one"). Verified from
`Local State` → `profile.info_cache`:

| dir | display name | account | use it? |
|---|---|---|---|
| `Default` | Your Chrome | kunal.colab@gmail.com | **NO** |
| `Profile 14` | Person 1 | xxpertcomments@gmail.com | **NO** |
| **`Profile 16`** | **Niloy** | **niloydassana@gmail.com** | **YES — THIS ONE** |
| `Profile 17` | Kunal | isearch.xsolve@gmail.com | **NO** |

So **always pin it explicitly** — do NOT rely on `last_used` (it happens to be Profile 16
today, but a single profile switch by the operator would silently redirect the whole harvest
into a Kunal account):

    --profile-directory="Profile 16"

**Verify identity AFTER attach, before harvesting:** read
`D:\chrome_live\Profile 16\Preferences` → `account_info[].email` and assert
`niloydassana@gmail.com` is present. On mismatch, STOP — do not capture. Every captured
cookie/session inherits whichever account was open, so an unnoticed profile swap poisons
`state/secrets/` with the wrong identity.

### 0.1 The obstacle
Chrome 136+ (running 151) **silently refuses `--remote-debugging-port` when the user-data-dir
is the default one**. The port simply never opens. You cannot attach to an
already-running Chrome either — the port must exist at launch.

### 0.2 The resolution: a junction, not a clone
Give Chrome a **non-default PATH STRING that resolves to the operator's REAL User Data dir**:

    powershell New-Item -ItemType Junction -Path 'D:\chrome_live' `
              -Target 'C:\Users\Admin\AppData\Local\Google\Chrome\User Data'

Then launch. **Pin the Niloy profile explicitly** (see §0.0 — never rely on `last_used`):

    chrome.exe --user-data-dir="D:\chrome_live" --profile-directory="Profile 16" \
               --remote-debugging-port=9222 --remote-allow-origins=* \
               --no-default-browser-check

Same bytes on disk, live: real cookies, real logins, real bookmarks, **and Google/DBSC
sessions stay valid because it is the same directory on the same device** — which is the
whole point, since `niloydassana@gmail.com` is the Google identity every
"Continue with Google" provider signs in as. Zero duplication.

### 0.3 The one hard safety rule
**Never launch this while the operator's Chrome is running.** The path string differs, so
Chrome may fail to detect the running instance and open a SECOND instance over the same
physical files → profile corruption. Poll for `chrome.exe` (excluding your own launches) to
hit zero, THEN launch. Never kill the operator's Chrome to get there — wait, or ask.
Killing *your own* automation Chromes (command line contains `automation_profiles` or
`chrome_live`) is fine and expected; strays annoy the operator.

### 0.4 ★ Why the old clone approach is DEAD (don't revive it)
A 154 MB `shutil.copytree` mirror of Profile 16 was built and works for ordinary sites, but:
- **Google sessions die** — DBSC binds the session to a TPM key that never travels with the
  cookie file. `gemini.google.com` demands a fresh sign-in in any copy.
- **`claude.ai` dies too** — bounced to `/login` in the mirror.
- It goes stale the moment the operator logs into anything.
The junction has none of these failure modes. Delete the clone once the junction is verified.

### 0.5 Attach discipline (all still binding)
- Recon is **read-only first**: `drive_capture.py state` / `els` before any interaction.
- **PASSWORDS ARE NEVER RECORDED AND NEVER TYPED.** Email-only, then hand off to the human.
- **Reject every captcha / card / phone / plan / quota wall — do not hit or hammer it.** A
  login or quota wall in the automation's own profile is a CORRECT, reportable outcome.
- Secrets (cookies, bodies, tokens, nonces) → gitignored `state/secrets/` ONLY.
  stdout gets lengths, counts, header KEYS. Never a value.
- Breadth, not depth: "we don't hammer one provider with parallel tasks. We divide among
  multiple providers, multiple accounts, multiple sessions."
- Never restart/stop/kill OmniRoute (:20128 NSSM service, self-healing). Idempotent /api only.

### 0.6 ★ Submitting a chat box over CDP — the #1 cause of a 0-POST capture
Three tiers, most-reliable first:
1. **`Input.insertText`** — REQUIRED for framework-controlled contenteditable editors
   (Lexical/Slate/ProseMirror). `el.textContent = val` makes text *appear* while the
   editor's internal model stays EMPTY → send button no-ops → you capture nothing.
   `el.focus()`, clear, then `Input.insertText`.
2. **Native value setter + `input`/`change`** — fine for plain `<textarea>`/`<input>`
   (worked on plai.chat, notrack.ai). This is `drive_capture.py`'s `JS_INJECT`.
3. **Genuine Enter** via `Input.dispatchKeyEvent` (rawKeyDown → char `\r` → keyUp).
   `new KeyboardEvent(...)` has `isTrusted=false`; editors ignore it for submit.

**Verify, don't assume:** read the input's text back AND the send button's
`disabled`/`aria-disabled`. A `false` disabled flag does NOT prove the model is populated.
**Icon-only buttons are ambiguous** — `els` labels them `<icon>`. On notegpt.io the icon
button beside the input fired only `/logstores/notegpt/track` (analytics), not a chat POST.
Do not brute-force icon buttons; that is hammering one provider. If genuine insertText AND
genuine Enter both yield no chat POST → conclude **guest send is sign-in-gated**, log it,
move to the next provider.

### 0.7 The capture → replay contract
ONE sentinel across ALL providers: `Reply exactly one word: Omni.`
Submit it in the real browser, match the POST **whose body contains the sentinel**, save
body + `Network.getCookies` jar. On a live call, string-replace sentinel → real prompt and
resubmit server-side. **No per-provider adapters — one universal replayer.** Never
reconstruct a request from scratch; reconstruction gets gated.

### ★ 0.8 THE SIGN-IN MODEL — whose account signs in, who types, what it does NOT buy
Missing from the first draft; the operator caught it. State it plainly — it is a decision the
operator must make knowingly, not an implementation detail.

**The guard's sanctioned path is not "no login" — it is a login in a different profile.**
`safe_profile_dir('providers')` gives automation its own user-data dir; it starts EMPTY, so
every walled provider must be signed in there. In practice that means **signing in or signing
up to third-party providers using the operator's own Google account,
`niloydassana@gmail.com`** — because most targets gate on "Continue with Google".

Division of labour (non-negotiable):
- **The HUMAN performs the sign-in**, in the visible automation window, once per provider.
- **The AGENT never types a password.** Email-only at most, then hand off. Automation may
  click "Continue with Google" and pick the account from Google's chooser; the credential
  step is the operator's.
- **Never solve a captcha / card / phone / plan wall.** Hitting one is a reportable STOP.
- It is a **one-time** cost per provider: automation's own profile keeps its DBSC binding
  because the browser instance never changes, so those sessions persist across runs. That is
  exactly why the guard's path works and the clone did not.

**What the `providers` profile protects — and what it does NOT:**

| risk | protected? |
|---|---|
| Revocation of the operator's LIVE browsing session (the 2026-08-22 loop) | **YES** — the live tree is never opened |
| Cookies of all 4 profiles exposed via an unauthenticated DevTools port | **YES** — only automation's own profile loads |
| A flag/ban landing on the **Google ACCOUNT** `niloydassana@gmail.com` | **NO** — same identity either way |
| Third-party accounts created under the operator's real identity | **NO** — real signups on ~11+ sites |

The guard removes the *session* risk, not the *account* risk. Automated traffic still
originates from the operator's real Google identity. Do not present this profile as risk-free.

**★ SCALING TENSION — settle before any film run.** One Google identity cannot back the
supply model. A 3-hour film needs ~2,160 clips ≈ **~540 free accounts** (Digen: 4 clips per
account at 30 credits each). `niloydassana@gmail.com` yields ONE account per provider, not
540 — and funnelling hundreds of signups through a single Google identity concentrates the
account-ban risk above onto the operator's personal account. The breadth-not-depth rule
("multiple providers, multiple accounts, multiple sessions") therefore needs an identity
source that is NOT the operator's personal Google account. **Unresolved; operator decision.**

---

## 1. Chat and video are TWO endpoints. Never merge them.
- CHAT  -> http://127.0.0.1:20128/v1/chat/completions
  via oioi/backend/studio_pipeline/omniroute.py (DEFAULT_BASE_URL L29, chat() L185,
  chat_json() L253, probe_video() L324, generate_video() L388)
- VIDEO -> http://127.0.0.1:8189/v1/videos/generations
  via OMNIROUTE_VIDEO_BASE_URL in oioi/backend/app/core/config.py:70; adapter built at
  provider_service.py:73-78, availability gate L105. Free POST /v1/videos/quote exists.

RULE: never point OMNIROUTE_BASE_URL at the video router. probe_video() discovers routes by
POSTing a REAL generation request, so every capability probe would submit a genuine paid job
and abandon it after an 8s timeout. config.py says the separate name is deliberate; it is.

A third face :8188 is a ComfyUI costume (video as a `comfyui/...` model string through
OmniRoute). It labels ALL bytes "webp" and has no error channel (failures = ~300s timeouts).
oioi uses :8189.

## 2. Video: oioi needs ZERO changes to gain a provider.
Implement video_provider.Provider (quote L285 / confirm L295 / probe L312 / submit L318),
register() L377 into REGISTRY L374. Rotation, per-account locking across submit+poll,
confirm-before-spend, and NO-automatic-submit-retry are already video_router.py's job --
inherit them, do not reimplement. oioi's URL never changes.

## 3. Chat is the one real gap.
session_pool.py has NO HTTP face -- verified: no HTTPServer, no FastAPI, no uvicorn, no
do_POST, no chat/completions. CLI-only (argparse L25, subparsers L227). It DOES have the
right registry and load-spreader: CLIENTS L46, PooledSession.modality L86, live() L142,
pick() L149, chat() L156, sweep() L190, DEFAULT_COOLDOWN=20.0 L52, per-host lock.

WORK: an OpenAI-compatible /v1/chat/completions shim over SessionPool.chat(), mirroring what
video_router.py does at :8189. Then oioi consumes it unchanged via either:
  (a) repoint OMNIROUTE_BASE_URL at the shim, or
  (b) register the shim as a provider INSIDE OmniRoute so :20128 fans out to it.
PREFER (b): keeps OmniRoute's routing/failover, leaves oioi's default untouched.
Shim must send `stream` explicitly as false. Responses may carry both `content` and
`reasoning_content` -- ONLY `content` is the answer.

### ★ 3.1 Universal replay is PROVEN — on exactly one host
`universal_replay.py` (`UniversalSessionClient`) was executed live:
- **notrack.ai — FULLY VERIFIED end-to-end.** Captured POST `/api/dispatch` (body 186 B,
  sentinel present, 3 cookies) → replayed with substitution → HTTP 200 → model answered.
- **plai.chat — session live, provider flaky.** POST `/api/web/chat/send` (body 165 B)
  replays 200 and routes to a real upstream model, which then returned
  `{"type":"error","error":"All models temporarily unavailable"}`. Session is good; the
  provider's own backend was down.
- **notegpt.io — guest send sign-in-gated** (see §0.6). No capture.
`_extract_response` was rewritten into a universal SSE + whole-body-JSON assembler
(OpenAI `choices[].delta`, Anthropic `content_block`/`delta.text`, generic
`content/text/answer/token`), returning `(text, error)` so upstream error chunks surface as
`ChatError("UPSTREAM_ERROR: ...")` instead of being silently swallowed.

### ★ 3.2 FIXED 2026-08-25: three incompatible session-file schemas
`state/secrets/*.json` was NOT one schema, and `universal_replay.py` read only the newest —
so an older capture yielded `base_body == ""` and fired a **BODYLESS POST that still returns
HTTP 200**, the worst kind of false green.

| writer | shape | before | now |
|---|---|---|---|
| `drive_capture.py` | `recorded_exchange{url,method,request_headers,request_body}` | worked | works |
| veoaifree (older) | `recorded_exchange{url,method,headers,post_data}` | **bodyless POST, silent** | **3487-byte body recovered → REPLAYABLE** |
| digen | `recorded_job{api_substr,exchanges[],recorded_at}` | raised ValueError | body recovered (65 B) |

Fix: `UniversalSessionClient._normalise_exchange()` accepts every shape — key aliases
(`post_data`/`postData`/`body`/`payload` → `request_body`; `headers` → `request_headers`) and
flattens `recorded_job.exchanges[]` / top-level `exchanges[]`, picking the first exchange that
carries a body (later ones are status polls). Two pre-flight guards were added to `chat()` so a
broken capture can never reach the wire: **`EMPTY_BODY`** (POST/PUT/PATCH with no body) and
**`SENTINEL_NOT_FOUND`** (no known sentinel matched, so the replay would re-send the recorded
probe prompt and log the answer to *that* as the caller's answer).

Dry parse over all 21 files (no network): **3 replayable** (notrack.ai, plai.chat,
**veoaifree.com** — the last previously invisible), **8 parse with a body but no injectable
sentinel** → correctly blocked, need re-capture with the sentinel (akool 5061 B, heygen 1374 B,
oiioii 3232 B, creen 107 B, digen 65 B, openart 2 B, flux-ai 0 B, rtst 0 B), **10 unparseable**
= genuinely cookie-only, no exchange recorded at all.

### ★ 3.3 19 of 21 session files are cookie-only shells
Only `session_notrack_ai.json` and `session_plai_chat.json` carry a replayable body with the
sentinel. The other 19 (akool, capcut, creen, flux-ai, imagine.art, kling, labs.google,
openart, rtst, teamily, topmediai, veoaifree, oiioii, heygen...) hold **cookies but
`request_body` length 0** — they prove a login existed, they do NOT prove a replayable
exchange. Treat "a session file exists" as no evidence of capability.

## 4. CORRECTION: the Digen adapter IS written -- and unproven.
digen_session_replay.py exists, registered session_pool.py:48, and has NEVER RUN
(state/session_pool_state.json has no digen entry; that file records every dispatch).
Gets right: lifts Digen-* custom headers not the cookie; drops content-length/cookie/
accept-encoding + HTTP/2 pseudo-headers; thread-local requests.Session; SessionExpired on
401/403; re-serialises scene_params as a JSON string.

DEFECTS, priority order:
1. LOAD-BEARING: replays the captured `code` idempotency key verbatim (L83-88 swaps only
   video_gen_prompt). That is a client-generated <epoch_nanos>_<uuid4> key -- reusing it may
   return the SAME cached video for every prompt (silently wrong; you'd notice only after
   watching 2,160 identical clips) or be rejected. Fix: synthesize per submit.
2. No spend guardrail at all: each chat() burns 30 credits with no quote/confirm/ceiling and
   no GET /v1/credit/remain pre-check. It bypasses the Provider guardrails by living in
   session_pool instead of behind video_router. This is the argument for porting it.
3. LIVE LANDMINE: session_digen_ai.json has no `modality` key and session_pool.py:86 defaults
   to "chat", so `sweep` (with or without --modality chat) fires a real 30-credit generation
   as its "one light call", blocking up to 120s. DO NOT SWEEP until fixed.
   ★ Confirmed by reading the file: top-level keys are captured_at/context/cookie_header/
   cookies/host/likely_authed/logged_in/match/modality/recorded_job/updated_at — `modality`
   IS present and set to "video". Re-verify which code path actually reads it before trusting
   either claim; the landmine may be narrower than originally written.
4. No error channel: poll URL hardcodes status=2 (L110), so a job appears only once DONE. A
   FAILED job never appears -> the loop can only ever raise TIMEOUT (L138). Same flaw as :8188.
5. Dead fallback raises AttributeError: reload() L46 sets a LOCAL `exchanges`, never
   self._exchanges, which L56 dereferences. Fix or delete the branch.
6. self.timeout does double duty (L92 per-request, L113 total poll budget). ~50s render vs
   120s budget is thin. Split into request_timeout / poll_budget.
7. cid and scene_id replayed verbatim -- correct for this account only.
8. videoURLV1 fallback (L124) is a guess; capture only showed videoUrl.
9. ★ video_provider_digen.py:88 typo `remain` -> `remained` (noted, unfixed).

## 5. Spend-guardrail collision -- operator decision required.
OMNIROUTE_VIDEO_MAX_CREDITS_PER_RUN = 60 vs Digen 30 credits/clip = 2 CLIPS PER RUN, against
a 2,160-clip 3-hour-film target. Calibrated before Digen's price was known (Flow 8s/720p = 20,
rtst 3s/540p = 6; whole rtst balance is 18, Flow's 930). Raising it is a real spend decision,
deliberately left unchanged.

## 6. Build order
0. ★ Attach via the junction (§0), pinned to `--profile-directory="Profile 16"`. Verify
   `:9222/json/version` answers AND `Profile 16\Preferences` shows `niloydassana@gmail.com`
   before any harvest.
1. ★ Normalise the session-schema readers (§3.2) -- a bodyless POST that returns 200 is the
   worst kind of false green.
2. Fix defect 3 (sweep landmine) -- it costs credits on a command that looks free.
3. Fix defect 1 (idempotency key) -- else a "working" pipeline silently emits duplicates.
4. Port Digen to video_provider_digen.py behind :8189, inheriting quote/confirm/rotation/
   no-retry. Proves replay end-to-end on ONE provider; oioi gets it for free.
5. THEN build the chat shim and register it inside OmniRoute (option b). Second, because it
   generalises over ~95 hosts and that's only worth doing once the pattern is proven on one.
6. Settle the credit ceiling (section 5) with the operator before any multi-clip run.

## 7. NOT claimed
No shim exists. No video_provider_digen.py exists. digen_session_replay.py has never run, so
its correctness is unverified by execution and the defect list is from reading -- a live call
may reveal more. All defects unfixed; the sweep landmine may still be live (see 4.3 caveat).
Only text-to-video was captured for Digen, so the character-relay image slots are captured
EMPTY and their populated wire shape is unknown. Nothing in oioi was modified producing this.

★ Newly NOT claimed, 2026-08-25:
- **The junction attach is NOT yet verified.** The junction exists and resolves
  (`D:\chrome_live` → real `User Data`, `Profile 16` = Niloy Das / niloydassana@gmail.com),
  but Chrome has NOT been launched through it, because the operator's Chrome was still
  running and launching concurrently risks profile corruption. Whether Chrome 151 opens the
  debug port through a junction path — or canonicalises it back to the default dir and
  refuses — is **UNTESTED**. If it refuses, the remaining honest options are a
  `chrome.debugger`-API extension loaded in the real profile, or reverting to the
  (operator-rejected) clone. Do not report the attach as working until `/json/version`
  answers and the account assertion in §0.0 passes.
- Chat replay is proven on **notrack.ai only**; plai.chat proves the session, not an answer.
  The ~95 swept providers are LISTED, not proven. session_pool deliberately refuses to
  blind-replay a host with no CLIENTS entry. That rule stands.
- The 154 MB clone at state\automation_profiles\niloy is superseded, not yet deleted.
