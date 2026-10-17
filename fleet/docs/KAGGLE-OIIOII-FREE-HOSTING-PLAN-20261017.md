# OiiOii on rotating Kaggle: free-tier preparation

**Decision:** keep the application compute on Kaggle. A separate paid web host
is not required. This is a prepared deployment plan, not a completed paid launch.
The owner requested free options; no account, subscription or billing agreement
has been created or accepted.

## Compute layout, common to both options

| Part | Location | Required behavior |
|---|---|---|
| Stable front door | Existing Cloudflare Worker | Resolve the healthy active `oiioii` session; keep management credentials out of browser JavaScript |
| Customer frontend and FastAPI | Rotating Kaggle CPU notebook | Serve the real Next customer UI and its API together; production owner bootstrap; no local-only customer state |
| Video generation and assembly | Finite Kaggle T4 worker | Hardware gate before installs/models; bounded jobs, measured output, per-job receipts; no idle GPU hosting |
| Accounts, film graph and leases | Shared durable database | All replacement notebooks see the same ownership, session, admission and idempotency state |
| Source media and finished MP4s | Private durable object storage | Verify uploaded bytes/hash before marking delivery available; authorized downloads |

## Storage options

| Option | Free-tier preparation | Limits / work remaining |
|---|---|---|
| **A: Supabase Free, preferred pilot** | One project supplies PostgreSQL and private media storage; Kaggle remains the web/GPU host | Current allowance:500MB DB and1GB files, inactivity pause; Free upload ceiling50MB per file. Start with short clips. Port the independent SQLite film-job store and local object store; do not assume setting `DATABASE_URL` performs that migration. |
| **B: Existing Cloudflare account, D1 + R2** | SQLite-oriented durable metadata plus private media buckets alongside the existing relay | Read-only inspection found no D1 databases and R2 not enabled (API code10042). Activation and account terms must be reviewed first. D1 requires a transaction-safe store adapter; R2 is metered outside its free allowance, so no automatic activation or claim of guaranteed zero charges. |

OptionA reduces initial account setup. OptionB keeps services within the existing
Cloudflare account but is not currently activated. Neither option supplies a
paying buyer or guarantees the emergency INR10,000 target.

Official sources checked17October2026:
[Supabase pricing](https://supabase.com/pricing),
[Supabase file limits](https://supabase.com/docs/guides/storage/uploads/file-limits),
[Cloudflare D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/),
[Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/).

## Handover, before any customer traffic moves

1. Start the replacement CPU notebook with the exact code revision and the
   existing per-account Kaggle Secrets. No owner password or storage credential
   belongs in a notebook source file, app bundle, relay KV or frontend build.
2. Connect shared account, film-job and object stores. Run migrations once under
   a migration lock. Prove one-owner leases and idempotent job keys against the
   genuine shared database, not a mocked backend.
3. Verify frontend HTML, owner login, tenant isolation, API liveness, actual
   available render capacity and an authorized download. A process marked
   RUNNING, a root JSON response, or a successful notebook push is insufficient.
4. Only then publish the new gateway session. The relay's binary streaming fix
   has passed a real-network before/after test; customer auth/download integration
   still needs its own live proof.
5. Drain the old session's admitted jobs under shared leases. Confirm their
   progress/artifacts from the replacement, then stop the old version. Do not
   accumulate overlapping versions until the account hits its session cap.
6. Force a controlled restart and prove account, film status, retained output and
   download recovery. Only after this passes should paid customer access open.

## First real render, already earned

Standalone Kaggle proof produced an original silent H264 MP4,720x480,49frames,
8fps,6.13seconds,888842bytes. Actual inference took621.635seconds. Source and
download SHA256 match:

`58e57e7360ee4c3b708f2ff9e427fca36999201839bfde4765c716ad8f896c43`

Both actual GPUs were TeslaT4, verified before installs or model downloads.
The contact sheet was inspected: the garden/camera motion is coherent; it is a
short prototype scene, not evidence of long-film quality, dialogue or customer
delivery. Do not extrapolate unlimited throughput from this single measurement.

Artifact and receipts:
`state/film_render_output_20261017/film-render-proof/` and
`state/film_render_output_20261017/download_verified.json`.

## Next implementation gates

- Select and provision the free durable store through the owner's account flow.
- Implement and prove film-job/media persistence; migrate actual state safely.
- Stage a CPU notebook that builds/serves Next plus FastAPI; owner secrets stay
  outside uploaded code. Its readiness check must cover the customer workflow.
- Repair rotator lifecycle handling before enabling unattended rotation: generator
  failure must stop deployment, metadata ownership must survive regeneration,
  and readiness must be earned after a push. The old rotator remains stopped.
- Wire the real GPU renderer into the app's admitted job contract, then verify
  customer render, progress, stored MP4 and download across a rotation.
- Configure a real payment/entitlement path and verify it separately.
