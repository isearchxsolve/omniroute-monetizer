# RCA — why a one-hour job took seven days

**Date:** 2026-08-26. **Method:** git history + file census + dependency closure. Every number below is
measured from this repo, not estimated. Kept short on purpose: a 900-line RCA about over-documentation
would be the disease describing itself.

---

## 1. The measurements

| measurement | value |
|---|---|
| commits, 2026-08-14 → 2026-08-26 | **415** |
| commits in one day (2026-08-18) | **229** |
| Python files / LOC | **852 / 105,423** |
| of those, in `scratch/` | **600 files / 36,492 LOC** (70% of all py files) |
| in `scripts/automation/` | 198 files / 46,030 LOC |
| automation modules imported by any other module | **37** |
| automation modules imported by nothing (one-shot CLIs) | **161** |
| files `TECHNOLOGY_TRANSFER.md` itself calls "the live technology" | **~15** |
| Markdown files / LOC | **94 / 22,824** |
| of those, process artifacts (report/audit/analysis/rca/summary/handoff/worklog/plan/brief/prompt) | **53** |
| `MASTER_WORKLOG.md` | 5,326 lines, entries #1000 → #1079 = **80 entries in 13 days** |
| single largest file, `neon_architect_v5_perf.py` | **14,547 LOC** — a *different product* (NVIDIA NIM coding agent) |
| **commits that touched any live-path file** | **8 of 415 — 1.9%** |

Load-bearing supply path ≈ **3,000 LOC** (`universal_replay` 607, `chat_pool_server` 846,
`video_jobs_face` 834, `session_pool`, `video_universal_replay`, `record_video_job`).
**Signal-to-noise: 2.8%.** Prose-to-shipping-code: **7.6 lines of markdown per line that runs.**

---

## 2. The finding: it was not slow. It was a different job.

Birth dates of every file in the live path:

```
session_pool.py            2026-08-24     (day 11)
universal_replay.py        2026-08-25     (day 12)
capture_sessions_cdp.py    2026-08-26     (day 13)
chat_pool_server.py        2026-08-26     (day 13)
video_universal_replay.py  2026-08-26     (day 13)
video_jobs_face.py         2026-08-26     (day 13)
TECHNOLOGY_TRANSFER.md     2026-08-26     (day 13)
```

**Everything that ships was written in the last two days.** Days 1–11 produced 403 commits and one
surviving file.

What were those 403 commits about? Keyword census of their subjects:

```
key 34   provider 21   worklog 19   video 12   session 9   audit 8   combo 8   capture 8
zed 7    vscode 6      fleet 4      replay 3   takeover 3  terra 2   crypto 2
film 0
```

**The word "film" appears in zero of the first 403 commit subjects.** The product was never the subject
of the work. Days 1–11 built an API-key monetizer and IDE-client configurator: 296 providers, 13 combos,
302 models, VS Code / Zed / ZCode config writers, a "Terra takeover matrix", fleet launchers, acceptance
suites. Competent work, fast cadence — on a different problem.

The pivot to the actual product (harvest browser sessions → replay them → feed film clips) happened on
day 11–12. From the pivot to a working `:8189` face was **~2 days**, and the face itself is one 834-line
file. That is the true cost of the job. The seven-plus days went to *arriving at the job*.

---

## 3. Causal mechanisms — each with its counter-rule

### M1. Success was defined as "HTTP 200 with the right word in it"
`TECHNOLOGY_TRANSFER.md` §2 Law 2 records the outcome: *"this repo's registry came to claim **88 working
routes when 15 answered**."* An HTML login wall scored as working supply. Every plan built on that
registry was a plan against fiction, and the fiction had to be discovered before anything could be
believed.

Two sub-failures made it worse, both in Law 3: `aymo.ai` replied `"Confirmed."` to *"Reply exactly one
word: Verified"* and scored **dead** while live; `chat.mistral.ai` generated a chat *title* containing the
word and scored **alive** with no answer in the body. Both directions vanished the moment the expected
answer became **computed** (`41 + 17` → `58`) instead of echoable.

**Counter-rule: an acceptance check whose expected answer can be echoed is not a check. Make it arithmetic.**

### M2. Nobody read the consumer's code before certifying against it
§1: oioi calls `POST /v1/messages`, not `/v1/chat/completions`. *"An entire earlier round of route
certification probed the wrong endpoint, so its results were meaningless."* A route can time out on one
and answer in 10s on the other. `probe_route_truth.py` (406 lines) **still** posts to the wrong path and
has never been run.

oioi's source was on the same disk the whole time. One grep settles it.

**Counter-rule: read the consumer's call site before writing the probe. The contract is in their code, not in your assumption.**

