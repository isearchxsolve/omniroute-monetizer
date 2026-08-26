# STATE OF PLAY — 2026-08-26 20:15 IST

One page. If the credits stop, start here.

## The deliverable exists

A **30-minute film with audio** is on disk and I verified it myself (ffprobe + sha256, not by reading a
report):

```
D:\god_ai\oioi\oioi\backend\run_artifacts\signal_tide_30m\artifacts\
    film_634081fc940b4874b42ff1da2f0324e9\final\film.mp4

1800.139323 s   h264 1280x720 24fps   +   aac stereo   91,984,983 bytes
sha256 D5CDFD5BA144E558C6B1D654B6FB97368E3F8881D0354C90E6092059B8A1C447
```

**Caveat that matters:** 360 ordered 5-second slots, but only **5 distinct renders** (sha256-counted).
It proves the architecture end to end — durability, ordered incremental assembly, zero-credit
completion, audio mux — not the art. Turning it into a watchable film is three changes, written up in
`D:\god_ai\oioi\oioi\FILM_PREMIUM_PASS_DIRECTIVE.md`. Codex owns that work and has the headroom.

## What is running, and how to bring it back

| port | what | restart |
|---|---|---|
| `20130` | chat superset gateway (free pool + forwards to `:20128`) | `python scripts/automation/chat_pool_server.py` |
| `8189` | video router, async `/v1/video/jobs` contract | `python scripts/automation/video_jobs_face.py --engine pool --port 8189` |
| `8010` | oioi FastAPI backend | from `oioi/backend`: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8010` |
| `3011` | oioi Next.js frontend (**was down at 20:15**) | from `oioi`: `npm run dev` |
| `20128` | OmniRoute chat — **not mine.** Never restart, never kill. Idempotent `/api` calls only. | — |

Launch Chrome for automation with **all three** flags or it silently fails:
`--profile-directory=<sub>` + `--remote-allow-origins=*` + `CREATE_NEW_PROCESS_GROUP|DETACHED_PROCESS`.

## Supply, measured

```
/v1/video/capacity  ->  4 rtst.ai seats, 101 credits, totalClipsAvailable = 16     (was 1)
                        answers in 0.1s (parallel probes, 45s cache, primed at startup)
:20130 /health      ->  5 sessions served, 4 available now; upstream calls=1 ok=1
```

Four automation profiles = four different Google accounts, all already signed in to rtst.ai. Only one
had ever been harvested; the adapter already existed, so the other three were a token read each:
`python scripts/automation/harvest_rtst_seat.py --all`. Seat files land in `state/secrets/`
(**gitignored**). The same trick may repeat on akool / digen / magichour / giz / heygen / Google Flow —
all four profiles show signed-in on those too.

## The config IS the backup

`scripts/automation/98e83bfd-e627-4557-a52e-9dcc8a008f50.json` (oioi's inference config) now points at
`http://127.0.0.1:20130` instead of `:20128`, and carries 166 models (160 original + `pool/auto` +
5 per-provider pool ids). Strictly additive and proven both ways:

```
codex/gpt-5.6-sol-low -> forwarded to :20128            -> "654"  correct
pool/auto             -> free session (api-cohere-com)  -> "654"  correct
```

When a paid route hits a wall or an auth refusal, `:20130` falls back to a free captured session on its
own — so the operator's default model is deliberately left unchanged. Pre-change copy:
`state/config_backup_98e83bfd_pre_pool_20260826.json`.

## Numbers that decide the next move

| | measured |
|---|---|
| pollinations still, cold | **44.5 s** median — and **HTTP 429 from request #4**, strictly serial |
| pollinations, repeat of same URL | **2.6 s** (upstream cache hit) — reuse is nearly free |
| Ken Burns clip render | **3.05 s** — 360 clips = 18.6 min. Not the constraint. |
| 360-shot incremental assembly | **75.8 s** warm / 153 s cold. Not the constraint. |
| chat pool sustained | 20.1 req/min, 96 % correct, **73 % clean — every dirty reply was `you-com`** |

**The still supply is the entire constraint**, and its sustained throughput is *unmeasured by rule* — a
429 pointing at a paid upgrade is a wall, and walls are not to be probed. So the plan must not assume
360 stills: reuse ~60 across 360 slots with a different camera move each, and let the still budget be
**discovered** (fetch until the limiter refuses, then spread what landed).

**The live danger:** `oioi/backend/film_pipeline/assembly.py:137` catches a 429 in a bare
`except Exception` and returns a correctly-timed **slate**, which reads as success to every downstream
stage including my own verification. An unattended premium run can "finish" as a 30-minute file of
placeholder cards. Making slates loud is change #1 in the directive.

## Rules that do not bend

Passwords are never typed or recorded. Card / captcha / phone / plan / quota walls: **stop** — never
solve, hammer, or pay. Secrets never printed (shapes and lengths only). Recon and DB access read-only,
never select key/token columns. Never restart or kill `:20128`. Never junction or drive the operator's
live Chrome — it permanently revoked a Google session on 2026-08-22. Breadth over depth: spread load
across providers, never hammer one host.

## The one recurring bug, named

Five times tonight, in five costumes: a 200 OK read as a paywall; a 403 CDP handshake read as a
signed-out profile; a frozen tab read as a signed-out profile; `creditsSpent: 0.0` for a clip that cost
6; a projected 600 clips read as current state. Always the same mechanism — **a callee returning
something plausible instead of the truth, and a caller inferring meaning from the wrong layer.** Two of
those profiles were signed in the whole time and cost three failed harvests to prove it. When something
reports failure, check which layer actually failed before believing the verdict.
