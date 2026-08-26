# MASTER PROMPT — harvest video supply at breadth

Supersedes `HANDOFF_PROMPT.md`. Paste everything below the line into a fresh agent with vision.

---

You are taking over supply-side work on `D:\omniroute-monetizer`. Windows 10, bash shell. Read
`TECHNOLOGY_TRANSFER.md` first — it is the canonical brief, and about 15 of 192 files are live, marked
`[VERIFIED]` vs `[INVENTORY]`. Then `STATE_OF_PLAY.md`. Never trust a file's claim about capacity or
liveness without probing it; this repo's registry overstates itself and that has already cost days.

## Mission

A film pipeline must deliver a 30-minute film end to end. At 5 seconds per clip that is **360 clips**.
Real video supply today is **16 clips across 4 `rtst.ai` seats** — about 4% of the film. Everything
else is filled by a local Ken Burns fallback, which completes the film but is not a premium cut.

Your job is to raise provider **count**. The arithmetic, from
`scripts/automation/discover_video_providers.py`:

```
providers  x  google_seats  x  free_clips_per_account  =  clips available
    19     x       4        x          ~4              =  ~300
```

Squeezing more credits out of `rtst.ai` cannot get there. Only breadth can. This is the single
highest-value task in the project.

## Two facts that make this possible, and one that makes it hard

**1. Google SSO is the whole trick.** A provider offering "Continue with Google" needs no email, no
OTP, no password, and shows no captcha to an already-signed-in aged profile — so onboarding is one
click and is automatable. A provider that demands email + password + verification is **skipped**, not
fought. The discovery pass already scored every candidate on exactly this.

**2. It is 19 captures, not 19 adapters.** You will read a warning in
`harvest_rtst_seat.py` that "breadth on 50 unwired providers costs 50 adapters." That is true only of
the hand-written API-client path (`rtst_api_client.py`). You are not using that path. You are using
capture-and-replay: `capture_video_job_cdp.py` records a genuine submit→poll→result exchange, and
`video_universal_replay.py` replays it with the prompt swapped. **One engine, N providers.** That
distinction is the entire reason this plan is affordable. Do not write per-provider adapters.

**3. The hard part is the capture, and it has a low observed success rate.** On 2026-08-26, four
candidates were attempted and zero produced a usable seat. Expect a conversion rate well under 100%
and plan for volume rather than for perfection on any one host. That is what the time box below is for.

## The queue — already discovered and ranked, do not re-derive it

`state/video_providers_discovered.json` holds 89 scored candidates from a read-only discovery pass run
2026-08-26 18:10: 48 alive video hosts, 34 with Google SSO. Filtering to SSO + video + alive + no wall
signal gives 26, of which these **19 have never been touched**. Work them in this order:

| score | host |
|---|---|
| 5 | `flyne.ai` `forvideo.ai` `genspark.ai` `gostudio.ai` `happyhorsevideo.com` `kensa.cc` `nemovideo.com` `openart.ai` `pixelbin.io` `seedance.tv` `veo3ai.io` `wavespeed.ai` `wireflow.ai` `heygen.com` `magichour.ai` |
| 3 | `app.klingai.com` `app.pixverse.ai` `atlascloud.ai` `pika.art` |

Re-score or widen the list with `python scripts/automation/discover_video_providers.py --no-search`
(read-only, spends nothing) if you exhaust it.

### Already ruled out — do not re-litigate

| host | outcome | why |
|---|---|---|
| `giz.ai` | dead | sentinel landed in its chat assistant, not its Video page; site also showed "temporarily unavailable … under maintenance" |
| `creen.ai` | `NO_REQUEST` | its textarea reports `editable: False` |
| `akool.com` | `NO_REQUEST` | tab is `apps/image-to-video/edit` — needs an uploaded image first |
| `veoaifree.com` | done, chat only | already harvested as chat supply, not video |
| `digen.ai` | partial | full contract captured, result exchange never observed — see the note below |

