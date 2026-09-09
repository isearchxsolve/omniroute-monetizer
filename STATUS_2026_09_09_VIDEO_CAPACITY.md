# Video-lane capacity and expansion — 2026-09-09 09:22 IST

This is the current, evidence-bounded capacity report for the designated consumer endpoint:
`http://127.0.0.1:8190/v1`.

## Fresh capacity correction at 11:58 IST

A read-only `video_router.py accounts` pass against the dedicated automation seats found the
current balances to be Flow `0 / 15 / 0 / 15`, RTST `1`, and Digen `0`.  All four Flow project tabs
remain ready, but the proven Fast Flow route costs 20 credits **on one account**. Credits cannot be
pooled between accounts, so the 30 total Flow credits buy **zero** proven Fast clips at this moment;
all 30 are below the per-account floor. RTST's one credit is below its 6-credit cheapest proven
clip, and Digen's zero is below its 30-credit cheapest proven clip.

The capacity CLI previously summed account balances before dividing by a clip price, which
incorrectly displayed one Flow Fast clip for four isolated balances of 0/15/0/15. It now sums
whole purchasable clips per account and explicitly reports stranded below-floor credits. Regression
coverage prevents that false capacity claim. The older 330-credit Digen and 4-credit RTST figures
below are historical reads, not current supply.

Therefore the current measured, immediately spendable capacity for the proven Flow Fast, RTST, and
Digen routes is **zero clips**. LTX remains an unquantified MP4-proven route and is deliberately not
converted into a numeric promise. This correction does not alter the 33.3 / 53.3 minute recurring
Flow **planning ceilings** below; those remain entitlement assumptions, not the present balances.

## Fresh independent-provider check at 12:52 IST

The locally vaulted Kie, Novita, and AI Studio credentials were rechecked against their own
documented, non-generation endpoints. All three authenticate today. Kie's own credit endpoint
reported a current **7.74-credit** balance. That is not capacity: its previous bounded
`kling-3.0/video` submit was correctly refused for insufficient credits at 7.79 credits, with no
charge, so the slightly lower present balance still buys **zero proven clips**. The Kie Python
adapter remains technically ready for its documented submit -> task ID -> poll -> result-URL flow,
but it must not be counted or submitted until the wallet can cover a known model cost.

Novita's key was accepted, but no direct video request, funded-balance response, or MP4 proof has
been obtained; its two candidate routes remain candidates only. AI Studio's key was accepted and
can list Veo models, but the previous bounded `predictLongRunning` attempt returned Google
`RESOURCE_EXHAUSTED` (generation quota/billing wall), so it also contributes zero current clips.
Segmind's recheck hit a connection timeout rather than an authentication rejection: the stored key
is not disproven, but the provider is not ready to count until a later non-spending verification
returns. These checks involved no render submission or credit spend.

## What is live now

The task-owned shim is running `2026-09-09-session-heartbeat-v1`. Its health payload reports a
six-hour idle window and one stateless chat heartbeat at most every five minutes; the latest live
read showed **0 beats / 0 failures / 0 skipped-busy** (`no beat needed yet`). The heartbeat is
deliberately not a video generator: it never drives Chrome and never spends video credits.

The current local pool has **49 session artifacts**, of which **16 are dispatchable**:

| Lane | Dispatchable/admitted session files | Current evidence |
|---|---:|---|
| Chat | 11 | Exact-file Law-3 replay admissions |
| Video | 5 | Exact-file video admissions and consumer wiring |

The five admitted video files are: Digen (stateless API), RTST seat2 (stateless API), public LTX
Space (zero-auth API), and two Google Flow Chrome seats (both PRO, Chrome-backed). The two Flow
seats are proven by submit → poll → downloadable MP4 evidence; the Chrome tabs remain a runtime
dependency. `GET /v1/models` currently returns **439 rows / 438 unique IDs**, including the
`video/auto` alias and per-provider aliases. Catalog rows and unprobed candidates are explicitly
**not video capacity** until they have exact provider proof and a pinned consumer proof.

## Minutes per month: what can honestly be stated

There is no single measured current-minute number for the five seats. The providers expose different
quota units, and two seats are Chrome-backed. The following earlier reads are retained as historical
provenance only; the 11:58 IST correction above supersedes them for current capacity:

* Digen: 330 credits remaining at an earlier read, with the measured 30-credit/5-second contract —
  **11 clips = 55 seconds = 0.92 minutes** remaining.
* RTST seat2: 4 credits remaining at an earlier read; its cheapest proven option is 6 credits for
  a 3-second clip — **0 additional clips at that balance**.
* LTX public Space: an MP4 submit/poll/download proof exists, but no monthly quota was measured;
  it is not converted into a guaranteed monthly-minute number.
