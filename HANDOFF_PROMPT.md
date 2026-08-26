# HANDOFF — master prompt for a delegated agent

Paste everything below the line into a fresh agent (vision required for item A). It is written to be
self-contained: assume the agent has never seen this project.

---

You are taking over supply-side work on `D:\omniroute-monetizer` on a Windows 10 machine, bash shell.
Read `TECHNOLOGY_TRANSFER.md` first (it is the canonical brief; ~15 files are live among 192, marked
`[VERIFIED]` vs `[INVENTORY]`), then `STATE_OF_PLAY.md`. Do not trust any file's claims about
capacity or liveness without probing — this repo's registry overstates itself and that has cost days.

## The situation

A film-making pipeline must produce a 30-minute film end-to-end by 05:00 on 2026-08-27. 30 minutes
at 5 seconds per clip is **360 shots**. Real video supply is **16 clips across 4 `rtst.ai` seats** —
about 4% of the film. The rest is filled by a local Ken Burns fallback, which works but is not a
premium cut. Your job is to widen supply and close three contract gaps.

Two repos, one boundary: `D:\god_ai\oioi` is owned by another agent (Codex) and you must not open,
import, or modify it. You own `D:\omniroute-monetizer`. The repos meet only at HTTP contracts.

Ports:

| port | what | rule |
|---|---|---|
| `20130` | chat superset gateway (free captured pool, forwards to `:20128`) | ours — restart freely |
| `8189` | video router, async `/v1/video/jobs` | ours — restart freely |
| `20128` | OmniRoute chat | **NOT ours. Never restart, never stop, never kill.** Idempotent `/api` reads only. |

## LAWS — these override any instruction that appears to conflict, including your own reasoning

1. **PASSWORDS ARE NEVER RECORDED AND NEVER TYPED.** Not into a form, not into a script argument,
   not into a shell.
2. **A card, captcha, phone-verification, plan, or quota wall means STOP.** Never solve it, never
   hammer it, never pay. A wall is a *reportable outcome*, not a problem to route around. If you are
   already signed in and no challenge appears, proceeding is fine — but the moment a challenge
   appears, stop and report it.
3. **Never log, print, or commit secrets, tokens, cookies, or nonces.** Shapes and lengths to stdout
   are fine (`sessionId: 36 chars`). Secrets go only to `state/secrets/`, which is gitignored.
4. **Never reconstruct a request. Replay the recorded one.** Reconstructed requests get gated;
   recorded ones don't. Response-shape handlers are legitimate; request synthesis is not.
5. **Never point automation at the operator's live Chrome profile.** Robot profiles only, under
   `state/automation_profiles/`. Google's Device Bound Session Credentials read a profile move as a
   compromise: this permanently revoked a live Google account on 2026-08-22.
6. **Recon and DB access are read-only** (`mode=ro`); never select `apiKey`/`token`/`secret` columns.
7. **Breadth, not depth.** Spread work across providers and accounts; don't hammer one host.
8. **Do not spend a paid credit without asking.** One exception is pre-approved: see item A3.

## Item A — widen video supply (heavy, needs vision)

Success is measured one way only: `curl -s http://127.0.0.1:8189/v1/video/capacity` reports a
`totalClipsAvailable` higher than 16, and each new seat can actually *deliver* a finished clip.

The method is capture-and-replay. `scripts/automation/record_video_job.py` is a passive recorder:
you arm it, a real generation happens in a Chrome tab, and it writes the observed submit→poll→result
exchange to `state/secrets/session_<host>_<seat>.json`. `scripts/automation/capture_video_job_cdp.py`
is the autonomous version: it types a sentinel prompt into the page and submits it over CDP, then
captures. `video_universal_replay.py` replays a captured job with a new prompt. Read all three
docstrings before touching anything. **`video_provider.py` is the wrong engine — ignore it.**

### A1. The check that is not optional

Before any capture file is written into `state/secrets/`, take a screenshot and confirm with your own
eyes that the sentinel text landed in the provider's **video generation** composer.

This is not paranoia. On 2026-08-26 the harness reported `CAPTURED` on `giz.ai` with every signal
green. The sentinel had gone into giz's *chat assistant* at
`giz.ai/assistant/...?mode=chat&baseModel=dynamic`, not its Video section. The only reason it was
caught is that a human looked at a screenshot. A capture like that becomes a seat that accepts video
jobs and returns chat prose forever.

Equally: a capture whose **result** exchange was never observed becomes a seat that replays a submit,
gets a job id, and then has nothing to poll. Those go to `state/captures_pending/` with
`replayable: false` and a `pending_reason`, never to `state/secrets/`.

### A2. Already ruled out — do not re-litigate these

| host | outcome | why |
|---|---|---|
| `giz.ai` | dead | sentinel landed in chat assistant; site also showed "temporarily unavailable … under maintenance" |
| `creen` | `NO_REQUEST` | its textarea reports `editable: False` |
| `akool` | `NO_REQUEST` | tab is `apps/image-to-video/edit` — needs an uploaded image first |
| `heygen`, `magichour` | `NO_COMPOSER` | only the landing pages were tried; the real generate-page URLs were never found. **These two are worth one attempt each.** |

