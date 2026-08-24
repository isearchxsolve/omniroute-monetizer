# OmniRoute live verdict — 2026-08-24 (v2, corrected)

**Verified:** 2026-08-24 by decrypting stored credentials, probing providers **directly**, and
routing **through** the running gateway.
**Supersedes:** the v1 of this file (whose "100% of credentials are dead" conclusion was WRONG)
and the headline of `emergentsh-standalone-clean/docs/OMNIROUTE_HEALTH_ROOT_CAUSE_REPORT_2026-08-24.md`.

## Bottom line (proven)

**The stored provider keys are LIVE. OmniRoute works. Live generation runs through it today, $0.**

```
POST http://127.0.0.1:20128/v1/chat/completions   (Bearer = gateway key "neon")
model: gemini/gemini-flash-latest   →  HTTP 200, model gemini-3.7-flash, content "51", finish=stop
model: gemini/gemini-3.6-flash      →  HTTP 200, real streamed tokens
```

The gateway decrypted the key, called Google, and streamed back real, correct content with cost
tracking (`x-omniroute-provider=gemini`, `x-omniroute-response-cost`). Running gateway is **v3.8.49**
(not 3.7.1 as the older report assumed).

## The real root cause (not crypto, not the gateway key, not dead keys)

OmniRoute routes a connection only if its **last health-check verdict** (`test_status`) is usable.
Providers whose keys are actually live **now** are excluded because their `test_status` is a **stale
negative** from an old check — and `OMNIROUTE_DISABLE_CREDENTIAL_HEALTH_CHECK` is set, so that stale
verdict never self-heals. At request time the router returns `No active credentials for provider: X`.

Proven by direct-vs-gateway comparison:

| Provider | `is_active` | stored `test_status` | Direct curl (live?) | Through OmniRoute |
|---|---|---|---|---|
| gemini | 1 | **active** | 200 | **200 — real generation** |
| mistral | 1 | expired (401) | **200, generated "OK"** | 404 "No active credentials" |
| groq, cohere, alibaba, arcee-ai, morph, nscale | 1 | expired (401) | key authenticates (200 on `/models`) | 404 "No active credentials" |
| cerebras, deepinfra | 1 | credits_exhausted (402) | key authenticates | 404 "No active credentials" |

Decryption is **not** the blocker: gemini's legacy-encrypted key decrypted and routed fine on the
same running process, so the gateway can read the store. The only difference between gemini (works)
and mistral (excluded) is `test_status`.

## Where the original report was wrong

| Original claim | Live reality |
|---|---|
| `cryptography.status = missing_or_invalid` blocks generation | Only the **20130 dashboard** has bad crypto. The **20128 gateway** decrypts and generates fine |
| NeonBuild gateway key rejected (401) | The `neon` key returns **HTTP 200** with real content on 20128 |
| Credential store unusable | Store is fine; keys decrypt (legacy salt) and the providers are live |
| "100% of provider credentials are dead" (v1 of THIS file) | **False.** ≥10 keys are live; gemini generates through the gateway right now |

Why v1 was wrong: it tested **through** OmniRoute and read the gateway's stale `test_status`/`last_error`
as ground truth. Testing the keys **directly** (curl to each provider) disproved it.

## Working route today ($0)

```bash
GW=$(python -c "import sqlite3;print(sqlite3.connect(r'C:/Users/Admin/.omniroute/storage.sqlite').execute(\"select key from api_keys where name='neon'\").fetchone()[0])")
curl -s -X POST http://127.0.0.1:20128/v1/chat/completions \
  -H "Authorization: Bearer $GW" -H "Content-Type: application/json" \
  -d '{"model":"gemini/gemini-flash-latest","max_tokens":1500,"messages":[{"role":"user","content":"hello"}]}'
```

Note: `gemini-flash-latest` / `gemini-3.7-flash` is a **thinking** model — give it headroom
(`max_tokens` ≥ ~1000) or it spends the whole budget on `reasoning_content` and returns no visible answer.

## Execution log — what was actually done (2026-08-24)

1. **NeonBuild already points at the healthy gateway.** `backend/app/services/nim_client.py`
   defaults `OMNIROUTE_BASE_URL` to `http://127.0.0.1:20128/v1` (line 30). No `:20130` override
   exists anywhere in the app (the only `:20130` refs are docs + a reauth script that correctly
   targets the dashboard). **No change needed.**
2. **Reactivated 9 proven-live providers** — cleared the stale negative `test_status` (→ `active`,
   null `error_code`/`last_error`/`last_error_type`/`last_error_at`, `backoff_level=0`,
   `rate_limited_until=NULL`) in `provider_connections`. Rows backed up first to
   `_reactivation_backup_2026-08-24.json`. The gateway re-reads `test_status` **per request** (canary:
   a provider generated immediately after the DB update), so this took effect with **no restart**.
   - **6 now generate through the gateway:** gemini, mistral (`codestral-2508`), groq
     (`openai/gpt-oss-20b`), cohere (`command-a-03-2025`), alibaba (`qwen-max`), morph (`morph-v3-fast`).
   - **3 keys authenticate but have no balance** (genuine upstream billing, not a key problem):
     cerebras / deepinfra return `402`, arcee-ai returns `404 + credits`, nscale returns `429`. Left
     `is_active=1`; they'll route the moment they're funded. This is the correct failure mode.
3. **Rebuilt both combos** (`combos` table, `data` JSON, `strategy=priority`) with proven-live models,
   original `data` backed up to `_combos_backup_2026-08-24.json`:
   - `auto/best-coding`: **codestral-2508 (100)** → gemini-flash-latest (95) → qwen-max (90) →
     gpt-oss-20b (85) → command-a (80). Leads with codestral (~1s, no thinking pass) for snappy first-token.
   - `auto/best-reasoning`: gemini-flash-latest (100) → qwen-max (95) → mistral-small (90) →
     gpt-oss-20b (85) → command-a (80).
   - **Verified end-to-end** through `:20128` with the `neon` key: `best-coding` → codestral, real
     Fibonacci one-liner, finish=stop, **1.2s**; `best-reasoning` → qwen-max (gemini was rate-limited,
     priority failover engaged automatically), real content, finish=stop, **5.7s**.
4. **Health checks were deliberately NOT re-enabled.** `OMNIROUTE_DISABLE_CREDENTIAL_HEALTH_CHECK`
   and `OMNIROUTE_DISABLE_TOKEN_HEALTHCHECK` stay `true`. Re-enabling them re-introduces the
   event-loop-blocking sweeps (~37s stalls) and watchdog crashes documented in MASTER_WORKLOG
   #21/#22 — a worse failure than the stale-`test_status` symptom it would fix. **Real** request
   failures already update `test_status` in real time (proven by the 402/404/429 providers flipping
   back), so the store stays honest for providers that are actually exercised. If auto-self-heal of
   *idle* stale rows is wanted later, the right fix is a lightweight scoped re-test (only `is_active=1`
   rows, throttled, off the request path) — not the blanket sweep. Surfaced, not silently applied.

## Acceptance test for "fixed" — PASSING
- `gemini/gemini-flash-latest` → HTTP 200, non-empty `content` through `:20128` with `neon`. ✅ (`"51"`)
- ≥2 independent providers generating. ✅ (6 do)
- `auto/best-coding` returns real content. ✅ (codestral, working Fibonacci code, 1.2s)
- `auto/best-reasoning` returns real content. ✅ (qwen-max, 5.7s, with automatic failover from gemini)
