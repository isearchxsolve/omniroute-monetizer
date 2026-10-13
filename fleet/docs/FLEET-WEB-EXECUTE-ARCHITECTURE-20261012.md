# OMNIRUTE WEB-EXECUTE — AGENT INTERNET ARCHITECTURE SPEC
**Date:** 2026-10-12 · **Updated:** 2026-10-13 17:30 IST
**Status:** LOCKED — PHASE 1 LIVE · PHASE 2 LIVE · PHASE 3 LIVE (verified end-to-end) · PHASE 4 LIVE · GATEWAY LIVE (door side)
**Parent doc:** FLEET-KAGGLE-RUNBOOK-20261012.md · MASTER-DOC-OMNIRUTE-AGENT-INTERNET-20261012.md
**Thesis:** OmniRoute Monetizer generalizes from *free LLM wire* to *free WWW wire* — any AI agent gets a Python execution body for the authenticated web. Parallel (Parag Agarwal) indexes the public web the hard way; we replay the authenticated web the lazy way. His layer is a map. Ours is a body.

---

## 1. THE TOOL CONTRACT

Any AI agent (Kilo, Claude, GPT, Antigravity) calls ONE tool over HTTPS. No custom SDK required beyond the fleet token.

### Endpoint (permanent door)
```
POST https://omniroute-relay.omniroute-fleet-kd.workers.dev/v1/tools/web.execute?token=GOLD24
```

### Request
```json
{
  "mode": "edge" | "fleet",
  "url": "https://example.com/api/search?q=...",
  "method": "GET" | "POST" | ...,
  "headers": {"User-Agent": "..."},
  "body": "raw body or null",
  "timeout_s": 15,
  "max_bytes": 100000,
  "capture_id": "optional registry ref for fleet replay"
}
```

### Response (immediate)
```json
{"job_id": "wx_a1b2c3", "mode": "edge" | "fleet", "status": "done" | "queued"}
```

### Result Lookup
```
GET /v1/tools/web.result?token=GOLD24&job_id=wx_a1b2c3
```
```json
{
  "job_id": "wx_a1b2c3",
  "status": "done" | "pending" | "failed",
  "mode": "edge" | "fleet",
  "http_status": 200,
  "content_type": "application/json",
  "content_b64": "...",
  "executed_by": "worker-edge" | "kaggle:cloud-cell",
  "duration_ms": 340
}
```

### Two Execution Paths

| Path | Who | When | Latency |
|------|-----|------|---------|
| **edge** | Cloudflare Worker itself (`fetch()` outbound) | Public URLs, simple GET/POST, no login | ~50-500ms |
| **fleet** | Kaggle kernels via door ledger | Authed wires, multi-step flows, capture-replay, sessions | 3-15 seconds |
| **playwright** | Dedicated headless-Chromium Kaggle kernel | Pure-JS SPAs, DOM extraction, cookie injection, screenshots | 4-30 seconds |

The Worker decides automatically: no `capture_id` + no cookies + simple method (GET/HEAD) + `mode!="fleet"` and `mode!="playwright"` → edge fast path. `mode:"playwright"` forces the `ledger:PLAYWRIGHT` queue. Otherwise queued to Kaggle fleet.

---

## 2. CAPTURE REGISTRY (LIVE IN PRODUCTION)

Located at `state/captures/{site}/{flow}.json` (mirrored in `C:\kaggle\working\state\captures` and `D:\anonym\state\captures`).

### Capture Schema Specification
```json
{
  "capture_id": "site.flow.version",
  "site": "site_identifier",
  "flow": "flow_name",
  "version": 1,
  "captured_at": 1791820800,
  "account_hint": "pool_identifier",
  "wire": {
    "steps": [
      {
        "name": "step_name",
        "method": "GET|POST",
        "url": "https://...",
        "headers": {"Header": "Value"},
        "body_template": "raw string or json template with {placeholders}",
        "extract": {
          "variable_name": "regex:pattern | json:key.path"
        },
        "response": "json|text"
      }
    ]
  },
  "params": {
    "param_name": "required|optional:type:default_value"
  },
  "fresh_fields": {
    "field_name": "crypto:uuid4 | time:epoch_s | time:epoch_ms | time:iso"
  },
  "tls": {
    "impersonate": "chrome"
  },
  "walls": ["csrf", "session-cookie", "ja3"],
  "sentinel": {
    "probe": {"method": "GET", "url": "https://site.com/api/me"},
    "expect": {"http_status": 200, "contains": "identifier"},
    "on_fail": "session_expired -> rotate account pool"
  },
  "notes": "Human rationale and details"
}
```

