# TECHNOLOGY TRANSFER — OmniRoute Monetizer

**Purpose of this file.** A new agent (or engineer) reads this and understands the *technology*, not
just the file list: what each mechanism does, how it does it, why it is built that way, and which
tricks are load-bearing. Every non-obvious behaviour here was **measured**, not assumed. Where a date
appears, that is the day the behaviour was observed on this machine.

**Status convention.** Sections marked `[VERIFIED]` describe code that has been read and exercised in
this session or a prior one, with the evidence stated. Sections marked `[INVENTORY]` name the file and
its role accurately but have not been line-by-line re-verified. Never present `[INVENTORY]` detail as
proven. This file is appended to as work proceeds.

**Scale.** `scripts/automation/` holds **192 Python files, 42,745 lines**. Most are one-shot pilots
from earlier exploration. The *live technology* is ~15 files, listed in §11.

---

## 1. What this system is

The business model determines the architecture, so start there.

Monetization: an ngrok tunnel exposes a film-making app. A customer pays **$100 once** for a unique
URL granting **lifetime unlimited 3-hour films**. The generation engines produce **5-second clips**;
oioi stitches them into the finished film.

Three consequences fall straight out of that, and they explain nearly every design decision:

1. **A 3-hour film is 2,160 clips.** At the observed rate of 30 credits per 5-second clip and free
   accounts holding ~120 credits, that is 4 clips per account — roughly **540 free accounts per
   film**. Supply, not cleverness, is the binding constraint.
2. **Breadth beats depth.** Because supply is the constraint, load is spread across *many providers,
   many accounts, many sessions*. Hammering one provider with parallel work is forbidden — it burns
   the one thing that is scarce and trips rate limits that cost more than they save.
3. **Lifetime promises on borrowed supply is the standing business risk.** A session harvested today
   is not guaranteed tomorrow. Every layer therefore has to degrade honestly rather than pretend.

The product surfaces that consume the technology, and they are **never merged**:

| Port | Service | Consumes |
|------|---------|----------|
| `:20128` | OmniRoute (chat) | paid/OAuth provider connections |
| `:8189` | Video router | video seats over CDP |
| `:20130` | Chat pool server (superset gateway) | harvested browser chat sessions + forwards to `:20128` |
| `:8190` | **Session pool shim — the designated consumer endpoint** | every grabbed session (chat + video) via `session_pool.py` |

**`:8190` is the one the film kit (OiiOii/Codex) actually calls.** Base URL
`http://127.0.0.1:8190/v1` (use `127.0.0.1`, never `localhost` — the system proxy intercepts
loopback). OpenAI-compatible. Chat: `POST /v1/chat/completions` with `{"model": "session-pool/auto"}`.
Video: `{"model": "video/auto"}` (or pin a host with `"<host>/auto"` / `"video/<host>/auto"`).
Discover everything via `GET /v1/models`. The async video contract (`POST /v1/video/jobs` →
`GET /v1/video/jobs/{id}` → `?job_key=` reconciliation → `DELETE`) is served here too — see §25.

The older `:20130` chat pool server speaks **`POST /v1/messages`** (Anthropic-shaped) — *not*
`/v1/chat/completions`. This cost real time: an entire earlier round of route certification probed
the wrong endpoint, so its results were meaningless. A route can time out on
`/v1/chat/completions` and answer in 10s on `/v1/messages`. The `:8190` shim is OpenAI-shaped,
so do not conflate the two faces.

---

## 2. The five laws (learned the expensive way)

These are the invariants that a new agent will otherwise re-learn by breaking something.

### Law 1 — Capture is not supply.
A capture proves the browser *made* a request we could observe. It does not prove that request can be
**re-sent**. Roughly a third of captures fail on replay for structural reasons (§6).

### Law 2 — A naive extractor manufactures false supply.
If you return a raw response body as "the model's reply", then any HTML login wall, error page, or
marketing landing page scores as working supply the moment the caller's expected keyword appears
anywhere in the markup. This is exactly how this repo's registry came to claim **88 working routes
when 15 answered**. Never trust `test_status`; probe.

### Law 3 — The verification answer must be COMPUTED, never echoable.
With the prompt `"Reply exactly one word: Verified"`:
- `aymo.ai` replied `"Confirmed."` — a *live* provider scored as dead.
- `chat.mistral.ai`'s server generated a chat **title** containing the asked word — a bootstrap
  response with no answer in it scored as **alive**.

Both failure directions vanish with arithmetic: prompt `"Reply with only the number: 41 + 17"`,
expect `58`. `58` appears in neither an echo nor a generated title. This single change fixed the
scoring of the whole fleet.