* Google Flow: two PRO accounts are admitted, but their balances were observed through dedicated
  Chrome UI snapshots rather than a current non-browser API. Their recorded proofs show 20 credits
  for an 8-second Fast generation and prior balances of 1,026 credits (P2 after proof) and a
  separate seat1 balance snapshot. These are historical snapshots, not a live balance guarantee.

For planning, the current official Google Flow help page documents **50 daily credits for every
account**, plus **1,000 monthly credits for Google AI Pro**; unused daily/monthly credits do not
roll over. It lists Veo 3.1 Fast at **20 credits per 4/6/8-second generation** for non-Ultra users.
On a 30-day month, that gives a *quota ceiling* of 2,500 credits / 125 eight-second Fast clips /
**16.7 minutes per Pro account**, if the account is actually entitled and used every day. Thus the
two already-proven Pro Flow accounts have a planning ceiling of about **33.3 minutes/month** from
the recurring Flow allocation, before subtracting any already-consumed balance. This is a planning
ceiling, not a current-balance assertion. The latest read-only UI balance across all four Flow tabs
is **30 credits (0 + 15 + 0 + 15)**; it is not a monthly quota measurement and cannot be pooled into
one Fast generation.

The older local estimate of **about 25–30 minutes/month** for the two-account Flow + free-tier mix
is retained as a historical estimate only. It must not be presented as the current guaranteed
balance. As of the fresh 11:58 IST read, Digen and RTST are both below one cheapest clip and no
numeric current remainder is guaranteed from those API seats.

## Expansion answer

**Yes, the architecture can expand**, but expansion is evidence-gated per account/provider:

1. **Four Google Flow accounts (two Pro, two normal).** The pool already supports one exact session
   file per account and hot-reloads new files without a shim restart. The live UI/tab check now
   finds all four project tabs and reports them `ready`, but only the two Pro seats are admitted with
   submit → poll → downloadable-MP4 proofs. The two additional accounts are therefore **ready but
   not graduated**. A safe expansion requires each account to be signed in on its own dedicated
   automation profile, a real Flow submit → poll → MP4 proof, and a pinned
   `video/labs.google/auto` consumer proof attributed to that exact session file. Using the official
   50-daily-credit rule, two normal accounts add a planning ceiling of about 20 minutes/month at
   8-second Fast (75 clips × 8 seconds each per account), making the all-four planning ceiling about
   **53.3 minutes/month** (2 Pro + 2 normal, 30-day month). This assumes separate entitled accounts,
   continuous daily use, Fast 8-second generations, and no policy/quota changes; it is not yet an
   achieved capacity claim.

2. **OmniRoute providers.** The chat side currently has **11 exact-file consumer-admitted seat
   routes**. Native Omni video currently has **zero admitted video routes**. Published model rows
   and candidate aliases need provider-by-provider direct video proof, correct request-shape/
   credential handling, and a second consumer proof through `:8190` before they can count. A
   catalog row or a successful chat route is not video capacity. Provider credentials, quotas, and
   any payment/plan walls remain terminal until the operator supplies a legitimate entitlement.

3. **Keepalive boundary.** The new shim heartbeat prevents idle stateless session jars from going
   stale by making one bounded real chat request and persisting any rotated cookie. It cannot refresh
   Google/Chrome cookies, resurrect an expired browser login, or create provider credits. The separate
   `:20130` heartbeat and OmniRoute OAuth keepalive continue to serve their own fleets; they do not
   own the `:8190` session files.

The video-router task on `:8189` remains disabled under the documented crash-containment decision.
No video generation was submitted to manufacture a number during this report. The current
seat-owned Flow queue samples remain provider-side `scheduled/waiting` with no newly correlated MP4;
they are not counted as additional capacity.

## Expansion preparation completed at 09:22 IST

The live-profile guard now distinguishes a stale operator `DevToolsActivePort` marker from a real
operator listener by checking the reachable listener's process and resolved user-data directory.
The migrated-tab matcher now accepts `flow.google.com/project/<id>` as well as the rollback-era
`labs.google/fx/tools/flow` form, and the UI probe no longer treats the retired relative session
endpoint's HTML shell as a JSON credential. Read-only target inspection found visible composers on
all four Flow project tabs (9222, 9223, 9224, 9225) and balances 0/15/0/15. Those auth/session
states are readiness evidence, not video capacity. The migration and error-body regression suites
are green (25 focused Flow/probe tests; 26 focused replay/fleet tests). The two unadmitted Flow
declarations and all OmniRoute native video candidates remain outside the five-seat admission count
until they pass the real submit → poll → MP4 and pinned `:8190` consumer proofs.
