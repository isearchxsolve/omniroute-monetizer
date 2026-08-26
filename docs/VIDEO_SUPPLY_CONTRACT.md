# Video Supply Contract — v1.1

_The wire between the film kit (`D:\god_ai\oioi\oioi`, consumer) and the video supply router
(`D:\omniroute-monetizer`, producer). Frozen 2026-08-26 so both sides could be built in parallel;
amended the same day from the consumer's implementation report._

**Base URL:** `http://127.0.0.1:8189`
**Rule:** this file is the only agreement. Neither side reads the other's source. The consumer built
against a local mock of this contract and passed 5 tests; the producer implements to match.

## Why the split exists

The consumer knows what a film needs: how many clips, in what order, with which characters, at what
cost ceiling. The producer knows where clips come from: which free accounts still hold credits, which
browser sessions still replay, which provider is walled today. Neither can be expressed in the other's
terms, and every past attempt to merge them produced a layer that knew both and could ship neither.

## Endpoints

### `POST /v1/video/jobs`

```jsonc
{
  "jobKey":          "sha256:...",   // REQUIRED. Idempotency key, caller-computed, stable.
  "prompt":          "...",
  "durationSeconds": 5,              // 5 is the only verified value today
  "imageRefs":       ["asset_7f2a..."],  // 0..n asset ids from POST /v1/video/assets
  "seed":            1234,           // optional
  "seatHint":        "digen-seat-04" // NEW in v1.1, optional. See "Seat visibility".
}
```

`202` on accept, `200` on a repeat of a `jobKey` already known (the existing job is returned, no
render starts). `503` with `{"error":"no_capacity","retryAfterSeconds":N}` when no seat can take it.

The idempotency key is the load-bearing part. Supply here is *free accounts with a credit balance*,
so a duplicate submit is not a wasted millisecond, it is a permanently spent credit out of a pool of
~120 per account. The key is computed by the caller from normalized prompt + duration + sorted image
refs + seed + canonical shot index, and the router treats it as authoritative.

### `GET /v1/video/jobs/{id}`

```jsonc
{
  "id": "...", "jobKey": "sha256:...",
  "state": "queued|running|done|failed",
  "provider": "digen",
  "seat": "digen-seat-04",           // NEW in v1.1. Which account actually rendered it.
  "clipUrl": "http://127.0.0.1:8189/media/....mp4",   // when done
  "costCredits": 30,                 // observed, not estimated, once known
  "error": "wall:card_required" | "auth:session_dead" | "transient:timeout"
}
```

The `error` prefix is the contract, not the text after it. `wall:` and `auth:` are terminal on that
seat and must never be retried there. `transient:` may be retried with the same `jobKey`.

### `POST /v1/video/jobs/{id}/reassign`  — NEW in v1.1

Moves a `failed` job to a different seat while keeping its `jobKey` lineage. `409` if the job is not
failed; `503` if no other seat can take it. Returns the same shape as a submit.

This exists because v1.0 had a deadlock the consumer found: a stable `jobKey` correctly returns the
*old failed job* on repost, so a `wall:` failure on seat 4 could never be moved to seat 9 — the film
would park a shot forever rather than risk a double spend. Reassign is the only safe way out, and it
has to be server-side because only the router knows which seats are still solvent.

### `GET /v1/video/capacity`

```jsonc
{
  "providers": [
    {"provider":"digen","seats":12,"seatsAvailable":9,"clipsRemaining":36,
     "creditsPerClip":30,"maxConcurrentPerSeat":1}
  ],
  "clipsRemainingTotal": 36
}
```

`clipsRemaining` is the honest number: credits actually observed on live seats divided by cost per
clip. It is not a registry count. The registry has historically overstated capacity by ~6x.

### `DELETE /v1/video/jobs/{id}`

Cancels if not yet submitted to a provider; otherwise `409` and the job runs to completion. A clip
already being rendered has already cost its credits.

## Assets — the character image relay  — NEW in v1.1

A film has recurring characters. Every generator that accepts a reference image has its own upload
endpoint, its own id format, and its own per-account scoping. The consumer must not know any of that.

### `POST /v1/video/assets`

`multipart/form-data` with `file` and optional `label` (e.g. `"protagonist"`), or JSON
`{"label":"...","dataBase64":"...","mimeType":"image/png"}`. Returns:

```jsonc
{ "assetId": "asset_7f2a...", "label": "protagonist", "bytes": 184320, "sha256": "..." }
```

`assetId` is content-addressed: uploading the same bytes twice returns the same id and stores one
copy. The consumer uploads each character **once per film** and thereafter passes `assetId` values in
`imageRefs`.

### `GET /v1/video/assets`

Lists `{assetId, label, bytes, providerBindings:[{provider, seat, remoteId, boundAt}]}`.

`providerBindings` is the whole trick and the reason this is a router concern. The router does **not**
upload an asset to every provider up front — most would never be used, and each upload consumes a
request against a free account. Instead, on the first job that names `asset_X` on provider `P` seat
`S`, the router uploads the bytes into that seat's image slot over the replay harness, records
`(asset_X, P, S) -> remoteId`, and reuses `remoteId` for every later job on that seat. Lazy, cached,
and per-seat because a remote upload id is scoped to the account that made it.

A seat that cannot accept images at all is simply not admitted for jobs that carry `imageRefs`, and
`GET /v1/video/capacity` reports that per provider as `acceptsImageRefs: true|false`.

### `DELETE /v1/video/assets/{assetId}`

Removes local bytes and bindings. Does not attempt remote deletion — that would be a second write
against a free account for no benefit, and the remote copies expire with the accounts.

## Seat visibility — the v1.1 amendment

v1.0 returned `provider` but not `seat`, which the consumer correctly flagged: it could apply a
client-side seat cap but never verify the router honoured it, so its own accounting was unfalsifiable.
v1.1 returns `seat` on every job and accepts an optional `seatHint` on submit.

`seatHint` is advisory. The router may ignore it — the hinted seat may be walled, mid-render, or out
of credits, and the router is the only side that knows. The returned `seat` is authoritative and is
what the consumer should account against. A contract where the consumer could *pin* a seat would let
a client burn one account while eleven sat idle, which is the exact failure the breadth-not-depth rule
exists to prevent.

## What is deliberately not in this contract

- **No streaming.** Clips are polled. A 5-second clip takes tens of seconds to render; a held
  connection buys nothing and breaks on every Chrome restart.
- **No provider choice.** The consumer cannot request `digen` specifically. Supply is fungible by
  design; letting the caller pick would concentrate load on whichever provider is currently best and
  burn it first.
- **No price-per-second.** `creditsPerClip` is reported, but no per-second price exists to optimise
  against until longer clips are verified on a real provider.
- **No auth.** Loopback only. If this ever leaves localhost it needs a bearer token, and that is a
  contract change, not a config change.

## Status

| Side | State |
| --- | --- |
| Consumer (`backend/film_pipeline/`) | Built against a local mock of v1.0. 5 tests pass. No live call made. |
| Producer (`:8189` video pool) | **Not yet implemented.** Task 2. |
| v1.1 amendments (`seat`, `seatHint`, reassign, assets) | Specified here; both sides to implement. |

The first live proof is `--backend live --live --max-clips 3` — three clips, ~90 credits, one account.
Nothing larger runs until that returns three playable URLs.