### Initial Production Captures (Battle-Tested)

1. **`github.get_zen.v1`** (`state/captures/github/get_zen.v1.json`):
   - Fast edge public verification baseline.
   - Verified live: returned HTTP 200 with Zen text `"Non-blocking is better than blocking."`

2. **`httpbin.post_payload.v1`** (`state/captures/httpbin/post_payload.v1.json`):
   - Authenticated POST replay with dynamic header generation.
   - Dynamic fields: `{timestamp_epoch}` (`time:epoch_s`), `{nonce_uuid}` (`crypto:uuid4`).
   - Verified live: echoed custom headers and injected JSON payload.

3. **`linkedin.search_jobs.v1`** (`state/captures/linkedin/search_jobs.v1.json`):
   - Multi-step enterprise job search wire.
   - Step 1: Bootstrap search page to extract `csrfToken` and `pageKey`.
   - Step 2: Query Voyager API with extracted CSRF token, dynamic page-instance UUID, and parameter substitution (`{query}`, `{location}`, `{geo_id}`).
   - Sentinel: Probes `/voyager/api/me` expecting `miniProfile` before replaying stateful calls.

---

## 3. CAPTURE REPLAY ENGINE (`capture_replay.py`)

Implemented at `C:\kaggle\working\capture_replay.py` and `D:\anonym\war-pipe\capture_replay.py`:
- **Parameter Substitution:** Replaces `{param}` placeholders from runtime arguments and defaults.
- **PREFLIGHT Generation:** Replaces dynamic nonces, timestamps, and UUIDs automatically on every invocation.
- **Sentinel Liveness & Poison Defense:** Verifies session cookies against sentinel endpoints prior to execution. If sentinel fails, triggers account rotation instead of serving stale data.
- **BoringSSL & JA3 Chrome Fingerprint:** Uses `curl_cffi` to impersonate real browser TLS fingerprints, completely bypassing Cloudflare, Akamai, and Datadome JA3 fingerprint walls.
- **Multi-Step State Flow:** Extracts regex and JSON tokens from intermediate responses and threads them into downstream requests.

---

## 4. FLEET EXECUTION & ZERO-BURN DISCIPLINE

```
Agent                      Worker (edge)              Kaggle Cloud Cell
  │ POST web.execute           │                          │
  ├───────────────────────────▶│ simple? → fetch now      │
  │◀─── {job_id} or RESULT ────┤                          │
  │                            │ complex? → KV queue      │
  │                            │ ledger:WEBEXEC ◀─────────┤ poll 15s (cached door)
  │                            │                          ├─ execute real HTTP (curl/subprocess)
  │                            │ POST web.result ◀────────┤ post result (KV wx:{job_id}, TTL 86400s)
  │ GET web.result             │                          │
  ├───────────────────────────▶│ KV read                  │
  │◀─── {status:done,...} ─────┤                          │
```

