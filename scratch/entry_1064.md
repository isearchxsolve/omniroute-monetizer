### [2026-08-24 02:3x] #1064 — THE TWELVE-TAB VIDEO SHELF, CLOSED OUT: rtst.ai IS A SECOND PROVEN ROUTE (real video, 6 credits, quoted 6); two money bugs fixed in flow_shim; and six of my own probe-tool bugs found by disagreeing with my own results

**Operator request:** *"check all the tabs in my chrome profile"*, then *"if you are done with the flow lets close the other ones"*. Flow was finished in #1063; this entry closes every other candidate with a verdict.

#### The one that mattered: rtst.ai is wired and proven

A real video was generated end to end: `vidu` (Vidu Q2) 3s @540p, **quoted 6 credits and charged
exactly 6** (30 → 24), delivered as `state/harvest/rtst/96089.mp4` (872,579 bytes, `ftyp` verified).

The whole contract was proven at **zero cost first** — payload shape, the ≥10-word prompt rule, and
server-side HTTP 402 balance enforcement — with the balance confirmed unchanged at 30 after both
probes. The technique that made that possible is worth keeping: **send a well-formed request for
something demonstrably unaffordable.** The server *must* reject it, so no video can be created, yet
the rejection reveals field-level validation. Validation runs before the balance check, so a short
prompt stops the probe early and hides the rest of the contract — the first attempt returned
`VALIDATION_INVALID_PROMPT` at 9 words and taught me the minimum.

rtst.ai earns its place for one reason: `GET /video/estimate-credits` returns
`{credits_required, credits_per_second, current_balance, can_afford, allowed_durations}`, so **every
cost question is settled for free.** Compare Flow, where the only way to learn a price was to spend
20 credits and diff the balance. `scripts/automation/rtst_client.py` gates `submit` behind
`--confirm-spend` AND a fresh `can_afford` quote AND `--max-spend`; everything else is read-only.
Trap recorded: `is_free:true` does **not** mean free — `wan22` carries that flag and still quotes 10
credits. It means "available on the free plan".

#### The money-safety review dimension is finally done — and it found two real defects

This is the dimension that stalled on all six attempts in #1063, on the one file that spends money.
Run inline this time. Both fixes are in `scripts/automation/flow_shim.py`:

1. **The reservation floor could ratchet upward and strand capacity permanently.** A billing
   observation is `credits_before` (read from the account) minus `credits_after` (read from the submit
   response). Anything else spending on that account inside that window — the operator in their own
   browser, a direct `googleflow_client.py` run — lands in the delta. Letting the newest delta become
   the floor meant one concurrent 1080p generation elsewhere would raise the floor to 80 *forever*,
   after which `acquire()` refuses every account holding 20–79 credits. That is precisely the bug the
   old hardcoded 60-credit floor caused. Now the floor moves **down freely and up never**, per-media
   deltas above `COST_FLOOR_MAX = 200` are discarded as someone else's spending, and a disagreement is
   logged with an explicit "check before trusting the balance arithmetic".
2. **A stale balance could survive a charged submit.** If a submit charges but the response omits
   `remainingCredits`, the cached balance is now known-wrong. The account is marked `ready = False`
   with reason "balance unconfirmed after a charged submit; awaiting re-probe" — deliberately *not*
   by clearing `credits`, because `acquire()` calls `probe_all()` when nothing is ready but raises
   immediately if a ready account merely lacks credits.

`scratch/shim_smoke.py` grew a 6-check money block covering both. Full suite: **22 checks, all green,
0 credits spent.**

#### The census, and the correction to two numbers I reported yesterday

**Page-text balances are rumours.** Two of the three I reported on 2026-08-23 were wrong: rtst.ai
rendered "412 credits" against a real 30, and topmediai rendered "3,000 Credits" while its API says
the profile is not even logged in *and* its UI multiplies real credits by 50 for display. Root cause
fixed in `tab_recon.py`, which now prints `CREDITS(page,unverified)` with a `GUEST?` column.

| site | verdict | evidence (from its own API) |
|---|---|---|
| **rtst.ai** | **WIRED AND PROVEN** | 24 credits left = 4 more short clips |
| **heygen.com** | **AUTHENTICATED, real unused free quota** | `data.user_plan_v2.available_quota_v2`: 3/3 Hyperframes renders, 5/5 API renders, 3/3 avatar IV, 600/600 TTS — `amount == total` everywhere, nothing spent |
| kling.ai | AUTHENTICATED, balance unreadable | userId 97309502; profile readable unsigned, but every other call needs a `__NS_hxfalcon` anti-bot param |
| digen.ai | VIABLE, needs work | daily login reward for user 3666347; session is device-bound via FingerprintJS |
| openart.ai | NOT A ROUTE — empty | ledger has exactly one entry: `CONSUME -40 trial_credit_balance, 40 → 0, 2026-04-08` |
| topmediai.com | NOT A ROUTE — signed out | `Login expired`; app calls `/v3/user/tourist_id` |
| akool.com | NOT A ROUTE — signed out | HTTP **200** `{"code":1002,"msg":"authorization cannot be empty"}` |
| teamily.ai | NOT A ROUTE — signed out | `open.teamily.ai` → 401 `ACCOUNT_NO_EXIST`; no video-submit endpoint exists at all |
| imagine.art | NOT A ROUTE — not the app | marketing origin, 8.9MB of bundle, and **zero** XHRs of its own after a reload |
| flux-ai.io | NOT A ROUTE | no API; see the correction below |
| capcut.com | NOT WORTH IT | msToken request signing, largest job on the shelf, and its UI shows 0 credits |