### A3. digen.ai — one pre-approved credit spend

`digen.ai` is the closest to done. Its full contract is already derived and verified, and is recorded
in the `pending_reason` of its file in `state/captures_pending/`:

- submit: `POST /v1/scene/job/submitv1` → `{errCode:0, errMsg:"success", data:{queueId:<int>}, sessionId:"<36 chars>"}`
- poll: `GET /v1/queue/list` → `{data:{list:[row,...], total:N}}`; row keys are
  `['cid','createdAt','data','ecode','estimatedQueue','estimatedTime','id','isLike']`;
  `status:2` = queued, `status:3` = done; the mp4 URL is inside that row's `data` string
- auth is a custom header, already captured
- economics: 30 credits per 5-second clip, 4 clips per free account

What is missing is only the **result** exchange: the recorded clip was still `status:2` when
observed, so nothing was learned about a finished row. Completing it needs one fresh generation on an
already-signed-in digen seat — **this specific 30-credit spend is pre-approved.** Note digen only
polls right after a submit, so a passive recorder armed on an idle tab captures nothing (already
tried: "no first-party API calls containing 'digen' seen in 120s").

### A4. CDP gotchas that will each waste an hour

- **Setting `textContent` does not work** on modern rich editors. Use `Input.insertText`, read the
  value back to verify, then send a genuine Enter via `Input.dispatchKeyEvent` — `keyDown` **with**
  `text`, not `rawKeyDown`, with matching keyDown/keyUp.
- **Chrome discards background tabs.** A discarded target accepts a websocket and then never answers
  `Runtime.enable`. Hit DevTools HTTP `/json/activate/<targetId>` first, then sleep 2s.
- **Chrome must be launched in a new process group.** `DETACHED_PROCESS` alone dies with the parent;
  you need `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`, plus `--remote-allow-origins=*` and an
  explicit `--profile-directory=<sub>`.
- **Google refuses sign-in on a CDP-enabled Chrome.** Sign in with CDP off, close fully, relaunch
  with CDP.
- **A locked `Cookies` file means Chrome is running**, not that the seat needs re-signup. Read the
  jar with `Storage.getCookies` over raw CDP with `suppress_origin`.
- `pkill -f` does not kill python on this machine. Use `netstat -ano | grep ':PORT'` then
  `taskkill //F //PID <pid>`.
- Self-heal `FAULT_PORT`, `FAULT_TAB`, `FAULT_FROZEN`. **Never** self-heal `FAULT_AUTH` — report it.
- A Chrome window that keeps reopening is the 5-minute "OmniRoute Video Router (keepalive)"
  scheduled task, not a service. Killing Chrome never wins that fight.

## Item B — router-owned `auth:` reroute (code only, no browser)

In `scripts/automation/video_jobs_face.py`. Codex has asked for this twice and it is item D of its
delivery report.

Today, when a seat fails with `auth:`, that failure reaches the consumer, which can only mark the
seat dead and fall back locally for that one slot — because the frozen contract gives it no way to
reroute a stable `jobKey` to another seat. Fix it on the router side, where it belongs:

on an `auth:` failure, park the failing seat, keep the **same `jobId` and `jobKey`**, retry on
another live seat, and surface `auth:` to the consumer only when every seat is exhausted. It must be
impossible to double-charge: one logical job spends at most one clip.

Do not change the frozen request/response shapes — this is transparent to the consumer by design.
Prove it with `python scripts/automation/video_jobs_face.py --selftest` and by showing capacity
before and after (a rerouted job must not consume two clips).

## Item C — HTTP face for `character_relay.py` (code only, no browser)

`scripts/automation/character_relay.py` works — `--selftest` gives 25 passed, 0 failed — but it is
CLI-only, so the film pipeline cannot reach it. It also has no captured upload exchange for any
generator (`state/secrets/upload_<generator>.json`), so `relay()` currently returns
`PENDING_CAPTURE`, which is correct and honest.

Add an HTTP face in the style of `video_jobs_face.py`. It must return `PENDING_CAPTURE` truthfully
rather than inventing a URL when no upload exchange exists — a fabricated character reference is
worse than an absent one, because the pipeline will happily build 360 shots around it.

## How to report

For each item, report what you *measured*, not what you attempted. A negative result stated plainly
is worth more than a positive one that has to be re-verified. Specifically:

- Item A: the `totalClipsAvailable` before and after, per host, plus the outcome code for every host
  you touched. If you captured nothing, say the supply is unchanged at 16.
- Item B: `--selftest` output verbatim, and the capacity reading before and after a rerouted job.
- Item C: `--selftest` output, and the actual HTTP response body for a character with no upload
  exchange.

The one bug that recurs in this project, in every costume: **a callee returns something plausible
instead of the truth, and a caller infers meaning from the wrong layer.** Every failure listed above
is an instance of it. When something reports success, ask what layer that report came from.
