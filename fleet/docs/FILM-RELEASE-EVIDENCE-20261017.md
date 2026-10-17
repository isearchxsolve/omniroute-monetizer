# Film product: verified evidence and remaining release gates

The owner selected the film-making product on 17 October 2026. No payment or
revenue has been verified. The urgent INR10,000 target is not secured by these
engineering checks.

## Verified live

- Permanent relay version `3.2.3-binary-gateway` is deployed.
- Public JSON GET capture `github.cpython.metadata.20261017.v1` graduated from
  actual Kaggle Playwright observation to independent curl replay. Both returned
  HTTP200 and genuine `python/cpython` repository data. Native MCP status works.
- Corrected CPU cloud version8 completed another real warm replay
  `wx_ca984527a53c`. Browser version5 remains active. Duplicate repair cloud
  versions5/6/7 and browser version4 were visibly cancelled.
- The fake legacy film completion handler and invented CDN URL were removed.
  The live relay also rejects retired render dispatch, protecting against older
  executors. Runtime generators now contain the fixes.
- Private finite GPU render proof was pushed with an explicit2700s limit.
  Re-pulled metadata requests `NvidiaTeslaT4`; actual notebook logs separately
  report two TeslaT4 devices and a successful pre-install hardware gate.
  The model rendered a real silent6.125secondH264 MP4,720x480,49decoded frames at8fps,888842bytes. Actual inference took621.635seconds. Downloaded SHA256 matched the GPU receipt: `58e57e7360ee4c3b708f2ff9e427fca36999201839bfde4765c716ad8f896c43`. Independent local ffprobe confirmed the same media properties. Contact sheet inspected: coherent garden/camera scene; long-film quality, dialogue and customer delivery remain unverified.

Local network receipts are under `state/`: `film_support_graduation_20261017.json`,
`cloud8_warm_result_20261017.json`, `capture_mcp_live_20261017.json`,
`film_gate_live_20261017.json`, and `film_product_preflight_20261017.json`.
These are actual recorded responses, not sample payloads.

The relay now streams binary media instead of corrupting it as UTF8 text. An actual public PNG failed the old isolated proxy (958bytes became1620) and passed the new proxy byte-for-byte. Customer authorization forwarding is implemented but awaits a real customer integration proof.

See [Kaggle-first free hosting preparation](KAGGLE-OIIOII-FREE-HOSTING-PLAN-20261017.md).

## Paid release is blocked

1. The public capture adapter only supports credential-free JSON GET requests.
   It does not implement authenticated film generation or a provider-specific DAG.
   Sentinel healing exists in code but has not earned a live failure/recovery proof.
2. The relay has no working chat/video inference surface or registered film app.
   A standalone GPU render does not close this integration gap.
3. The old film web notebook exposes FastAPI, not the Next customer frontend.
   Customer login, render submission, progress and download need a complete UI run.
4. Local owner configuration exists, but it is not deployed into Kaggle. The app
   account database defaults to SQLite. Its independent film-job database and
   object store also use local disk. Merely adding PostgreSQL for accounts will
   not preserve the separate job graph and media across Kaggle session expiry.
5. A real owner login, tenant isolation, restart recovery and authorized MP4
   download must pass against the chosen persistent deployment.
6. Payment collection and paid customer entitlements have no live receipt.
   Do not advertise unlimited films or take payment as if these gates passed.

## Render proof reproduction

`python fleet/tools/stage_film_render_probe.py` stages the private notebook.
Its first cell gates actual2xT4 hardware before installs or downloads. It renders
one original49-frame720x480 scene using the official FP16
[CogVideoX-2b model](https://huggingface.co/zai-org/CogVideoX-2b).
The notebook decodes the MP4 and saves its measured hash, frame count and contact
sheet. `python fleet/tools/collect_film_render_proof.py` only accepts a finished
run and verifies downloaded bytes against that genuine GPU receipt. Visual
review remains required; no failure is converted into a placeholder clip.

## Hosting research, not an activated deployment

If no existing persistent host is available, investigate a small external
metadata/media store and adapt the film-job/object store before deployment.
[Supabase Free](https://supabase.com/pricing) currently includes500MB database
and1GB file storage, with inactivity pausing. This is a limited pilot option,
not sufficient evidence for an unlimited film service. No account was created,
subscription started, or credentials transmitted.

[Render Free](https://render.com/docs/free) has ephemeral application disks and
its free PostgreSQL expires after30days; this does not fix durability by itself.
[Hugging Face Spaces](https://huggingface.co/docs/hub/en/spaces-overview) currently
requires a paid plan to create compute Spaces despite CPU Basic having no hourly
hardware charge. Do not describe it as an unconditional zero-cost backend.
