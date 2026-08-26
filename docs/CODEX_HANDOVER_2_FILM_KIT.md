# Codex handover #2 — film kit: characters, upload relay, and the studio kit

_Paste this into the `Build film consumption pipeline` thread when the current deep-dive audit
finishes. It builds directly on what you already shipped (`backend/film_pipeline/`, 5 tests passing)._

---

## Read this first

Your report was accepted in full, including both of its frozen-contract objections. They were right,
and the contract has been amended rather than defended. The contract now lives in a file:

**`D:\omniroute-monetizer\docs\VIDEO_SUPPLY_CONTRACT.md`** — read it. It is the only agreement between
your layer and the supply router. Do not read any other file in `D:\omniroute-monetizer`, and do not
import, copy, or modify anything there. Everything you need is in that one document.

What changed in v1.1, all three because of your report or this task:

1. **`seat` is now returned** on `GET /v1/video/jobs/{id}`. Your seat accounting becomes auditable —
   compare the returned `seat` against what your scheduler assigned and log a divergence rather than
   trusting your own guess.
2. **`seatHint` is now accepted** on submit, advisory only. The router may ignore it and the returned
   `seat` wins. Do not treat a hint as a pin.
3. **`POST /v1/video/jobs/{id}/reassign`** exists, and it closes the deadlock you identified: a stable
   `jobKey` correctly returns the old failed job on repost, so a `wall:` failure could never move to
   another seat and your build parked it forever. Reassign keeps the `jobKey` lineage and is
   server-side because only the router knows which seats are still solvent. Wire `parked_wall` →
   reassign-once → only then park permanently.
4. **Assets exist** — `POST /v1/video/assets` and friends. That is the subject of task A below.

The supply router side of v1.1 is **not yet implemented**; it is being built now, to this contract.
Keep mock-first. Your `--backend live --live --max-clips N` gate stays exactly as it is.

---

## Task A — the character upload relay (the priority)

A film has recurring characters. The operator uploads a character's image **once** into the film kit,
and every generated shot containing that character must carry that same reference so the character
looks like themselves in shot 1 and shot 2,159.

Your side of it:

- A **character registry** per film: `{characterId, name, description, imageAssetIds[], createdAt}`,
  durable in the same SQLite graph, with the film's continuity bible referencing `characterId` rather
  than re-describing the face in prose every time.
- **Upload endpoint** on your API: accept an image file, hand the bytes to
  `POST /v1/video/assets` on the router, store the returned content-addressed `assetId`. The router
  deduplicates by content hash, so re-uploading the same file is free and idempotent — you do not need
  your own dedup, but you do need to store the mapping.
- **Shot planning must resolve characters to `imageRefs`.** When the planner decides shot 412 contains
  the protagonist and the mentor, shot 412's job carries both of their `assetId` values in
  `imageRefs`, in **sorted order** — sorted because `imageRefs` is part of the `jobKey` and an
  unstable order would silently break your idempotency and double-spend credits.
- **Capacity gating.** `GET /v1/video/capacity` now reports `acceptsImageRefs` per provider. A film
  whose shots all carry characters can only use providers where that is `true`; admission must compute
  capacity from those providers only, and refuse with a numerical shortfall as it already does.
- What you must **not** build: any per-generator upload logic. You never learn that digen wants
  multipart and some other engine wants base64, or that an upload id is scoped to one account. The
  router uploads lazily on first use per seat and caches the binding. That asymmetry is deliberate.

Mock parity: extend `mock.py` with the asset routes, content-addressed ids, an `acceptsImageRefs:
false` provider so the gating path is actually exercised, and a failure injection for "asset not bound
on this seat".

## Task B — the studio kit, driven by your own audit

Your audit is expanding this into a studio-operating-model review — development/greenlight,
story/editing, casting/continuity, preproduction, production, editorial, sound/music,
finishing/delivery, audience ownership, control-room economics. Good. Turn the findings into the kit,
with two constraints:

- **Anything that costs a render is gated.** Casting looks, style tests, and continuity checks are all
  temptingly cheap to express and ruinously expensive to run — 30 credits each, four per free account.
  Any kit feature that can trigger generation must route through the same admission + cap path as a
  shot, and must be visible in the film's projected-cost summary before it runs.
- **Editorial must not require regeneration.** Reordering, trimming, and re-cutting have to work on
  clips already in hand. Your incremental assembler with fixed contiguous segments is the right shape;
  make sure an edit that changes shot order invalidates only the segments it touches, not the film.

Where the audit finds a competing product stack or a second generation path that bypasses the durable
graph, say so plainly in the report and recommend which one dies. Two generation paths with different
safety guarantees is how a "mock only" run spends real credits.

## Task C — close your own two open items

- The recovery test simulates worker loss with the mock alive in-process. Add one test where the
  **store is reopened from disk by a fresh connection** mid-film and the tick resumes with zero
  duplicate `jobKey` submissions. That is the property that matters and it is testable without a real
  `kill -9`.
- The 900-canonical-generation row in your cost table is a target scenario, and you labelled it as one.
  Now make it measurable: emit `uniqueGenerations / logicalShots` as a real counter on the film
  summary, so the dedup ratio is observed per film instead of projected.

---

## Rules that do not change

- Mock is the default. No live call without `--backend live --live --max-clips N`.
- Never solve, pay, or hammer a captcha, card wall, phone verification, or plan/quota wall. Hitting one
  is a **correct, reportable outcome** — park it and say so.
- Never log or print secrets, tokens, or cookies.
- Do not read or modify `D:\omniroute-monetizer`. `docs\VIDEO_SUPPLY_CONTRACT.md` is the exception and
  is read-only.
- Report what you did not verify, as clearly as you did last time. That section was the most valuable
  part of your report.

## Deliverable

Update `docs/FILM_PIPELINE_REPORT.md` with a new dated section: what you built, what you measured,
what you did not verify, and any further contract objections. Contract objections have been acted on
once already — raise them.