**`digen.ai` is one fresh generation away from working**, and that specific 30-credit spend is
**pre-approved**. Its contract is already derived and verified, recorded in the `pending_reason` of its
file in `state/captures_pending/`: submit `POST /v1/scene/job/submitv1` →
`{errCode:0, errMsg:"success", data:{queueId:<int>}, sessionId:"<36 chars>"}`; poll
`GET /v1/queue/list` → `{data:{list:[row,...], total:N}}` with row keys
`['cid','createdAt','data','ecode','estimatedQueue','estimatedTime','id','isLike']`, `status:2` =
queued, `status:3` = done, and the mp4 URL inside that row's `data` string. Auth is a custom header,
already captured. Only the finished-row shape is unknown. Note digen polls **only** right after a
submit, so arming a passive recorder on an idle tab captures nothing — that was already tried and
returned "no first-party API calls containing 'digen' seen in 120s".

## The per-provider loop — time-boxed, and the box is not advisory

**Budget 12 minutes per provider. When it expires, record the outcome code and move to the next
host.** Nineteen hosts at 12 minutes is under four hours; one host at ninety minutes is a failed
harvest. Depth on a stubborn provider is the failure mode here, and Law 7 exists for this reason.

For each host:

1. **Reach the generate page, not the landing page.** `heygen.com` and `magichour.ai` were previously
   scored `NO_COMPOSER` purely because only their landing pages were tried. Find the actual
   text-to-video composer URL.
2. **Sign in via Google SSO on an existing aged robot profile** under `state/automation_profiles/`.
   One click. If any challenge appears — captcha, phone, card, plan — **stop on that host** and record
   the outcome. Do not solve it.
3. **Trigger one generation over CDP** with `capture_video_job_cdp.py`, then capture submit → poll →
   **result**.
4. **Verify replayability before the file is trusted**, then confirm
   `curl -s http://127.0.0.1:8189/v1/video/capacity` reflects the new seat.

### The check that is not optional

**Before any capture file is written into `state/secrets/`, screenshot the page and confirm with your
own eyes that the sentinel text landed in the provider's video-generation composer.**

This is not paranoia. The `giz.ai` harness reported `CAPTURED` with every signal green. The sentinel
was in giz's chat assistant. The only reason it was caught is that a human looked at a screenshot. A
capture like that becomes a seat that accepts video jobs and returns chat prose forever — and it
inflates the capacity number, which is worse than having no seat at all, because the film pipeline
will plan around clips that will never arrive.

Same principle for the result exchange: **a capture whose result exchange was never observed is not a
seat.** It replays a submit, gets a job id, and has nothing to poll. Those belong in
`state/captures_pending/` with `replayable: false` and a `pending_reason` recording what you did learn.
Never hand-copy one into `state/secrets/` to raise the number.

## Ledger — one row per host, so nothing is attempted twice

Append every host you touch to `state/harvest_ledger.json`: host, outcome code, the URL you actually
used, elapsed seconds, and one sentence of evidence. A negative result recorded precisely is worth
more than a positive one that has to be re-verified.

Outcome codes: `CAPTURED` · `CAPTURED_NO_RESULT` · `DRY_RUN_OK` · `NO_REQUEST` · `NO_COMPOSER` ·
`WALL` · `WEBSOCKET` · `TEXT_REJECTED` · `FAULT_FROZEN` · `CDP_ERROR`.

## LAWS — these override any instruction that appears to conflict, including your own reasoning

1. **PASSWORDS ARE NEVER RECORDED AND NEVER TYPED.** Not into a form, not into a script argument, not
   into a shell. Google SSO on an already-signed-in profile is how you avoid ever needing one.
2. **A card, captcha, phone-verification, plan, or quota wall means STOP.** Never solve it, never
   hammer it, never pay. A wall is a *reportable outcome*, not an obstacle to route around. Dodging one
   by using a profile that is already signed in — so no challenge ever appears — is fine. The moment a
   challenge appears, stop on that host.
3. **Never log, print, or commit secrets, tokens, cookies, or nonces.** Shapes and lengths to stdout
   are fine (`sessionId: 36 chars`). Secrets go only to `state/secrets/`, which is gitignored.