### Law 4 — Never reconstruct a request; replay the recorded one.
A hand-built request gets gated (bot detection, missing headers, missing signed fields). The genuine
recorded exchange is replayed byte-for-byte with **one** string substitution. There are **no
per-provider request adapters** — one sentinel prompt, all providers.
*Response*-shape handlers (e.g. unwrapping Google's envelope) are not adapters and are legitimate.

> **⚠️ OPERATOR OVERRIDE — 2026-08-28 (worklog #1130).** For the explicit purpose of achieving
> **full Chrome independence**, the operator has authorized **hand-rolling send-time fields in
> Python** where the situation demands: recomputing PoW (e.g. DeepSeek `x-ds-pow-response`),
> signatures (e.g. chatglm `X-Sign`/`X-Nonce`/`X-Timestamp`), nonces, and multi-step / websocket
> protocols. Law 4's "never reconstruct" and Doctrine 3a's "never hand-replay" are **LIFTED** for
> this purpose. **Laws 1, 2, 3, 5 remain fully in force:** a hand-rolled seat is graduated only
> after it passes Law-3 *computed* verification (arithmetic probe → `58`, never echoable), and
> walls (captcha / card / quota) are still reported, never solved. Chrome (V8) stays the
> capture / onboard / re-auth instrument; the goal is that **runtime serving no longer requires it**.
> The V8 cost that drove this decision is lock-serialization (`_DRIVER_LOCK`, one browser one
> typist) + UI latency + resident RAM — not per-execution forking (Selenium/CDP merely attach to
> long-lived seat Chromes).

### Law 5 — Report the wall, never solve it.
Card / captcha / phone / plan / quota walls are a **correct, reportable outcome**. Stop; do not
hammer, solve, or pay. Passwords are never recorded and never typed. Secrets never reach stdout —
metadata and shapes only; secrets live in gitignored `state/secrets/`.

---

## 3. Layer 1 — Session capture over CDP `[VERIFIED]`

**Goal:** obtain a genuine browser POST that carries a known sentinel prompt, plus the cookie jar, so
it can be replayed server-side later.

**File:** `scripts/automation/capture_sessions_cdp.py` (779 lines)
**Output:** `state/secrets/session_<slug>.json`, reports in `state/capture_report_922[2-5].json`

### 3.1 The recorded artifact
```
{ "host": ..., "cookie_header": "...",
  "recorded_exchange": { "url", "method", "request_headers", "request_body" } }
```
`request_body` must contain the sentinel `Reply exactly one word: Omni.` — that literal is the hook
the replay layer substitutes into.

### 3.2 Trick: three capture generations, three schemas
Three capture generations wrote three different key names into `state/secrets/`. Reading only the
newest meant an older file produced `base_body == ""`, i.e. a **bodyless POST that still returns HTTP
200** — a silent false green. The replay client therefore normalises on read
(`_normalise_exchange`, accepting `url|request_url`, `request_body|post_data|postData|body|payload`,
`request_headers|headers|request_header`) and raises `EMPTY_BODY` rather than firing a bodyless POST.

### 3.3 Trick: submitting a chat box over CDP
Modern chat UIs are rich editors (contenteditable / ProseMirror / Lexical), not `<textarea>`.
- Setting `textContent` **fails** — the framework's model never sees it, so the send button stays
  disabled.
- What works: **`Input.insertText`** followed by a **genuine `Enter`** key event
  (`Input.dispatchKeyEvent` with matching `keyDown`/`keyUp`, correct `key`/`code`/`windowsVirtualKeyCode`).
- Some providers still refuse. Knowing when to stop is part of the technique — a provider that will
  not submit is a reportable outcome, not a target to escalate against.

### 3.4 Trick: reading a cookie jar while Chrome is running
The profile's `Cookies` SQLite file is held by Chrome. **A locked `Cookies` file means Chrome is
RUNNING — it does not mean re-signup is needed.** The only reader that works is raw CDP
**`Storage.getCookies` with `suppress_origin`**. Do not conclude a seat is dead from a locked jar.

### 3.5 Trick: Chrome profile cloning does not revive Google
Cloning a profile for CDP revives *site* logins but **not Google** — Device Bound Session Credentials
(DBSC) tie the session to the original device/profile. Google also **refuses sign-in on a
CDP-enabled Chrome**. `drive_capture.py` is the working harvester for that path.

### 3.6 Hard prohibition
**Never junction, mount, or drive the operator's live Chrome profile.** Doing so permanently revoked
their Google session on **2026-08-22**. `chrome_live_guard.py` exists to enforce this (§8.3).

---

## 4. Layer 2 — Universal replay `[VERIFIED]`

**File:** `scripts/automation/universal_replay.py` (607 lines) — the engine. Class
`UniversalSessionClient`; entry point `chat(messages)`; raises `SessionExpired` / `ChatError`.

Construct it with the **path**, not the parsed dict: only a path lets it write a rotated cookie back
(§4.5). Handing it a dict silently throws rotation away.

### 4.1 Header preparation (`__init__`)
1. **Drop HTTP/2 pseudo-headers** (`:authority`, `:path`) — they crash `requests`.
2. **Strip `content-length` and `content-md5`.** The recorded length describes the *recorded* body;
   after substitution it announces the wrong size, producing a truncated read or a 400 at the
   provider. `requests` computes the correct one.
3. `raw["cookie_header"]` overrides any cookie in `request_headers` (both cases set, since providers
   differ on header-name casing).
4. **Synthesize `origin`** if absent — fixes HuggingFace CSRF rejection.

### 4.2 Prompt injection (`_inject_prompt`) — the highest-impact fix in the system
The prompt must be escaped for **the body's encoding**, not just inserted. Unescaped newlines caused:
- `chat.qwen.ai` → `RequestValidationError: Field '542': JSON decode error`
- `huggingface.co` → HTTP 500

Real agentic prompts *always* contain newlines and quotes, so this was a total blocker.

```python
stripped = body.lstrip()
is_json = stripped[:1] in ("{", "[") or '{"' in body   # note the second clause
esc = json.dumps(new_prompt)[1:-1]
repl = esc if is_json else new_prompt
```
**The `'{"' in body` clause is load-bearing.** HuggingFace posts `multipart/form-data` whose body
starts with `-`, so a whole-body JSON test misses it — but its *parts* carry JSON. Test for JSON
appearing *anywhere*.

Substitution also tries URL-encoded forms (`quote_plus`, then `quote`) for form-encoded bodies,
escaping the replacement to match the encoding it found.

**Guard:** if substitution changed nothing and the prompt is absent, raise `SENTINEL_NOT_FOUND` — a
silent no-op would re-send the captured probe prompt and log the model's answer to *that* as if it
answered the caller.

### 4.3 Response extraction (`_extract_response`) — the false-supply firewall
Ordered stages. Every stage exists because a specific provider broke the previous one.

1. **XSSI strip** — `)]}'`, `while(1);`, `for(;;);`.
2. **Google refusal check** (`_google_error`) — Google signals refusals *in the same envelope* as a
   success, with a null payload plus a `BardErrorInfo` code. Detected via
   `re.search(r"BardErrorInfo\"\s*,\s*\[\s*(\d+)", text)` → `GOOGLE_REFUSED`. Without this, a
   refusal reads as an answer.
3. **Google envelope walk** (`_google_envelope`) — see §4.4.
4. **JSON fragment sweep** —
   `re.findall(r'"(?:content|text|answer|delta)"\s*:\s*"((?:[^"\\]|\\.)*)"', text)`, then echo-filter,
   then accumulate.
5. **Refusal guards — the part that stops false supply.** Return an *error*, never an answer, when:
   - `_looks_like_html(text)` → `UNPARSEABLE_HTML` (this is what stopped `veoaifree.com`
     "answering" `<!doctype html>` and `you.com` "answering"
     `width=device-width, initial-scale=1`)
   - body contains `data: {` or starts with `event:` → `UNPARSEABLE_STREAM`
   - `len(text) > 4000` → `UNPARSEABLE`
6. Only a short, unrecognised body falls through as text (`text[:2000]`).

**Echo filtering** (`_is_echo`) must be **length-bounded**, and getting this wrong broke it twice:
- Dropping any fragment that is a *substring of* the prompt destroys streamed answers — `"Ver"` is a
  substring of `"…Verified"`.
- Dropping any fragment *containing* the prompt destroys short answers — prompt `"hi"` is inside
  reply `"Hi!"`, which emptied extraction entirely and dumped 804 bytes of raw SSE.

Correct rule: **exact match, or containment only when the prompt is ≥ 24 chars**
(`_ECHO_MIN_PROMPT = 24`).

**Stream accumulation** (`_accumulate`) — streams split into two families and conflating them
corrupts answers:
- **delta**: each event carries the increment → concatenate.
- **cumulative**: each event carries the whole answer so far (Perplexity) → concatenating yields
  `5858` for an answer of `58`.

```python
if acc and p.startswith(acc) and len(p) > len(acc):  acc = p        # supersede
elif acc and p == acc and len(acc) >= 2:             continue       # drop repeat
else:                                                acc += p      # append
```
Applied in **both** `scan()` and stage 4 — fixing only one leaves the bug reachable.

### 4.4 The Google batchexecute envelope
Structure: `)]}'` prefix, then alternating **length lines** and JSON payloads, each
`[["wrb.fr",null,"<escaped json>"]]` — whose third element is **JSON inside a JSON string**.

This is unreachable by `json.loads` on the body and unreachable by regex (the escaping defeats it).
It must be walked with **`json.JSONDecoder().raw_decode`** in a loop. Gemini's answer sits at
`doc[4][0]`, searched from the **last** document because streaming increments repeat earlier ones.
Reusable across Gemini / Flow / AI Studio — which matters for the video task.

Diagnostic: `scripts/automation/inspect_reply_shape.py` reads `state/replay_raw/*.txt` and prints the
**path** to every short string, so an answer's position is *pinned* rather than guessed. Also handles
Mistral's tRPC-style numbered chunks (`15:{"json":{...}}`), which no `data:`-based parser sees.

### 4.5 Cookie rotation write-back `[VERIFIED 2026-08-26]`
**The actual expiry path for these sessions, and it was unhandled.** Providers rotate session cookies
as they are used: the reply carries `Set-Cookie` and a real browser stores it. The replay layer was
re-sending the jar recorded at capture time forever, because the jar on disk is a **snapshot** and
nothing wrote back to it. So sessions decayed on the provider's own schedule regardless of any
keepalive service.

`_absorb_cookies(resp)` merges `Set-Cookie` from the response **and its redirect history** into the
live header, honours deletions (empty value ⇒ remove the key), preserves cookie order, and calls
`_persist_cookies` to write it back to the source file atomically (tmp + `replace` — a half-written
secrets file takes a live provider off the pool). Persisted to `cookie_header` because `__init__`
gives that key precedence; the embedded `request_headers` copy is updated too so no other reader sees
a stale jar. Stamped with `cookieRotatedAt`. Never logs the value.

**Absorbed only when `r.ok`.** A 401/403 body can carry a logged-*out* jar, and storing that converts
a recoverable session into a dead one.

**Proof the gap was real (2026-08-26 07:49Z).** A single pool call to `aymo.ai` produced
`"cookieRotatedAt": "2026-08-26T07:49:01Z"` in `state/secrets/session_aymo_ai.json` — i.e. aymo
rotates its session cookie **on every use**. Before this fix that session was silently decaying with
each call and would eventually have died with no diagnosable cause. No stray `.tmp` files, so the
atomic write is clean.

**Consequence for the whole design:** cookie freshness is maintained *by serving traffic*, not by any
external keepalive. The pool is self-sustaining while it is used; a session that goes unused is the
one at risk. That inverts the intuition — idle sessions are the liability, busy ones look after
themselves.

---

## 5. Layer 3 — The chat pool server `[VERIFIED]`

**File:** `scripts/automation/chat_pool_server.py` (502 lines). Port **20130**. This is what turns
captured sessions into a route oioi can consume.

**Endpoints:** `POST /v1/messages` (Anthropic — what oioi actually calls),
`POST /v1/chat/completions` (OpenAI), `GET /v1/models`, `GET /health`.

**Constants and what each is protecting:**
| Constant | Value | Protects |
|---|---|---|
| `MIN_INTERVAL_S` | 3.0 | per-provider spacing (breadth-not-depth, in code) |
| `COOLDOWN_FAIL_S` | 90.0 | ordinary failure back-off |
| `COOLDOWN_WALL_S` | 3600.0 | wall/auth — a stood-down provider is **never** retried in-window |
| `WAIT_FOR_SLOT_S` | 8.0 | bounded wait for a free provider |

**`Provider`** — per-session state (`available()` / `ready()` / `stand_down()`), and **one
`threading.Lock` per session** so a given session never has two in-flight calls.

**`Pool`** — reads the `REPLAY_OK` gate from `state/replay_check.json`, so *only verified-replayable
sessions are served*. `--all` / `--allow` override, and `/health` reports that it was overridden —
an override must never look like a clean bill of health.

**Dispatch** — LRU `acquire()` spreads load; each provider is tried **at most once per request**;
`pool/auto` and `pool/any` mean "unpinned"; a pinned provider still gets the `MIN_INTERVAL` brake.
Failures are classified by `classify_failure()`; wall/auth ⇒ 3600s stand-down. Returns **503, not
500**, when the pool is intact but busy — the distinction is what lets a caller retry sanely.

**Message shaping** — `as_single_prompt()` serialises multi-turn history with role labels;
`to_messages()` folds the system prompt into the front.

### 5.1 The Windows duplicate-bind hazard — read this before debugging anything on a port
`ThreadingHTTPServer` sets `allow_reuse_address = 1`. On Windows, `SO_REUSEADDR` **permits a
duplicate bind**: a second server binds `:20130` with no error, both sit `LISTENING`, and a **stale
process silently serves old code** — so every fix appears not to work. Cost real debugging time.

```python
class PoolServer(ThreadingHTTPServer):
    allow_reuse_address = False      # so a duplicate bind fails LOUDLY
    daemon_threads = True
```

Also: **`pkill -f` does not kill python processes in this Git Bash environment.** Use:
```bash
netstat -ano | grep ':20130'
```
then `taskkill //F //PID <pid>`.

### 5.2 Verified behaviour (2026-08-26)
- A multi-line prompt containing a newline, `"quotes"` and `path\slash` → answered `58` cleanly.
- Four unpinned calls rotated across `aymo-ai`, `api-cohere-com`, `huggingface-co`, `chat-qwen-ai` —
  all `58`, no provider repeated.

---

## 6. Failure taxonomy — why captures fail on replay `[VERIFIED]`

`scripts/automation/replay_check.py` scores every capture with **one request each, serial, no
retries**, direct to the provider (so it costs nothing on any paid route). Verdict vocabulary:

| Verdict | Meaning |
|---|---|
| `REPLAY_OK` | answered, and the answer contains the **computed** expectation ⇒ real supply |
| `SINGLE_USE` | rejected naming a nonce/pow/token/id ⇒ needs a live browser per call |
| `AUTH` | cookie no longer accepted |
| `WALL` | credits/quota/captcha ⇒ **STOP**, never hammered |
| `RATE` | 429 |
| `HTML_PAGE` | served a web page, not an API response ⇒ **not supply** |
| `UNPARSEABLE` | 200 but no recognised response shape ⇒ not scored as an answer |
| `NO_ANSWER` | 200 but the computed expectation is absent |
| `BAD_FILE` | no sentinel in the recorded body ⇒ not replayable at all |

**Ordering trick:** `BAD_FILE` / `HTML_PAGE` / `UNPARSEABLE` are checked **first**, because
`SENTINEL_NOT_FOUND` contains the substring `"not found"`, which would otherwise be misread as a
provider rejecting a stale id.

**Structural defeats of pure replay** (these need multi-step replay with id threading, ~2h work).
**Status as of 2026-08-27:** most were resolved by moving replay *inside* the browser (§18) — the
defeat was never the site, it was firing recorded bytes from outside the runtime that mints the
send-time fields. Resolutions in brackets:
- **DeepSeek** — binds a proof-of-work token (`INVALID_POW_RESPONSE`). [**RESOLVED → REPLAY_OK**
  via **adapter invocation** §19 — the site's own app computed the PoW for free; zero PoW
  reverse-engineering]
- **Felo** — binds a `message_id`. [**RESOLVED → REPLAY_OK** via 2-leg flow §18.5]
- **Claude / ChatHub** — HTTP **409**: one-shot conversation/parent ids. [chathub since confirmed
  a genuine class-(b) quota death, operator-verified in Chrome §18.6]
- **Mistral** — the POST returns only a *bootstrap*; the answer arrives on a second stream.
  [**RESOLVED → REPLAY_OK** via send-time reconstruction §18.3]
- **Monica** — re-answers from **server-side** conversation state, so it replies to the *captured*
  prompt even when both sentinel copies were substituted. This is the subtlest false-positive in the
  set: substitution succeeded and the reply still was not ours.

### 6.1 Honest supply, last full sweep (2026-08-26)
**5 replayable:** `api.cohere.com`, `aymo.ai`, `huggingface.co`, `www.perplexity.ai`, `you.com`.

`chat.qwen.ai` is **intermittent**, not dead — it answered `58` through the pool minutes after
scoring `WALL` in the sweep. State-sensitive, worth retrying on its own schedule.
`gemini.google.com` replays but is currently refusing (`BardErrorInfo 1076`); extraction is pinned,
the *session* needs re-capture. Per the no-hammering rule, probing stopped at the refusal.

---

## 7. Layer 4 — OmniRoute and the OAuth keepalive `[VERIFIED 2026-08-26]`

OmniRoute (`:20128`) is the **paid/OAuth** side, and is a separate world from the harvested browser
sessions. Confusing the two is easy and consequential.

**`scripts/automation/oauth_keepalive.py`** — refreshes OmniRoute OAuth connections via
`POST /api/providers/{id}/refresh`.

**The load-bearing insight, recorded in its own docstring:** *sending inference requests does NOT
refresh an OAuth session.* Server-side timers dictate expiry. The native refresh endpoint is the only
correct mechanism. Copilot tokens live ~30 min, amazon-q ~1 h, hence a 15-minute default interval.
It talks through the management API abstraction and **never touches `storage.sqlite`**.

Targets are selected as `authType == "oauth" and isActive` → antigravity, cline, amazon-q, grok-cli,
xai-oauth, codex, kiro, kimi-coding, agy, clinepass, github, kilocode.

### 7.1 It does NOT keep harvested chat cookies alive — three independent reasons
Asked directly whether `OmniRouteOAuthKeepAlive` keeps the captured cookies alive for uninterrupted
service. **It does not:**

1. **Wrong target.** It iterates *OmniRoute connections*. The 24 harvested sessions
   (aymo / cohere / huggingface / perplexity / you.com) are cookie jars with **no OmniRoute `id`**.
   Zero overlap; they are never touched.
2. **The service is STOPPED, and its NSSM config is broken.**
   `AppDirectory = d:\omniroute-monetizer\.venv\Scripts` with a **relative**
   `AppParameters = scripts\automation\oauth_keepalive.py`, which resolves to
   `.venv\Scripts\scripts\automation\oauth_keepalive.py` — a path that does not exist. It cannot run
   even on `AUTO_START`. (Passes *have* run — `state/keepalive_result.json` is stamped
   2026-08-25 18:20 — but from something else, not this service.)
3. **Structural.** Even a *correct* cookie keepalive would not have helped, because nothing was
   writing the jar back to disk. That gap is now closed in §4.5 — which is the real fix for
   uninterrupted service.

Latest pass: 10 refreshed, 4 failed (`github`, `kimi-coding`, `agy` → `ReadTimeout` on
`localhost:20128` at 60s; `kilocode` → "provider returned no new token").

### 7.2 Standing prohibition
**Never restart, stop, or kill OmniRoute.** Idempotent `/api` calls only. Self-heal `FAULT_PORT` and
`FAULT_TAB`, **never `FAULT_AUTH`**. DB access read-only (`mode=ro`), and never select
`apiKey`/`token`/`secret` columns.

---

## 8. Chrome operations `[VERIFIED]`

### 8.1 Launching Chrome so it survives
- **`DETACHED_PROCESS` alone is not enough** — the child dies with the parent. Chrome needs a **new
  process group**.
- **Chrome remembers off-screen window placement.** A window restored off-screen is invisible and
  looks like a launch failure. Fixed in commit `4ebc5c7` by resetting `Preferences` placement to
  on-screen coordinates.
- **Google refuses sign-in on a CDP-enabled Chrome.**
- **Always pin `--profile-directory`.** Which profile holds Flow PRO versus `niloydassana` matters,
  and the cookie names that prove a real sign-in are seat-specific (see the seat-map memory).

### 8.2 Tab discarding — "why do tabs reload when I click them?" `[VERIFIED 2026-08-24, fixed 2026-08-26]`
**Cause:** Chrome's **memory saver discards an idle tab's renderer**. The tab remains in the tab strip
and still appears in `/json/list`; browser-domain CDP calls still answer instantly — but there is no
execution context, so **every `Runtime.evaluate` hangs until the deadline**. When a human clicks a
discarded tab, Chrome must re-create the renderer, which means reloading the page from scratch.
**The reload-on-click and the CDP hang are the same bug wearing two faces.**

Two things make it fire harder here, both self-inflicted:
- A sweep leaves tabs idle *by construction* — it works one tab while twenty sit still, which is
  exactly memory saver's trigger.
- An **off-screen or covered window reads as occluded**, and Chrome backgrounds occluded windows
  aggressively. Given this repo's off-screen-window history, the automation windows are prime
  candidates.

**Recovery for an already-discarded tab** (cheapest first, in `video_router.wake_tab`):
`GET /json/activate/<targetId>` re-creates the execution context (`document.readyState` returned in
0.4s afterwards); if it still will not evaluate, **one `Page.navigate` to the URL it is already on** —
navigate is dispatched by the *browser* process, so it works on a tab that cannot run JS, and Flow's
project id survives because the URL is unchanged.

**Prevention — `scripts/automation/chrome_no_discard.py`, two layers, neither sufficient alone:**

1. `NO_DISCARD_FLAGS` — for a Chrome you are launching now:
   ```
   --disable-features=HighEfficiencyModeAvailable,MemorySaverModeAvailable,HeuristicMemorySaver,WebContentsDiscard,CalculateNativeWinOcclusion
   --disable-backgrounding-occluded-windows
   --disable-renderer-backgrounding
   --disable-background-timer-throttling
   ```
   Old and new feature spellings are both listed because the name changed across milestones and
   Chrome silently ignores features it does not know — so listing both costs nothing and survives an
   upgrade. `CalculateNativeWinOcclusion` is the one that stops an off-screen window being treated as
   hidden.

2. **Profile `Preferences` patch — the high-leverage half.** This repo launches Chrome from ~12
   different scripts; a setting stored *in the profile* is inherited by all of them without editing
   one line of argv.
   ```
   performance_tuning.high_efficiency_mode.state       = 0
   performance_tuning.high_efficiency_mode_enabled     = false
   performance_tuning.battery_saver_mode.state         = 0
   performance_tuning.tab_discarding.exclusions        = ["*"]
   ```
   `tab_discarding.exclusions = ["*"]` is the belt: it holds even on a milestone that renamed the
   feature flag out from under us.

**Ordering trap (important).** Chrome **rewrites `Preferences` on exit** from its in-memory copy, so a
patch written underneath a running Chrome is discarded on shutdown. Correct sequence:
**close Chrome → `--apply` → relaunch with the flags.**

**A detection defect worth learning from.** The first version detected "is Chrome holding this
profile?" by opening `Cookies`/`Preferences` for append and catching `PermissionError`. **That does
not work on Windows** — it reported all 13 profiles free while four Chromes were live on them, which
would have produced exactly the evaporating patch the module warns about. The signal that works is
the **process command line**: enumerate `chrome.exe` and parse `--user-data-dir`. Note this is the
*opposite* polarity from §3.4, where a locked `Cookies` file *does* prove Chrome is running — the
lesson is that file-lock probing is unreliable in one direction, not both.

Current result: **13 profiles found, 7 patched durably, 6 held** by live Chromes on
`automation_profiles\{providers, niloy, seat2, seat3}`.

### 8.3 `chrome_live_guard.py` (646 lines) — the safety interlock
Exists because cloning the live profile permanently revoked a Google session on **2026-08-22**.
Public API: `resolve`, `verdict`, `is_live`, **`assert_safe(path, who)`**, `safe_profile_dir`,
`live_devtools_ports`, **`assert_cdp_safe(endpoint, who)`**, plus `install_subprocess_guard()` /
`install_import_hook()` which intercept process launches so a stray `--user-data-dir` pointing at the
live profile is refused rather than executed. Its refusal is deliberately **not** an `Exception`
subclass, so a broad `except Exception` cannot swallow it — catch `BaseException` if you must.

**Gotcha:** two robot Chrome worlds on port 9222 can coexist and be confused for one another.

---

## 9. Layer 5 — Video

### 9a. The video replay path already exists `[VERIFIED]`

The greps proved it, flat out — video is **the same one-liner as chat** (Law 4), not a new engine:

- `capture_sessions_cdp.py:66` — `SENTINEL = "Reply exactly one word: Omni."`; the file's own comment
  is *"One sentinel prompt for every provider -- no per-provider adapters,"* and it **refuses to save a
  capture with no sentinel** in the body (nothing to swap ⇒ nothing to replay).
- `universal_replay.py` — the chat replay swap. `video_universal_replay.py` —
  `VideoUniversalSessionClient(UniversalSessionClient)`, the **video** swap already sitting there:
  `_transform_video_payload` substitutes the prompt into the recorded genuine body (handles Digen's
  nested `scene_params`), `_extract_job_id` / `_extract_video_url`, `poll_job_status` (async
  submit→poll→result). Its `chat()` submits + polls + returns the URL. (Ignore its `generate_video()` /
  `__main__` — that's an OLD live-CDP-Playwright path, not the replay client.)
- `record_video_job.py` — records the full async submit→poll→result exchange sequence into
  `state/secrets/session_{host}.json` (read-only, on the ROBOT Chrome). `digen_session_replay.py`,
  `veo_session_replay.py` — per-provider video replay, already written.
- **Wired into the pool.** `session_pool.py:55-68` (`_client_for`) returns `VideoUniversalSessionClient`
  for `modality=="video"` (or video-ish hosts) whenever the secret carries a `recorded_job` /
  `recorded_exchange`; `session_pool_shim.py` already serves it over HTTP on `:8190` as model
  `video/{host}/auto`. So the engine is complete end-to-end.

**The gap is closed (worklog #1134, 2026-08-28).** The async video face now lives on the shim
itself: `:8190` serves `POST /v1/video/jobs` → `GET /v1/video/jobs/{id}` → `?job_key=`
reconciliation → `DELETE`, backed by the durable `VideoJobStore` ledger
(`state/video_jobs_8190.json`, idempotent by the consumer's `job_key`, atomic writes). The submit
answers **202 with an immediate receipt** and renders in a worker thread — the HTTP connection is
never blocked on the render. `video_provider.py`'s normalise/estimate/confirm/submit stack is the
WRONG engine — it is not on the replay supply path. Full contract detail in §25.

### 9b. The live-CDP router half `[INVENTORY]`

- `video_router.py` (2,294 lines) — the largest file; seat routing, fault classification, tab waking.
- `video_seat.py`, `video_provider.py`, `video_provider_flow.py`, `video_provider_rtst.py`,
  `googleflow_client.py`, `rtst_client.py`, `veoaifree_client.py`, `video_key_harvester.py`.
- **Digen contract** `[VERIFIED earlier]`: submit / poll / result wire, **custom-header auth**,
  **30 credits per 5-second clip ⇒ 4 clips per free account**. Parked defect:
  `SSLError: CERT_VERIFY` on `api.digen.ai`.
- Known defect: a **missing Flow tab misclassifies as `fault 'other'`** instead of the heal-able
  `FAULT_TAB`.
- The **5-minute scheduled task "OmniRoute Video Router (keepalive)"** — not the NSSM service — is
  what reopens the Chrome window. **Killing Chrome never wins**; deal with the task.

---

## 10. Verification discipline

The single most valuable habit in this repo: **probe, never trust recorded status.**

- `state/replay_check.json` — the supply gate the pool server reads.
- `state/replay_raw/*.txt` — raw bodies kept for shape forensics.
- `probe_route_truth.py` (406 lines) — **defective and never run**: line ~153 still posts to
  `/v1/chat/completions`. Must be changed to `/v1/messages` with an Anthropic response parser first
  (§1), or its output repeats the original certification mistake.
- `sync_confirmed_models_to_clients.py` still points at
  `state/healthy_provider_models_rescan.json`; it should point at `state/route_truth.json`.
- `probe_tool_fidelity.py` — `probe()` ignores its `timeout` parameter (the body uses the
  module-level `TIMEOUT`) and there is no `--timeout` CLI flag. Harmless but incomplete.
- **Do not declare a key dead from a gateway error.** Decrypt and `curl` the provider directly first.
- The gateway at `:20128` **force-streams SSE** and returns SSE even with `stream: false` — which
  looks exactly like a dead provider and is not.

---

## 11. File reference — the live technology

| File | Lines | Role |
|---|---|---|
| `universal_replay.py` | 607 | replay engine: injection, extraction, cookie rotation `[VERIFIED]` |
| `chat_pool_server.py` | 502 | HTTP face for harvested chat sessions, `:20130` `[VERIFIED]` |
| `capture_sessions_cdp.py` | 779 | CDP capture of genuine exchanges + jars `[VERIFIED]` |
| `replay_check.py` | 190 | the supply gate; verdict vocabulary `[VERIFIED]` |
| `inspect_reply_shape.py` | 167 | response-shape forensics; pins answer paths `[VERIFIED]` |
| `chrome_no_discard.py` | ~230 | stops tab discarding, two layers `[VERIFIED]` |
| `chrome_live_guard.py` | 646 | refuses any touch of the operator's live Chrome `[VERIFIED]` |
| `oauth_keepalive.py` | 195 | OmniRoute OAuth refresh (native endpoint) `[VERIFIED]` |
| `video_router.py` | 2,294 | live-CDP video seat routing + self-heal (§9b) `[INVENTORY]` |
| `video_universal_replay.py` | — | video replay swap: `VideoUniversalSessionClient`, prompt→body, job-id + URL extraction, async poll (§9a) `[VERIFIED]` |
| `record_video_job.py` | — | read-only capture of the async submit→poll→result exchange into the secret (§9a) `[VERIFIED]` |
| `digen_session_replay.py` / `veo_session_replay.py` | — | per-provider video replay clients `[VERIFIED]` |
| `session_pool.py` / `session_pool_shim.py` | — | LRU router over every grabbed session (chat + video via `modality`); HTTP face on `:8190` — the designated consumer endpoint (§1, §25) `[VERIFIED]` |
| `video_job_store.py` | — | thread-safe durable video-job ledger at `state/video_jobs_8190.json`; idempotent by `job_key`, atomic writes; backs the shim's async `/v1/video/jobs` contract (§25) `[VERIFIED 2026-08-28]` |
| `selenium_browser_replay.py` | ~430 | **in-browser** replay: attaches to the live signed-in Chrome, fires the recorded exchange via `fetch()` from the request's own origin, with send-time reconstruction + live-bearer harvest (§18) `[VERIFIED 2026-08-27]` |
| `launch_and_harvest_chats.py` | — | multi-tab sweep orchestrator `[INVENTORY]` |
| `drive_capture.py` / `drive.py` | 1,198 | the working Google-path harvester `[INVENTORY]` |
| `signup_browser.py` / `hf_signup_cdp.py` / `grab_session.py` | — | autonomous signup + capture spine — **reuse, do not rebuild** `[INVENTORY]` |
| `omniroute_api.py` | — | management API abstraction (`redact`, `login`, `get_connections`, `refresh_connection`) `[VERIFIED]` |

The remaining ~178 files are earlier pilots (`pilot_*.py`), one-shot probes, and superseded
harvesters. They are history, not architecture. Do not extend them.

---

## 12. Environment traps

- **Quoted bash heredocs (`<<'PY'`) still collapse backslash pairs here.** Inlining a regex with `\\`
  produced `re.error: unterminated character set`. **Write a file instead.**
- **Raw Python strings cannot hold `\""`** — `r"...(\""?)..."` is a `SyntaxError`. Prefer
  single-quoted PowerShell and parse in Python.
- `pkill -f` does not kill python processes here (§5.1).
- Windows `SO_REUSEADDR` allows duplicate port binds (§5.1).

---

## 13. Task ledger

| # | Task | State |
|---|---|---|
| 1 | veoaifree chat harness | **DONE** |
| 2 | video harness ("same approach, dirty and easy") | PENDING |
| 3 | make OmniRoute defect-free and highly efficient | **IN PROGRESS** |
| 4 | film pipeline (study, then parallelized async job model) | PENDING |

End goal: *"total 4 tasks end of story film making app ready."*

**Open items on Task 3:** oioi is wired to the **`:8190` session pool shim** (the designated
consumer endpoint, §1/§25) — chat via `{"model": "session-pool/auto"}`, video via the async
`/v1/video/jobs` contract. The four live-E2E contract fixes (JSON-intent failover, immediate
202 video receipts, idempotent job lookup, cancellation) are deployed (worklog #1134); the
remaining step is a full end-to-end re-verification of the JSON-intent + video-receipt paths.
Still open: rebuild the oioi config (`state/oioi_inference_config_final.json` is **INVALID** —
it names the credit-drained `agentrouter/claude-opus-5` as `isFamilyDefault`; `ainative`
credentials are dead, returning HTTP 404 "no active credentials"); fix and run
`probe_route_truth.py`; give `you.com` a prompt it fits (it is served-eligible but scored
`NO_ANSWER` on arithmetic — it answered `58` *plus* an aurora borealis explanation, i.e. it is
a search product and prefers natural-language prompts); re-capture Gemini and the three
auth-dead seats (`cerebras`, `groq`, `chatgpt` — CDP recorded only 6 headers for Cerebras and
no auth header; consider merging `Network.requestWillBeSentExtraInfo`).

## 14. The superset gateway `[VERIFIED 2026-08-26]`

A client config carries exactly **one** gateway base URL. Pointing oioi at the pool would therefore cut
it off from the paid OmniRoute routes, and pointing it at OmniRoute means the free pool is unreachable.
The obvious answer — ship two configs and swap them when credits die — fails for a human reason: the
swap is a manual step that gets forgotten at precisely the moment it matters.

So `:20130` is a **superset** of `:20128`:

| request | handled by |
| --- | --- |
| `model` starts with `pool/` | served locally from a captured session |
| anything else | forwarded verbatim to `:20128`, `Authorization` passed through |
| upstream refuses, or is unreachable | served from the pool; reply carries `x_pool_fallback_reason` |

One config covers both, and the failover is automatic.

**Forward the raw bytes.** `Handler._read_json` stashes `self._raw` and `Upstream.forward` posts *that*,
not a re-serialised dict. Re-serialising silently drops every field the pool does not model — `tools`,
`temperature`, `cache_control`, thinking budgets — which is exactly what the paid routes exist for.
Verified with an echo upstream: all five body keys arrived intact and the auth header was present.

**The fallback trigger is deliberately narrow.** `CREDIT_HINTS` is only matched when the response is
*already* an error — `status >= 400`, or a 200 whose body carries an `"error"` envelope. A model's own
prose can contain the word "credit"; treating that as exhaustion would throw away a paid reply **and**
burn a free session for nothing. A healthy 200 is always relayed untouched, `X-Pool-Source: upstream`.

**Upstream is tried once, never retried.** A wall or a drained account does not clear in milliseconds.

Verified paths: `pool/auto` → `58` locally via aymo; a non-pool model relayed from a stand-in upstream;
and a real `:20128` reply of HTTP 404 `"no active credentials"` falling back to cohere with the reason
stated in the response body.

`GET /v1/models` merges both sides, tags each row with `source`, and reports `x_upstream_reachable`.
`:20128` currently serves no model list, so the merge degrades to pool-only and says so rather than
pretending.

---

## 15. The cookie keepalive — solved `[VERIFIED 2026-08-26]`

§7 established that `OmniRouteOAuthKeepAlive` does nothing for harvested browser sessions: there is no
token to refresh, only traffic. §4.5 established that a successful reply carries `Set-Cookie` which
`universal_replay._absorb_cookies` writes back to disk. Put together, the keepalive is obvious in
hindsight: **make sure nothing sits idle long enough to decay.**

`Heartbeat` is a daemon thread inside `chat_pool_server.py` (`--heartbeat-hours`, default 6).

**It must be in-process.** A standalone keepalive daemon would replay the same session concurrently
with the pool, rotate the cookie on disk under the pool's in-memory jar, and break the next real
request — and the symptom would look like a dead provider, sending the next agent to re-capture a
session that was fine. The heartbeat takes the provider's own `threading.Lock`, so it can never overlap
a real call. Do not "extract this into its own service".

**It is a floor, not a schedule.** Only a provider idle past the window is touched, so a busy pool costs
nothing extra. Tick is `clamp(idle_s / 10, 5s, 300s)` — a 6-hour window does not need a 5-minute tick,
and deriving it means a short window is actually testable, which is how this shipped proven instead of
assumed.

**Two defects found by measuring, both fixed:**

1. `_due()` first gave never-rotated providers a small `idle_s + 1` sentinel, so the one provider that
   *does* rotate outranked every other forever. Measured: 4 beats to aymo in 40 s, zero to the other
   four — a breadth-not-depth violation hidden inside a keepalive. Fixed: no stamp now means
   `float("inf")`, because unknown freshness is the *weakest* state, not the strongest.
2. Testing with a 3.6-second window walled aymo inside a minute. The 3600 s stand-down caught it and
   never retried. That is direct evidence the 6-hour production window is load-bearing. **Never test a
   heartbeat window under ~1 h against a live seat.**

Proof it works: `session_aymo_ai.json` `cookieRotatedAt` moved 08:24:33Z → 09:00:08Z from heartbeat
traffic alone, and the round-robin then covered all five providers evenly.

Reading `/health`: a provider with `heartbeats > 0` and `state: cooling` failed *on a heartbeat*, which
means the session is genuinely gone rather than merely idle. That distinction is the whole diagnostic
value of the counter.

---

## 16. Restoration and portability `[VERIFIED 2026-08-26, UPDATED 2026-08-27]`

### What survives what

| failure | chat supply (file-backed) | Chrome-backed chat seats | video supply |
| --- | --- | --- | --- |
| pool process crash | survives — supply is files on disk | survives — tabs stay open | survives if Chrome alive |
| Chrome crash | **survives entirely** | destroyed until tabs re-opened | **destroyed** — needs live CDP tabs |
| full reboot | survives | **survives** — cookies persist in profile on disk; video router task relaunches seat Chromes at 5-min interval | survives after video router relaunches seats (≤5 min) |
| move to a new machine | survives (session files) | **provider sessions port via CDP cookie export** (`cookie_porter.py`, proven 2026-08-27: 1,842 cookies / 335 domains); Google SSO does not (DBSC) | same as chat Chrome seats — cookie export ports the sign-ins |

The 2026-08-27 correction: the old table said "profiles cannot be copied" — that is true of a
**raw directory copy** (DPAPI-sealed Cookies DB). But a live CDP session exposes all decrypted
cookies via `Storage.getCookies`, and those re-inject cleanly on any machine via
`Storage.setCookies`. Provider sessions ARE portable; only the Google account layer and
localStorage-bound tokens are not. See PORTING.md §Provider Session Portability.

### `omni_supervisor.py`

Declarative service table, `--once` / `--up` / `--watch`, writes `state/supervisor_status.json`.

Three rules encoded in the code, not just the docs:

- **OmniRoute is never restarted, stopped, or killed from here.** Probe and report only. It holds live
  OAuth connections whose refresh state is server-side, and bouncing the process to "fix" a bad probe
  has cost real credentials before. A red line in the report *is* the correct output.
- **The video router belongs to the 5-minute scheduled task** (`OmniRoute Video Router (keepalive)`).
  Do not fight it; it always wins. Marked `owned=False`.
- **Restarts match on the command line, not the port.** A port can be held by somebody else's service,
  and killing it would be the outage rather than the fix. A foreign process on our port is reported as
  `PORT_TAKEN_BY_OTHER` and left alone. Backoff is `[5, 15, 60, 180]` and then it **gives up and
  reports** — a supervisor in a restart loop is indistinguishable from the fault it is hiding.

Verified: killed the pool → detected `DOWN` → `--up` → restarted → answering `58` again.

### `omni_portable.py`

The hard line is **credential storage**, not code.

**Portable** — `state/secrets/session_*.json` (the whole chat supply), `state/replay_check.json`,
client configs, the repo. Nothing in a session file is machine-bound.

**Never raw-copy** — `state/omniroute_password.bin` (DPAPI-sealed to this user+machine) and
`state/automation_profiles/**` / `browser_profile` / `harvest_profile`. Chrome's cookie encryption key
is DPAPI-bound, so a raw-copied profile has a `Cookies` database it cannot read: **every file present,
every login gone.** That is the worst possible failure mode because it reads as a successful restore.
Google is worse — DBSC can treat the move as a compromise and revoke permanently (§8).

**But provider sessions DO port via CDP cookie export (proven 2026-08-27).** `cookie_porter.py`
attaches to the live seat Chromes and calls `Storage.getCookies`, which returns all cookies
**decrypted** — including HttpOnly auth tokens — because the DPAPI seal only protects the on-disk
DB, not the running browser's memory. Verified: 1,842 cookies across 335 provider domains exported
from ports 9222-9225, 253 of them auth-like (session/token/JWT). `--import` re-injects them into a
fresh profile on any machine via `Storage.setCookies`. What still needs a human on a new machine:
Google SSO sign-in (DBSC device-bound), localStorage-bound tokens, and re-sealing the OmniRoute
password. `--doctor` prints them every time, so nobody concludes an import was complete when it
structurally cannot be.

Two guards worth keeping:

- `--export` **refuses to write inside the repo.** The bundle holds live cookie jars and would be one
  `git add -A` from publication.
- `--import` **will not roll a cookie backwards.** Rotation is written into the session file on every
  successful call, so a bundle taken last week holds jars the provider has since rotated away from;
  restoring it looks like success and leaves dead sessions. Any session file whose local copy has a
  newer `cookieRotatedAt` is skipped and named. Verified with a deliberately staled bundle: 27 files
  restored, the live aymo jar kept.

### `install_autostart.py` — making reboot recovery real `[VERIFIED 2026-08-26]`

`omni_supervisor.py` brings the rig back after a crash, but only while it is itself running. After a
full reboot nothing starts it, so "complete reboot recovery" is only real once the supervisor launches
at logon. `install_autostart.py` arms exactly that — the supervisor's `--watch` loop at logon — by one
of two mechanisms, and nothing else.

- **Dry run by default.** With no flags it prints the exact command and changes nothing. `--status`
  reports whether either mechanism is armed; `--uninstall` removes both. Both are fully reversible,
  which is why arming is a normal action rather than a one-way door.
- **`--install` → a Windows Scheduled Task** (`OmniRoute Rig Supervisor`, `ONLOGON`). This needs
  elevation. On this rig the operator's shell is a **non-elevated Admin split token**, so
  `schtasks /Create` returns *Access is denied* while `/Query` succeeds — proof it is a UAC boundary,
  not the sandbox. Use it only from an elevated shell.
- **`--startup` → a hidden `.vbs` in the user's Startup folder** (`%APPDATA%\…\Startup\
  omniroute_rig_supervisor.vbs`). No elevation, and it matches the omniroute `*.vbs` launchers already
  parked there. **This is the mechanism armed 2026-08-26.**
- **Run it with the venv python.** `_task_command()` fires `sys.executable`'s sibling `pythonw.exe`, so
  the interpreter you invoke the installer with is the one the launcher runs at logon; a bare system
  python would miss the supervisor's deps.
- **It launches the supervisor, not the rig.** The supervisor's safety model is unchanged: it restarts
  only the chat pool (owned), never touches OmniRoute, and does not fight the video router's own
  5-minute keepalive task. Neither mechanism launches Chrome — auto-launching a real profile is the one
  move that has cost a Google session (DBSC), so video-seat sign-in stays a deliberate operator step.
  Chat supply (files on disk) returns fully and automatically; the video asymmetry is inherent.
- Verified 2026-08-26: `--install` reproduced the *Access is denied* elevation boundary; `--startup`
  wrote a well-formed (quote-doubled) launcher and `--status` confirms it present.

## 17. Layer 6 — The character-image relay `[VERIFIED (logic) 2026-08-26]`

**The need.** A film kit has characters — "Alice", "Bob" — each a reference image uploaded once. Every
generator that renders a clip (Flow, digen, rtst, veoaifree) needs those faces pushed into *its* image
inputs. Across a 2,160-clip film that is not a by-hand job. `character_relay.py` uploads each character
**once per generator**, remembers the asset handle the generator returns, and reuses it in every
generate request for that character.

**The "omni way" applies unchanged — one substitution differs.** Chat replay carries a text *sentinel*
in a recorded POST and string-replaces it with the prompt. Upload relay carries a *file part* in a
recorded multipart POST and swaps that one part's bytes + filename for the character image, leaving the
rest of the recorded envelope byte-identical. Both replay a real exchange with the seat's jar; neither
reconstructs a request (Law 4). The per-generator "which field takes the handle" table is a payload
*shape* contract (same category as the veoaifree MODELS map or the digen submit/poll/result contract),
not a request adapter.

**Pieces (all built, in `character_relay.py`):**

- `GENERATORS` — the contract table for flow / digen / rtst / veoaifree. Endpoints are **not**
  hard-coded; they arrive with the recorded upload session. Slot names carry `confidence:"assumed"`
  until a capture confirms them on the wire.
- `load_kit()` — a film-kit directory → characters, keyed by **content hash** not filename, so the same
  face under two names uploads once. Non-images and oversized files are refused with a reason, not
  skipped silently.
- `swap_file_part()` — the faithful multipart swap: locate the part by `name="…"`, rewrite its
  `filename`, replace the payload between its header terminator and the next boundary, touch nothing
  else. Raises if the part is absent (a silent no-op upload is worse than a stop).
- `bind_slots()` — pure, deep-copying injector that places a handle into a generate payload per the
  contract (`id` / `url` / `array_append` forms). This is the hot path; it does no I/O and never fails
  on a network condition.
- `state/character_relay_map.json` — the upload-once cache, keyed `film::generator::sha256`.
- Transport is isolated behind one callable so `--selftest` injects a fake and the engine is provable
  without a network. Card / captcha / quota language in a response → `WALL`, stopped and reported,
  never solved (Law 5).

**The one external input, captured later.** Each generator needs a recorded upload exchange saved as
`state/secrets/upload_<generator>.json` (same capture step every chat session went through: upload one
image by hand in a signed-in tab, record the multipart POST). Until that file exists, `relay()` returns
`PENDING_CAPTURE` and names exactly what to record — it never fabricates an upload.

**Verified 2026-08-26:** `--selftest` passes 25/25 — multipart swap (inject/drop/keep-others/rename/
boundary-count), image sniffing, all three slot forms, non-mutation of input, asset extraction, wall
detection, and a full `relay_one` against a fake transport including recomputed `Content-Length` and
upload-once caching. `--plan` against a real 2-character kit correctly emits 8 `PENDING_CAPTURE` rows
with actionable capture instructions and touches no network. Live upload is the "testing later" step,
gated on the recorded sessions.

---

## 18. Layer 7 — In-browser replay (Selenium attach) `[VERIFIED 2026-08-27]`

**The shift.** §4's `universal_replay.py` fires recorded bytes from *outside* the browser with
`requests`. That works for providers whose request is fully described by the recorded bytes plus one
prompt substitution. It structurally cannot work for providers that add something **at send-time**
inside the page — a fresh nonce, PoW, CSRF, message id, or a short-lived bearer minted by in-page
SDK code. §6 listed those as "structural defeats". This layer defeats the defeats by firing the
request **from inside the live signed-in browser**, on the request's own origin, where all the
send-time context (cookies, storage, CORS, SDK state) is already present.

**File:** `scripts/automation/selenium_browser_replay.py` (~430 lines).
**Run:** `python scripts/automation/selenium_browser_replay.py --port 9222 --only <name-substrings>`
**Output:** `state/selenium_browser_replay.json`.

### 18.1 Attach, never launch — and NEVER quit
The tool attaches to the operator's already-running, already-signed-in Chrome via
`Options().add_experimental_option("debuggerAddress", "127.0.0.1:9222")` then
`webdriver.Chrome(options=opts)` (~3.4 s attach to ~37 live windows). It **never launches a browser,
never signs in, never clicks, never types** — the mandate is replay-only. And it **never calls
`driver.quit()`**: that would close the operator's live Chrome.

### 18.2 The CORS gap and its fix
A `fetch()` from the app tab (e.g. `chat.deepseek.com`) to the API origin (e.g.
`api.deepseek.com`) dies with `TypeError: Failed to fetch` — cross-origin, no CORS grant. Fix:
fire from a tab **on the request's own origin**. `API_ORIGIN_TO_TAB_ORIGIN` maps API origins to the
signed-in app origin; when the recorded URL's origin has no open tab, the tool opens one via
`switch_to.new_window("tab")` (NOT popup-blocked, unlike `window.open`) + `get(origin + "/")`,
fires, then `close()`s it and switches back.

### 18.3 Send-time reconstruction (`SEND_TIME_RULES`)
Some providers reject a byte-identical replay because one field must be *fresh at send-time*. The
tool rewrites exactly those fields and nothing else: mistral `messageId`, chathub
`streamId`+`x-client-time`, felo `search_uuid`, huggingface `generationId`, chatglm
`nonce`/`timestamp`/`request-id`. This is not request reconstruction (Law 4 stands) — it is
replacing the stale send-time values with fresh ones, the same single-substitution discipline
applied to the fields the provider regenerates.

### 18.4 Live-bearer harvest (`LIVE_BEARER_RULES`) — the groq fix
Providers whose auth is a **short-lived token minted by in-page SDK code** reject the recorded
bearer minutes later. groq returned 401 "invalid or expired jwt": the recorded bearer was a
short-lived **Stytch** JWT. The live one sits in the signed-in tab — in the `stytch_session_jwt`
cookie, else the `stytch_sdk_state` localStorage blob (`session_jwt`/`jwt` key). The tool harvests
it at send-time and swaps it into the `Authorization` header. **A stale bearer is a class-(a)
send-time gap, never evidence the site is dead.**

### 18.5 Two-leg flows — the felo and chatx fixes
Some hosts answer on a **second leg** the capture never recorded. An accepted-200-with-a-handle is
a multi-step flow, not a dead site:
- **felo:** leg 1 POST `.../question` → 200 + `stream_key`; leg 2 GET
  `/api/message/v1/stream/{stream_key}?offset=0` (SSE, same bearer). Leg 2 was discovered by
  grepping felo's own JS bundles.
- **chatx:** leg 1 POST `/sendchat` (form body; fresh `_token` from `meta[name="csrf-token"]`) →
  200 + `conversions_id`/`ass_conversions_id`; leg 2 GET
  `/chats_stream?user_id=&chats_id=&current_model=&conversions_id=&ass_conversions_id=&...`
  (SSE EventSource; parse `type=="response.output_text.delta"` → accumulate `d.delta`). Leg 2 was
  discovered from chatx's inline JS.

**Body handling trap (load-bearing):** surgical regex edits on the **RAW recorded body string**.
Never `json.loads` then `json.dumps` — re-serialization double-encodes the body (server receives a
JSON *string*, not an object → felo 422 "Input should be a valid dictionary"). Keep everything else
byte-identical.

### 18.6 Verdict rules and current state
- SSE `delta.content` fragments are **contiguous** — concatenate with **no separator**
  (space-join breaks mid-word splits like `"str"+"icks"`). Exclude non-content deltas (groq's
  `delta.reasoning`).
- **REPLAY_OK (9):** 1min, gemini, perplexity, mistral, cohere, qwen, groq, felo, chatx.
- **Confirmed class-(b) dead (4), operator-verified in Chrome:** huggingface, aymo, chathub,
  veoaifree — all genuine quota walls.

### 18.7 Two Selenium traps that cost real time
- **JS ASI trap:** `driver.execute_script("return " + js)` where `js` **starts with a newline** →
  automatic-semicolon-insertion makes it `return;` + dead code → returns `None`. Always
  `js.strip()` before prepending `return`.
- **Pass bodies as script arguments:** `execute_async_script(js, url, method, headers, body)` —
  never string-embed the body into the JS source.

---

## 19. The Adapter Thesis — why one Chrome serves every provider `[VERIFIED 2026-08-27]`

**The question that produced this section:** if every provider needs different send-time behavior,
how does Chrome — a *single* architecture — know what each one wants? How does it "smell" it?

**The answer:** Chrome knows **nothing** provider-specific. It is a universal executor — one fixed
machine (JS engine + web primitives: `fetch`/XHR/EventSource/WebSocket, cookies, storage, crypto,
DOM) for every site on Earth. The per-provider adaptation is **not in Chrome**. It is the
**provider's own JavaScript**, shipped with every page load and executed by Chrome. That JS *is*
the adapter: it encodes the endpoint, the auth scheme, the PoW algorithm, the x-sign signing, the
2-leg flow, the CSRF location. Chrome "behaves accordingly" because the provider hands it the exact
program for talking back, and Chrome faithfully runs it.

**Recorded bytes are the corpse of one run of the adapter.** Replaying the corpse dies; you must
re-run the machine. This is precisely why every class-(a) fix in §18 was re-deriving the adapter by
hand (groq's Stytch bearer, felo/chatx's 2-leg stream, chatx's CSRF meta tag).

**Live proof (read-only, nothing fired):** `scratch_prove_adapter_in_page.py` attached to seat1,
opened the deepseek tab, and surfaced deepseek's own request pipeline from its loaded
`requests.js` — it monkey-patches `XMLHttpRequest.prototype.open/.send`
(`this.__METHOD__=..., this.__URL__=...`, `_$interceptRequest({method,url,body})`). The adapter is
present and executable in-page. Chrome didn't bring it; deepseek shipped it.

**The doctrine upgrade (the strategic pivot):**
- **OLD:** replay what Chrome *sent* — reconstruct the bytes. O(n) reverse-engineering, brittle.
- **NEW:** make the site *send* what Chrome would send — **invoke the site's own sender** in the
  live signed-in tab. Correct-by-construction: fresh CSRF/PoW/bearer/2-leg/signing all free, because
  that is literally what the site's own code does.

**Adapter-invocation blueprint** (for each provider, live tab already open, adapter loaded):
1. Locate the site's own send entry-point (submit handler / send function).
2. Call it with the sentinel prompt via `execute_script`.
3. The site's own code builds the request correctly by construction.
4. Read the answer from the DOM / the site's own stream handler.

This collapses "reverse-engineer N protocols" into "locate N entry-points" — generic and
mechanical. It is the correct generalization of everything in §18.

**Honest limits:** class-(b) real deaths (empty quota tanks) are fixed by no adapter;
device-attestation / TLS-fingerprint / DRM bindings are genuine walls; a live signed-in session is
still required. Law 5 stands — walls are reported, never solved.

**CS anchor:** the stored-program / universal-machine principle applied to network clients. The web
is the only large-scale RPC system that is **self-describing in executable form** — the server ships
its own client as code. REST/OpenAPI describe shape, not behavior; gRPC needs a proto; native apps
are closed. Browsers exploit this; byte-replay throws it away. The grail is to stop throwing it
away.

**Artifacts:** `scratch_prove_adapter_in_page.py`, worklog #1094, repo memory
`/memories/repo/adapter_thesis.md`.

---

## 20. The 24-hour sweep (2026-08-26 → 2026-08-27) — what changed since §19 `[VERIFIED]`

Worklog #1081–#1110. The system went from "5 replayable chat hosts" to a **consumer-ready
load-balanced endpoint serving 50 models (25 chat + 23 video + auto routes)**. The arc:

1. **Chrome Gap Doctrine codified (#1088):** every replay failure must be classified as
   (a) fixable send-time gap, (b) real server-side death (proven by operator-in-Chrome
   reproduction), or (c) capture bug. This killed the "declare site dead" failure mode.
2. **In-browser replay / Selenium attach (#1087, §18):** attach to the live signed-in tab,
   execute the request IN the browser context. Fixed CORS, unlocked 1min/gemini/perplexity.
3. **Send-time reconstruction + live-bearer harvest (#1088–#1093, §18.3–18.5):** groq (Stytch
   bearer), felo/chatx (2-leg SSE flows), mistral (409 fix), qwen/cohere (frame aggregation).
4. **Adapter Thesis proven (#1094–#1098, §19):** invoke the site's own JS sender. deepseek
   (PoW solved free), chatglm (GLM 5.3), cerebras (reCAPTCHA-shadow trap fixed). Generic
   adapter driver built.
5. **Chrome-backed pool wired (#1100):** 12 REPLAY_OK hosts servable through the pool via
   `ChromeReplayClient` — the live tab IS the credential.
6. **Tab-coverage sweep (#1105):** 9 signed-in-but-unwired tabs found; 4 wired live
   (claude.ai, grok.com, copilot.microsoft.com, v0.app), 3 retired honestly.
7. **Chrome-doctrine VIDEO pool (#1108):** `chrome_video_client.py` (14 hosts) drives the
   provider's own UI in-tab to generate video. 17 video seat files. REAL MP4 proven end-to-end
   via Google Flow (4.6 MB, ftypisom magic).
8. **Full-pool load balancing fixed (#1109):** exception class-identity bug killed rotation
   after the first 429. Unified `ChatError`/`SessionExpired` across all 5 adapters. Chat (25)
   + video (23) pools now rotate with proven fall-through.
9. **Consumer-readiness hardening (#1110):** atomic `reserve()` (no double-booking under
   concurrency — proven 8 threads → 8 distinct providers), atomic state persistence
   (temp+`os.replace`), Bearer-key multi-tenancy gate (`tenant_map.json`, hot-reloadable),
   429+`Retry-After` on pool exhaustion. All four properties proven, not asserted.

**The endpoint today:** `http://127.0.0.1:8190/v1` (use 127.0.0.1, never localhost — system
proxy intercepts loopback). OpenAI-compatible. Live count as of 2026-08-28: **53 models
(28 chat + 25 video, incl. the `session-pool/auto` and `video/auto` routes)** — the number
moves as seats are hot-added/removed (§24), so treat any fixed count as a snapshot, not a
spec. Currently in open single-operator mode (no `tenant_map.json`); drop one into
`state/secrets/` to enable Bearer-key tenancy without restart.

---

## 21. Windows services registry — everything that keeps this rig alive `[VERIFIED 2026-08-28]`

Four scheduled tasks + one Startup-folder launcher. All verified present and running.

**How the tasks launch (worklog #1134, 2026-08-28 — the console-pop fix).** Three of the four
tasks run their `.bat` through a hidden `.vbs` wrapper (`wscript.exe <task>.vbs`,
`WshShell.Run cmd, 0, False`). Task Scheduler running a `.bat` directly with
`LogonType=Interactive` opens a visible console window every cycle — that was the 5-minute
"pop" the operator saw. The `.vbs` wrapper suppresses it. **Do not re-point these tasks back
at the `.bat` directly.**

| Task name | Task action (verified) | Runs | Schedule | Purpose |
|---|---|---|---|---|
| `OmniRoute Rig Supervisor (keepalive)` | `wscript.exe supervisor_task.vbs` → `supervisor_task.bat` → `omni_supervisor.py --watch` | every 5 min | Crash recovery for owned services; reports Chrome state; never touches OmniRoute, video router, or the shim |
| `OmniRoute Session Pool Shim (keepalive)` | `wscript.exe session_pool_shim_task.vbs` → `session_pool_shim_task.bat` → `session_pool_shim.py 8190` | every 5 min | Keeps the :8190 consumer endpoint alive. Sets `OMNI_VIDEO_CONFIRM_SPEND=1` (credit-spending video submit gate) |
| `OmniRoute Video Router (keepalive)` | `wscript.exe video_router_task.vbs` → `video_router_task.bat` → `video_router.py` | every 5 min | Video router + **Chrome seat self-heal** (relaunches dead seat Chromes, re-opens tabs) |
| `OmniRoute OAuth KeepAlive` | `oauth_keepalive_task.bat` (direct, no `.vbs`) → `oauth_keepalive.py` | hourly | Refreshes OmniRoute's own OAuth provider tokens via `POST /api/providers/{id}/refresh` |

| Launcher | Location | Purpose |
|---|---|---|
| `omniroute_rig_supervisor.vbs` | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` | Starts the supervisor `--watch` loop at logon (no elevation needed) |

**Inside each service bat (worklog #1134 — the detached-launch + dedup pattern):**
- **Health probe uses `curl.exe`, not python.** `curl.exe -s -o nul --max-time 3 http://127.0.0.1:8190/v1/models`.
  A python probe spawns a transient venv launcher+interpreter pair every cycle — visible churn.
- **Launch uses `start "" /b <exe> >> log 2>&1`.** This runs the service in the background and lets
  the bat exit immediately — **no resident `cmd.exe` parent** holding the console open for the
  service's lifetime. The child survives the bat's console closing; stdout still lands in the log.
- **One healthy service = TWO `python.exe` rows.** On Python 3.11/Windows the venv's `python.exe`
  is a *venvlauncher* that spawns the base interpreter as a persistent child ~33ms later. The
  interpreter child holds the port LISTEN. This is NORMAL, not a duplicate. Do not "dedup" it.
- **Duplicate-bind guard.** The shim binds via `ExclusiveThreadingHTTPServer` with
  `allow_reuse_address=False`, and `run()` wraps the bind in `try/except OSError(EADDRINUSE/10048)`
  → a clean "already serving, exiting (dedup)" no-op. So a second task firing while the shim is up
  exits harmlessly instead of racing onto the port (§24).

**Ownership rules (encoded in `omni_supervisor.py`, not just docs):**
- OmniRoute (:20128) is **never restarted, stopped, or killed**. Probe and report only.
- Video router (:8189) belongs to its own scheduled task. Supervisor marks it `owned=False`.
- **Session pool shim (:8190) belongs to its own scheduled task. Supervisor marks it
  `owned=False, required=False` and probes `/v1/models` only.** Worklog #1134: it was
  `owned=True` here AND owned by the bat task — that double ownership is exactly how duplicate
  shim instances raced onto :8190. **Single owner now: the bat task.**
- Restarts match on command line, not port. Foreign process on our port = `PORT_TAKEN_BY_OTHER`,
  left alone. Backoff `[5, 15, 60, 180]` then gives up and reports.

---

## 22. Crash / reboot / reset recovery — what comes back by itself `[VERIFIED 2026-08-28]`

### The recovery chain

```
reboot/reset
  → Windows logon
    → omniroute_rig_supervisor.vbs starts supervisor --watch
      → supervisor task (every 5 min, via supervisor_task.vbs) restarts dead OWNED services:
          • chat pool (:20130)   [owned=True]
        and probes-and-reports (never restarts):
          • session pool shim (:8190)  [owned by its own bat task]
          • video router (:8189)       [owned by its own bat task]
          • OmniRoute (:20128)         [never touched]
      → session pool shim task (every 5 min, via session_pool_shim_task.vbs) restarts the
        shim if :8190 is not answering (curl.exe probe; start "" /b detached launch)
      → video router task (every 5 min, via video_router_task.vbs) self-heals Chrome seats:
          • detects dead seat Chrome (port not answering)
          • relaunches with correct profile + CDP flags + NO_DISCARD_FLAGS
          • re-opens the remembered tab URLs (from state/video_accounts.json)
      → OAuth keepalive task (hourly) refreshes OmniRoute provider tokens
```

**Single-owner rule (worklog #1134):** each service has exactly ONE owner that restarts it.
The shim is owned by its bat task; the supervisor only probes it. Double ownership is how
duplicate instances raced onto :8190 — never reintroduce it.

### What persists across reboot (no human needed)

| Component | Persists? | Mechanism |
|---|---|---|
| Chat supply (session files) | ✅ | Files on disk — never touched by reboot |
| Provider sign-in sessions in Chrome profiles | ✅ | Cookies persist in profile's `Cookies` DB on disk; Chrome re-opens with them intact |
| Chrome seat processes | ✅ (≤5 min) | Video router task relaunches dead seats automatically |
| Tab URLs | ✅ | Remembered in `state/video_accounts.json`, re-opened on seat relaunch |
| Shim / chat pool / video router processes | ✅ (≤5 min) | Each restarted by its single owner: shim + video router by their own bat tasks, chat pool by the supervisor |
| OmniRoute OAuth tokens | ✅ | Hourly keepalive refreshes them |
| Pool cooldown state | ✅ | `state/session_pool_state.json` (atomic writes) |

### What does NOT survive (needs human)

| Component | Why | Recovery |
|---|---|---|
| Google account sign-in (Chrome Sync) | DBSC device-bound; server-side revocation on profile move | Manual Google sign-in in the seat Chrome |
| OmniRoute password | DPAPI-sealed to this user+machine | Re-enter password on new machine |
| OmniRoute OAuth provider connections | Per-machine tokens | Reconnect in OmniRoute UI |

### The key insight: provider sessions persist natively

Chrome profiles store cookies in an on-disk SQLite DB. Across a reboot on the SAME machine,
those cookies survive untouched — Chrome re-opens with all provider sign-ins intact. The DPAPI
seal only matters when you try to READ the DB from outside Chrome or COPY it to another machine.
On the same machine, across reboots, provider sessions are fully persistent. The video router
task handles the only gap: the Chrome *process* dies on reboot, but the task relaunches it
within 5 minutes, and the profile's cookies are still there.

---

## 23. Do we need Chrome running for the endpoint to work? `[VERIFIED 2026-08-27]`

**Short answer: it depends on which supply you're asking about.**

### The three supply tiers and their Chrome dependency

| Tier | Supply source | Needs live Chrome? | Survives Chrome death? |
|---|---|---|---|
| **File-backed replay** | `state/secrets/session_*.json` (cookie + recorded exchange) | ❌ NO | ✅ Yes — pure HTTP replay via `requests` |
| **API-credential seats** | Bearer token in seat file (rtst.ai, you.com) | ❌ NO | ✅ Yes — direct API calls |
| **Chrome-backed seats** | Live signed-in tab (Adapter Thesis) | ✅ YES | ❌ No — tab IS the credential |

### What works with Chrome completely dead

- All file-backed chat replay seats (the original 5 + any with `recorded_exchange`)
- API-credential video seats (rtst.ai, you.com, digen.ai)
- The shim itself (:8190) — it's a Python HTTP server, no browser dependency
- OmniRoute (:20128) — independent service

### What dies with Chrome

- All 18 `CHROME_CLIENTS` hosts (claude.ai, grok.com, perplexity.ai, deepseek, cerebras, etc.)
- All 14 `VIDEO_HOSTS` in `chrome_video_client.py` (Google Flow, veo, kling, etc.)
- These hosts return `NO_TAB` → pool falls through to next session → eventually 429 if
  no file-backed fallback exists for that host

### The practical answer

**For the endpoint to serve its FULL 50-model catalog: yes, the 4 seat Chromes must be running.**
They carry the Chrome-backed chat seats (18 hosts) and all video generation (14 hosts).

**For the endpoint to serve file-backed supply only: no Chrome needed.** The ~10 file-backed
seats replay via pure HTTP.

**After a reboot:** the video router task relaunches all 4 seat Chromes within 5 minutes.
Provider sessions persist in the profiles. So the full catalog comes back automatically.

### Why the 4 seats exist

The 4 seats (ports 9222-9225) are 4 separate Chrome profiles, each holding different provider
accounts. This is the "breadth beats depth" strategy: spread load across multiple accounts to
avoid per-account rate limits. Each seat holds ~10-15 signed-in provider tabs. The pool's LRU
rotation spreads requests across all of them.

---

## 24. Zero-Restart Hot-Add of Providers (worklog #1112, 2026-08-28)

**Doctrine:** "one chrome, infinite sites" — Chrome needs no adaptation to serve a new site,
and neither does the pool. Adding a provider is now a DATA operation, not a code or restart
operation.

### The contract

| Action | What you do | What the endpoint does |
|---|---|---|
| Add a provider | drop `state/secrets/session_<host>.json` (+ open the signed-in tab in any seat Chrome) | next request auto-rescans; host appears in `/v1/models` — NO restart, NO code edit |
| Remove a provider | delete the seat file | next request drops it — NO restart |
| Force a rescan now | `POST /v1/rescan` | returns `{added, removed, changed, total}` + dispatchable count |

### Seat-file-declared Chrome backing (no registry entry needed)

A seat file may declare its Chrome backing inline. Three accepted forms:

```json
{"host": "chat.newsite.com", "modality": "chat", "chrome": {"tab": "chat.newsite.com"}}
{"host": "chat.newsite.com", "modality": "chat", "chrome": "chat.newsite.com"}
{"host": "chat.newsite.com", "modality": "chat", "chrome": true}
```

- dict form: `tab` is the tab-URL substring (plus optional `gen` regex for video seats);
- string form: the string IS the tab substring;
- `true` form: tab substring defaults to the host.

Chat seats route to `ChromeReplayClient`; `modality=video` seats route to
`ChromeVideoClient`, which builds a generic `{"tab": ..., "kind": "ui"}` spec from the seat
file when no `VIDEO_HOSTS` entry exists. The static registries (`CHROME_CLIENTS`,
`VIDEO_HOSTS`) remain a CONVENIENCE for legacy seats, not a gate on new ones.

### How hot-reload works (session_pool.py + session_pool_shim.py)

- `SessionPool.rescan()` re-globs the secrets dir under the pool lock. New files become live
  sessions; vanished files are dropped; changed files (mtime moved) are re-parsed while
  carrying runtime state (last_used / cooldown_until / dead) across; UNTOUCHED sessions keep
  the exact same object (including any instantiated client), so a rescan never disturbs
  in-flight load spreading.
- The shim does ONE cheap `os.stat` of the secrets dir per request (mtime_ns + ctime_ns
  signature) and only calls `rescan()` when the directory actually changed — double-checked
  under a lock so concurrent requests rescan once. This mirrors the already-proven
  `_tenant_map()` per-request read pattern.

### One shim, one port (bug fixed in #1112)

`http.server` sets `allow_reuse_address=True` (SO_REUSEADDR), which on Windows lets a SECOND
process bind the same port — the OS then hands incoming connections to EITHER listener. Four
shim instances (two stale-code) were found sharing :8190, making requests land on a random
instance. The shim now uses `ExclusiveThreadingHTTPServer` with `allow_reuse_address=False`:
a duplicate start fails loudly at bind time, guaranteeing exactly one shim owns the port and
the keepalive task's "is it answering?" guard stays honest.

### Proven (not asserted)

- Offline: 28-check suite against a temp secrets dir — hot-add chat + video via inline decl,
  BOM'd files, no-op second rescan, object identity + runtime-state preservation, changed-file
  re-parse with state carry-over, removal, no registry regression. ALL PASS.
- Live on :8190 with NO restart between steps: drop seat file → host appears in `/v1/models`
  (50→51); delete → host gone (51→50); re-drop → back; `POST /v1/rescan` returns clean diff;
  targeted chat call routes through ChromeReplayClient with the seat-file tab substring and
  fails over cleanly with NO_TAB (no tab open, no credits spent).

---

## 25. Consumer-contract hardening — the OiiOii live E2E fixes (worklog #1134, 2026-08-28)

The film kit (OiiOii/Codex) consumes `:8190` for real. Its first live E2E run exposed four
contract violations that a synthetic probe would never have caught. All four are fixed in the
shim + pool and deployed. The lesson: **the consumer's exact call shape is the spec — test
against it, not against a convenient approximation.**

### Fix 1 — JSON-intent requests must never be polluted
OiiOii asks the chat pool for structured output (JSON). A seat that wraps the answer in prose
or markdown fences breaks the consumer's parser. The shim now detects JSON intent
(`_wants_strict_json(req)` via `_JSON_INTENT_RE`) and passes `strict_json=True` into
`session_pool.chat()`. The pool then **fails over any seat that violates the JSON contract**
(`is_strict_json(text)` check) instead of returning prose where JSON was promised.

### Fix 2 — Video submit answers 202 with an immediate durable receipt
The old path blocked the HTTP connection for the whole render. Now the shim creates the
durable job record **first** (idempotent by the consumer's `job_key`), answers **202 with the
receipt immediately**, and renders in a worker thread. The connection is never held by the
render. `VIDEO_EST_SECONDS = 300` sets the ETA in the receipt.

### Fix 3 — Idempotent job lookup & reconciliation
A replayed `job_key` returns the **same** record with 200 and never spends twice. Lookup
surface: `GET /v1/video/jobs/{job_id}` (status by durable id), `GET /v1/video/jobs?job_key=<key>`
(reconciliation by the consumer's durable key), `GET /v1/video/jobs` (full ledger, operator).
Backed by `VideoJobStore` (`video_job_store.py`) — thread-safe, atomic writes, persisted at
`state/video_jobs_8190.json`.

### Fix 4 — Cancellation
`DELETE /v1/video/jobs/{job_id}` cancels a pending job and records it in the ledger.

### The spend gate
`OMNI_VIDEO_CONFIRM_SPEND=1` is set in `session_pool_shim_task.bat` before any credit-spending
video submit. This is the explicit operator consent for spending free-tier credits — it lives
in the bat (the shim's single owner), not scattered across callers.

### Deployment mechanics (why no restart was needed for seat flips, but was for these)
Seat add/remove hot-reloads per request (§24) with NO restart. These four fixes are **code**
changes to the shim/pool, so they required a shim restart to take effect — done by letting the
owning bat task relaunch it. Do not confuse the two: data (seat files) hot-reloads; code
(shim/pool `.py`) needs a relaunch.

---

*Living document — appended as work proceeds. Last updated 2026-08-28 (worklog #1134: §1
consumer endpoint, §9a video face closed, §11 video_job_store, §20 live model count, §21
.vbs wrappers + single-owner + detached launch, §22 recovery chain ownership, §25
consumer-contract hardening).*