**heygen is the best remaining candidate to wire** — but it is avatar/presenter video, not
prompt-to-video, so it is only a route if the filmmaking app wants avatar or Hyperframes renders. Its
submit contract has **not** been probed; no generate endpoint was called.

#### Six bugs in my own probe tooling, found by disbelieving my own output

Every one of these produced a *confident wrong answer*, which is the failure mode that matters:

1. **`site_probe` filtered script URLs to the page's own registrable domain** — the identical mistake
   already fixed in `tab_recon`. akool and teamily serve their whole app bundle from a CDN host, so
   all 166 scripts were discarded and both sites reported "0 paths" as if they had no API. Fixed by
   excluding known analytics/ad hosts instead, and fetching with `credentials:'same-origin'` (a
   wildcard-CORS bundle response is *invalid* for a credentialed request).
2. **No time budget on the discovery loop.** Once it read cross-origin CDN bundles, one slow script
   hung the whole probe and the site got no verdict at all — worse than a partial read. Fixed with a
   100s overall deadline plus a 12s per-script `AbortController`.
3. **Candidate URLs were built from the CLI name, not the tab's origin.** A tab on `app.heygen.com`
   had every call made cross-origin to `heygen.com`, so everything returned `TypeError: Failed to
   fetch` — reads like a dead site, was self-inflicted. Fixed: the page's own origin goes first, where
   CORS cannot refuse.
4. **An HTML body counted as proof of an authenticated API.** flux-ai.io was called AUTHENTICATED off
   `/subscription-terms` returning a marketing page, with "submit-shaped" paths that were all
   marketing routes. Fixed: evidence must be JSON. **HTTP 200 + a body proves nothing.**
5. **Signed-out was detected from prose only**, so akool's `200 {"code":1002}` and teamily's `401
   ACCOUNT_NO_EXIST` both slipped past. Fixed: 401/403 is now structurally decisive.
6. **Balance candidates were ranked by name**, so teamily's Next.js page route `/credit-usage` (which
   500s with `Only HTML requests are supported here`) was tried ahead of its real `/userCenter/api/v1/`
   endpoints. Fixed: API-shaped paths rank first, and the bundle's *own* host list is tried too.

One reload-based technique was added and is worth reusing: a tab open for hours no longer remembers
the XHRs its app fired at startup, and those are the only record of endpoints built from template
strings. Reloading replays exactly the app's own requests. **Navigation only — nothing clicked, no
generate button touched, so it cannot spend a credit.** It is what cracked kling and heygen.

#### Safety posture held throughout

Zero credits spent on any site except the one deliberate 6-credit proof run. No password typed, no
CAPTCHA touched, no payment form. Every bearer token was read and used *inside* the page and never
crossed the CDP boundary; only lengths and JWT-ness were ever printed. Cookie names only. Saved
artifacts are scrubbed. A login wall in the automation profile was reported as the correct outcome
three times (topmediai, akool, teamily) rather than worked around.

#### Still owed

1. **4-account Flow rotation** is still one account. Only port 9222 is debuggable; accounts 2–4 need
   their own profile plus `--remote-debugging-port`, then `flow_shim.py add <port> --label <name>`.
2. **Generalise `flow_shim` into a multi-provider router.** Two proven providers now sit behind two
   different faces. The right shape is not N bespoke clients but one router where each site is a
   submit/poll/download adapter. This is the main architectural debt of #1063 and #1064 combined.
3. **heygen's submit contract is unprobed** — the free quota is real but nothing has been generated.
4. `veo_3_1_t2v_quality` and `veo_3_1_t2v_lite` remain **inferred** from the fast key's naming and are
   reported `proven:false`.
5. `gf.submit`'s captcha `ACTION_FALLBACKS` loop still re-submits on a 403 with no idempotency key. If
   Flow ever returns 403 *after* creating the video, that retry mints and charges a second clip.
6. capcut's 0-credit figure is the only number in this census taken from a UI rather than an API.

Full machine-readable census: `state/harvest/probes/FINDINGS.json`.