4. **Never reconstruct a request. Replay the recorded one.** Reconstructed requests get gated;
   recorded ones do not. Response-shape handlers are legitimate; request synthesis is not.
5. **Never point automation at the operator's live Chrome profile.** Robot profiles only, under
   `state/automation_profiles/`. Google's Device Bound Session Credentials can read a profile move as a
   compromise: this permanently revoked a live Google account on 2026-08-22. Never junction or copy a
   live profile.
6. **Recon and DB access are read-only** (`mode=ro`); never select `apiKey` / `token` / `secret`
   columns.
7. **Breadth, not depth.** Spread work across hosts. Never hammer one.
8. **Do not spend a paid credit without asking.** The one pre-approved exception is the single digen
   generation described above.
9. **Never restart, stop, or kill `:20128`** — that is OmniRoute and it is not ours; idempotent `/api`
   reads only. `:20130` (chat gateway) and `:8189` (video router) are ours and may be restarted freely.

## CDP gotchas that will each cost an hour

- **Setting `textContent` does not work** on modern rich editors. Use `Input.insertText`, read the
  value back to verify, then send a genuine Enter via `Input.dispatchKeyEvent` — `keyDown` **with**
  `text`, not `rawKeyDown`, with matching keyDown/keyUp.
- **Chrome discards background tabs.** A discarded target accepts a websocket and then never answers
  `Runtime.enable`. Hit DevTools HTTP `/json/activate/<targetId>` first, then sleep 2s.
- **Chrome must launch in a new process group.** `DETACHED_PROCESS` alone dies with the parent; use
  `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`, plus `--remote-allow-origins=*` and an explicit
  `--profile-directory=<sub>`.
- **Google refuses sign-in on a CDP-enabled Chrome.** Sign in with CDP off, close Chrome fully, then
  relaunch with CDP.
- **A locked `Cookies` file means Chrome is running**, not that the seat needs re-signup. Read the jar
  with `Storage.getCookies` over raw CDP with `suppress_origin`.
- `pkill -f` does not kill python here. Use `netstat -ano | grep ':PORT'` then `taskkill //F //PID <pid>`.
- Self-heal `FAULT_PORT`, `FAULT_TAB`, `FAULT_FROZEN`. **Never** self-heal `FAULT_AUTH` — report it.
- A Chrome window that keeps reopening is the 5-minute "OmniRoute Video Router (keepalive)" scheduled
  task, not a service. Killing Chrome never wins that fight.

## Secondary items — only after the harvest, or if harvesting is blocked

**Item B — router-owned `auth:` reroute**, in `scripts/automation/video_jobs_face.py`. Code only, no
browser. When a seat fails with `auth:`, park that seat, keep the **same `jobId` and `jobKey`**, retry
on another live seat, and surface `auth:` to the consumer only when every seat is exhausted. One
logical job must spend at most one clip. Do not change the frozen request/response shapes. Prove it
with `--selftest` plus a capacity reading before and after a rerouted job.

**Item C — HTTP face for `character_relay.py`.** Code only. The module works (`--selftest`: 25 passed,
0 failed) but is CLI-only, so the pipeline cannot reach it, and it has no captured upload exchange, so
`relay()` correctly returns `PENDING_CAPTURE`. Add an HTTP face in the style of `video_jobs_face.py`
that returns `PENDING_CAPTURE` truthfully rather than inventing a URL — a fabricated character
reference is worse than an absent one, because the pipeline will build 360 shots around it.

## Definition of done

`curl -s http://127.0.0.1:8189/v1/video/capacity` reports a `totalClipsAvailable` **above 16**, every
seat behind that number has an observed **result** exchange, and `state/harvest_ledger.json` has one
row for every host in the queue — including the ones that failed.

Report what you **measured**, not what you attempted: capacity before and after, and the outcome code
for all 19 hosts. If you captured nothing, say the supply is unchanged at 16 clips. That sentence is a
useful result; a capacity number that cannot deliver is not.

The one bug that recurs in this project, in every costume: **a callee returns something plausible
instead of the truth, and a caller infers meaning from the wrong layer.** Every failure named in this
document is an instance of it. When something reports success, ask which layer that report came from.