### Zero-Burn Quota Governance:
- Polling interval relaxed to **15 seconds** (5,760 requests/day per kernel, staying safely within Cloudflare's 100k daily ceiling).
- Door resolution cached for **300 seconds** (eliminates redundant `/health` roundtrips).
- Routine debug writing (`FETCHDBG`) **completely eliminated** from idle poll cycles, conserving the 1,000 KV writes/day quota.
- Results expire automatically after **24 hours** (`expirationTtl: 86400`).

---

## 5. MODEL CONTEXT PROTOCOL (MCP) SERVER (PHASE 4)

Implemented at `C:\kaggle\working\omniroute_mcp.py` and `D:\anonym\war-pipe\omniroute_mcp.py`.
Exposes the entire OmniRoute agent internet to any MCP-compliant assistant (Claude Desktop, Cursor, Antigravity, Kilo) over standard I/O (JSON-RPC 2.0).

### Available MCP Tools:
1. `web_execute` — Takes `url`, `method`, `headers`, `body`, `mode`, `timeout_s`. Returns execution result or queued job ID.
2. `web_result` — Takes `job_id`. Returns the asynchronous result of a fleet job.
3. `capture_execute` — Takes `capture_id` and `params`. Replays any capture from the registry directly with dynamic headers and TLS fingerprinting.

### Configuration for Claude Desktop / Cursor:
```json
{
  "mcpServers": {
    "omniroute": {
      "command": "python",
      "args": ["C:/kaggle/working/omniroute_mcp.py"]
    }
  }
}
```

---

## 6. PHASE 3: PLAYWRIGHT EXECUTOR (LIVE — VERIFIED 2026-10-13 13:19 IST)

While 90% of high-value sites expose clean REST/GraphQL/Voyager APIs that can be replayed via `capture_replay.py`, certain pure-JS single-page applications render data strictly via client-side DOM execution without reusable endpoints.

### Phase 3 Architecture (DEPLOYED):
1. **Dedicated Playwright Kernel:** `isearchxsolve/omniroute-playwright-executor` — Kaggle CPU kernel, installs `playwright` + Chromium at boot, polls `ledger:PLAYWRIGHT` (15s, zero-burn).
2. **Same Tool Contract:** Agents call `web.execute` with `"mode": "playwright"` → Worker queues `PW_EXECUTE:{json}` to `ledger:PLAYWRIGHT`.
3. **Cookie Injection:** Playwright-format cookie lists or raw `Cookie` header strings are parsed and injected into the browser context.
4. **DOM Extraction:** CSS selectors with `attr` (`text`/`html`/attribute), `all` (match all), `limit`; body `innerText` always included; optional `screenshot` (PNG base64).
5. **Graceful waits:** `wait_css` + `wait_ms` — selector-wait timeouts are reported as `wait_warning` in the result, never fatal.

### Playwright job spec (inside `web.execute`):
```json
{
  "mode": "playwright",
  "url": "https://spa.example.com",
  "headers": {"Cookie": "session=..."},
  "wait_css": ".job-card",
  "wait_ms": 3000,
  "extract": [
    {"name": "cards", "selector": ".job-card", "attr": "text", "all": true, "limit": 50},
    {"name": "next_page", "selector": "a[rel=next]", "attr": "href"}
  ],
  "screenshot": false,
  "timeout_s": 30,
  "max_bytes": 100000
}
```
Result: `content_type:"application/json"`, `content_b64` = JSON of `{http_status, final_url, title, text, extracts, screenshot_b64?}`, `executed_by:"kaggle:playwright"`.

**Verification proof:** `wx_605bf56676f7` → example.com, HTTP 200, title "Example Domain", multilingual DOM text extracted, 4066ms.

## 6.5 GATEWAY — SESSION POOL ROUTING (door side LIVE)

Kernels with public tunnels register into the door's session pool; agents route through ONE permanent URL:

```
POST /v1/gateway/register?token=   {"service":"oiioii","url":"https://<tunnel>","meta":{...}}   (KV TTL 1800s)
GET  /v1/gateway?token=                        -> {"sessions":[...],"count":N}
GET  /v1/gateway?token=&service=oiioii         -> one live session (503 if none)
ANY  /v1/gateway/route?token=&service=oiioii&path=/api/...  -> Worker proxies to the session
```
- Dead sessions age out via KV TTL (30 min); kernels re-register every 10 min (144 KV writes/day/service — zero-burn safe).
- `x-omniroute-duration-ms` + `x-omniroute-session` response headers on routed calls.
- OiiOii/EmergentSH supervisor kernels (v21/v19 on n42888) register automatically when their tunnel is UP.

---

## 7. VERIFIED STATUS & PROOFS

- **Phase 1 (Tool Endpoints & Fleet Loop):** 5/5 jobs passed (`wx_6b2dc5779c1c`, `wx_0ef15400814f`, `wx_9510d1e0483c`, `wx_5e5d12c8f85d`, `wx_7e409c537c70`) echoing headers and payload. Re-verified under Worker v3: `wx_4810f186ee6b` done via `kaggle:cloud-cell` (401ms).
- **Phase 2 (Capture Registry & Replay Engine):** Verified live with `github.get_zen.v1` and `httpbin.post_payload.v1`.
- **Phase 3 (Playwright Executor):** LIVE — kernel `isearchxsolve/omniroute-playwright-executor`; `wx_605bf56676f7` executed on `kaggle:playwright` (HTTP 200, DOM extracted, 4066ms).
- **Phase 4 (MCP Server):** Verified live with full JSON-RPC 2.0 stdio handshake (`initialize`, `tools/list`, and `tools/call`).
- **Gateway (session pool):** Worker endpoints live + verified (`register`/`list`/`route` all proven with probe sessions); kernel-side registration via supervisor kernels in flight.

Any agent, one tool, the whole authenticated web.