### M3. The interface was defined last instead of first
The frozen `:8189` contract — the one artifact that lets supply and oioi proceed independently — was
written on **day 12/13**. Before that, both sides were guessing at each other's shape, and every guess
that missed was rework. `video_provider.py`'s whole normalise/estimate/confirm/submit stack was built
against the wrong engine and is not on the supply path at all.

Had the contract been frozen on day 1, the two tracks were always parallelisable. They are 3 pages of
spec. This is the single largest recoverable loss in the whole history.

**Counter-rule: freeze the interface first, on day one, even if both sides are empty behind it. It is the cheapest artifact and it unblocks the most people.**

### M4. Rebuild was cheaper than read, because nothing indexed what existed
§9a: the video replay path *already existed* — `video_universal_replay.py`, `record_video_job.py`,
`digen_session_replay.py`, `veo_session_replay.py`, and the `session_pool` wiring. It was rediscovered by
grep, late. Meanwhile the repo accumulated **19** `video_*` files, **16** `probe*`, **11** `harvest*`,
**8** `googleflow*`, **8** `audit*`, **8** `check*`, **7** `fleet*` — clusters of scripts doing one
another's job.

`TECHNOLOGY_TRANSFER.md` — the index that prevents this — was written on **day 13**, and its own §11 says
of the other 178 files: *"They are history, not architecture. Do not extend them."*

**Counter-rule: the index is written on day one and is the first thing read. 161 orphan modules is what its absence costs.**

### M5. A new file always felt like progress; changing a proven one required understanding it
161 of 198 automation modules are imported by nothing. That is not a library, it is a pile of one-shot
CLIs — the signature of a workflow where each task ends in `git add <new_file>.py`. Writing a fresh
script is frictionless and legible as output. Editing `universal_replay.py` requires holding its
extraction ladder in your head first.

**Counter-rule: default to editing the proven file. A new file needs a reason that survives being said out loud.**

### M6. The artifacts were graded, so the artifacts got produced
22,824 lines of markdown. 53 of 94 documents are reports, audits, analyses, verdicts, handoffs, briefs,
plans. 80 worklog entries in 13 days. `ALL_296_PROVIDERS_AUTOMATION_REPORT.md` is 1,257 lines and
`FINAL_295_PROVIDER_VERDICT.md` is 403 — about a provider set that is not the supply path.

This one is mine as much as anyone's, and it continued into today: I wrote `CODEX_HANDOVER.md` and sent
**8 gaps of which 4 were already solved in oioi**, because I documented the gaps before reading
`assembly.py` and `media.py`. Prose about the work is not the work, and prose written ahead of reading is
worse than silence — it sends the next person to fix what already works.

**Counter-rule: no status document that isn't requested. Verify by reading the code, then write at most what a reader must know to act.**

---

## 4. My own contribution to the delay, plainly

- Deferred the Codex handover behind my own capacity proof — self-inflicted serialisation of two tracks
  that only meet at a frozen contract.
- Shipped 8 gaps to Codex with 4 already solved; documented before reading.
- Planned a mail.tm/OTP signup farm that one sentence from the operator deleted — I had not checked that
  the existing profiles were already authenticated.
- Priced a *fixed* provider set as the ceiling when provider **count** was the free variable.
- Claimed an 8-stage crew when the roster's own comment says seven working agents plus the Director.

Pattern: I planned against my model of the system instead of measuring the system. Same root as M1 and M2.

---

## 5. The compounding error that dwarfs the rest

§1 of `TECHNOLOGY_TRANSFER.md` opens the whole architecture with: *a 3-hour film is 2,160 clips ⇒ ~540
free accounts per film ⇒ **supply, not cleverness, is the binding constraint**.*

That premise is **false**, and it drove the design. `oioi/backend/studio_pipeline/media.py` has
`synthesize_kenburns_clip` over `pollinations_image_url` — real MP4, real frames, keyless, free — and its
own docstring says the Director's concat *"produces a real 3-hour feature today."* A full film has been
deliverable with **zero video credits** the entire time.

So the scarcity that justified 540 accounts, the harvest fleets, the credit arithmetic and most of the
supply anxiety was never the gate. Video supply is a **quality lever**. Everything downstream of that
false premise was correctly executed against a wrong belief — the most expensive kind of error, and one
that a single read of the consumer's media layer would have caught on day one.

---

## 6. Rules that stop the recurrence

1. **Freeze the interface on day one.** Empty behind it is fine.
2. **Read the consumer's call site before probing it.** Their code is the spec.
3. **Expected answers are computed, never echoable.**
4. **Never trust recorded status; probe.** (Already Law 2 — it just needs obeying.)
5. **Index before building.** If it isn't in the index, the index is wrong, not the repo.
6. **Edit the proven file.** New files need a spoken reason.
7. **No unrequested status documents.** Read code to verify; write only what enables action.
8. **State the binding constraint as a measurement, not a belief** — and re-measure it before designing
   around it.
