# OMNIRUTE PHASE 5 — AUTONOMOUS CAPTURE-TO-GRADUATION ARCHITECTURE
**Document ID:** `PHASE-5-AUTONOMOUS-GRADUATION-ARCHITECTURE-20261015.md`  
**Date:** 2026-10-15 06:45 IST  
**Parent Spec:** `MASTER-DOC-OMNIRUTE-AGENT-INTERNET-20261012.md`  
**Canonical Source:** `D:\omniroute-monetizer\fleet\`  
**Status:** DESIGNED, COMPILE-GATED & READY FOR PRODUCTION LOCK

---

## 0. EXECUTIVE THESIS: THE JIT WIRE COMPILER

In Phases 1–4, OmniRoute established a permanent Cloudflare Worker door (`worker.js`), a 5-account rotating Kaggle execution fleet (`rotator.py`), a fast `subprocess-curl` replay engine (`capture_replay.py`), a headless browser executor (`kaggle:playwright`), and a JSON-RPC 2.0 MCP server (`omniroute_mcp.py`). However, creating or repairing a site-flow wire recipe in `state/captures/` still treated the laptop as a manual capture studio.

**Phase 5 eliminates human hand-holding from the capture lifecycle.**  
Instead of using `kaggle:playwright` merely as a slow runtime scraper or relying on manual laptop Chrome sessions, Phase 5 turns the Playwright kernel into a **Just-In-Time (JIT) Wire Compiler**:
1. **Cold Discovery:** When an agent calls an unknown `capture_id`, the Permanent Door routes the request to `ledger:PLAYWRIGHT` with `"harvest": true`.
2. **Backward DAG Distillation:** The Playwright kernel navigates the live DOM, intercepts all XHR/Fetch/GraphQL network traffic via CDP, traces dynamic tokens (CSRF headers, cookies, UUID nonces, epoch timestamps) backward through prior responses, and synthesizes a deterministic wire recipe (`capture_synthesizer.py`).
3. **Shadow `curl` Graduation Gate:** Before completing the job, the kernel tests the candidate recipe using raw `subprocess-curl`. If the wire replay passes the Sentinel probe without a browser, it marks the recipe `"execution_pin": "wire_verified"` and ships it to the Door to be stored in `LEDGER` KV (`capture:{id}`). If client-side WASM/TLS walls block raw `curl`, it marks the recipe `"execution_pin": "playwright"` so future calls route cleanly without wasting fleet cycles.
4. **Autonomous Self-Healing (`v1` → `v2`):** Whenever an existing wire recipe breaks in production, `capture_replay.py` catches the failure at the Sentinel probe and reports `"status": "sentinel_failed"` to the Door. The Door intercepts the error before the calling agent sees poisoned data, bumps the capture version (`v1` → `v2`), re-queues the job to `kaggle:playwright` for live re-harvesting, and aliases `v1` → `v2` in a single KV write.

---

## 1. END-TO-END AUTONOMOUS STATE MACHINE

```text
              ┌──────────────────────────────────────────┐
              │  Agent / MCP calls /v1/tools/web.execute │
              │         with capture_id="site.flow.v1"   │
              └────────────────────┬─────────────────────┘
                                   │
                                   ▼
              ┌──────────────────────────────────────────┐
              │  Permanent Door (worker.js v3.2)         │
              │  Checks LEDGER KV for capture:{id}       │
              └──────┬────────────────────────────┬──────┘
                     │                            │
       [Present & wire_verified]        [Missing OR Cold Discovery]
                     │                            │
                     ▼                            ▼
    ┌────────────────────────────────┐  ┌──────────────────────────────────┐
    │ Enqueue -> ledger:WEBEXEC      │  │ Enqueue -> ledger:PLAYWRIGHT     │
    │ (Fast Fleet subprocess-curl)   │  │ (harvest: true)                  │
    └────────────────┬───────────────┘  └─────────────────┬────────────────┘
                     │                                    │
                     ▼                                    ▼
    ┌────────────────────────────────┐  ┌──────────────────────────────────┐
    │ capture_replay.py              │  │ playwright_harvester_hook.py     │
    │ 1. Run PREFLIGHT chain         │  │ 1. Attach CDP response listener  │
    │ 2. Substitute {{params}}       │  │ 2. Extract DOM for agent         │
    │ 3. Run terminal curl           │  │ 3. Run capture_synthesizer.py    │
    │ 4. Enforce Sentinel Probe      │  │ 4. Run Shadow curl Replay Gate   │
    └───────┬────────────────┬───────┘  └─────────────────┬────────────────┘
            │                │                            │
     [Sentinel OK]   [Sentinel TRIPPED]                   │
            │        ("sentinel_failed")                  │
            │                │                            │
            │                ▼                            │
            │   ┌─────────────────────────────────────┐   │
            │   │ Door Intercepts Poisoned Response   │   │
            │   │ Bumps Version (v1 -> v2)            ├───┘
            │   │ Re-queues to ledger:PLAYWRIGHT      │
            │   └─────────────────────────────────────┘
            │                                             │
            ▼                                             ▼
    ┌──────────────────────────────────────────────────────────────────────┐
    │ Door POST /v1/tools/web.result                                       │
    │ • Persists capture:{v2} + aliases capture:{v1} in LEDGER KV (1 write)│
    │ • Returns clean HTTP 200 payload to waiting Agent / MCP client       │
    └──────────────────────────────────────────────────────────────────────┘
```

---

## 2. THE 4-PASS NETWORK DISTILLATION ALGORITHM (`capture_synthesizer.py`)

Instead of parsing obfuscated frontend JavaScript, `capture_synthesizer.py` treats the Playwright HAR trace as a **Directed Acyclic Graph (DAG) of token dependencies**:

### Pass 1: Terminal Anchor Selection ($R_{\text{term}}$)
* Filters out static browser assets (`.css`, `.png`, `.woff2`, `.svg`, media) and non-200 responses.
* Scores remaining `application/json`, `graphql`, and form payloads by size and substring overlap against the DOM text extracted by Playwright.
* Selects the highest-scoring API response as the **Terminal Anchor** ($R_{\text{term}}$) and slices all earlier network entries `[0 ... term_idx - 1]` as candidate preflight sources.

### Pass 2: High-Entropy Token Fingerprinting
Every request header, query parameter, and body value in $R_{\text{term}}$ is classified into one of four buckets:
1. **`INPUT`:** Substrings matching runtime agent inputs (`job.inputs`) are converted into `{{param}}` template variables for `substitute_template()`.
2. **`CLIENT_NONCE`:** Values matching UUIDv4 regexes or 10/13-digit epoch timestamps within $\pm 86,400\text{s}$ of the current clock are mapped to local runtime macros (`{{__uuid4__}}`, `{{$PREFLIGHT.epoch_s}}`, `{{$PREFLIGHT.epoch_ms}}`).
3. **`HIGH_ENTROPY`:** Strings of length $L \ge 12$ with Shannon entropy
   $$H(X) = -\sum_{i} P(x_i) \log_2 P(x_i) \ge 3.6 \text{ bits/char}$$
   are flagged as dynamic server-issued secrets (CSRF tokens, session IDs, OAuth bearer tokens).
4. **`STATIC`:** Standard browser headers and low-entropy constants are preserved verbatim.

### Pass 3: Backward Provenance Resolution
For each `HIGH_ENTROPY` token $T$ in $R_{\text{term}}$, the synthesizer walks backward from $t_{-1}$ to $t_0$:
* **Case A — Cookie-to-Header Mirror (`response_header:set-cookie`):** Detects patterns like LinkedIn Voyager where a token is issued inside `Set-Cookie: JSESSIONID="ajax:..."` and echoed in `csrf-token: ajax:...`. Synthesizes a `PREFLIGHT` step with a cookie regex extractor (`pf_jsessionid`).
* **Case B — Custom Response Header (`response_header:<name>`):** Captures tokens issued in headers like `x-csrf-token` or `x-guest-token`.
* **Case C — Response Body Extraction (`response_body`):** Locates $T$ inside an earlier JSON or HTML payload and builds a bounded contextual regex (`16 chars prefix + capture group + 8 chars suffix`) to extract `pf_body_{idx}` at runtime.
* **Case D — Orphaned Signature (`orphaned_signatures`):** If $T$ never appeared in any prior server response, it was generated client-side by JS/WASM anti-bot instrumentation. The synthesizer records the orphaned signature so the Graduation Gate knows why raw `curl` may fail.

### Pass 4: Sentinel Synthesis
Automatically constructs a `sentinel` verification dictionary from $R_{\text{term}}$:
* `expect_status`: Exact HTTP status (typically `200`).
* `min_bytes`: $25\%$ of the observed valid response byte length (minimum 16 bytes).
* `reject_substrings`: `["login_required", "SESSION_EXPIRED", "cf-chl-bypass"]`.
* `require_json_keys`: Up to 5 top-level keys from the parsed JSON response object.

---

## 3. COMPONENT INVENTORY & SPECIFICATIONS

| File | Canonical Path (`D:\omniroute-monetizer\fleet\`) | Role | Quota Impact |
|---|---|---|---|
| **Synthesizer** | `capture_synthesizer.py` | Pure-Python 3.13 4-pass HAR-to-recipe compiler | Zero KV impact (runs in-memory on Kaggle) |
| **Harvester Hook** | `playwright_harvester_hook.py` | CDP network listener, DOM extractor (`6fd3b39` normalized), and shadow `curl` gate inside `kaggle:playwright` v3 | Bundles `graduated_capture` inside existing job result POST |
| **Replay Engine** | `capture_replay.py` | Executes `PREFLIGHT` + terminal wire via `subprocess-curl`, enforces Sentinel probe, posts `sentinel_failed` on break | 1 POST per job completion/failure |
| **Permanent Door** | `cf-worker\src\worker.js` (**v3.2**) | Resolves `capture:{id}` from KV, promotes `sentinel_failed` to `ledger:PLAYWRIGHT`, aliases `v1` → `v2`, exposes `/v1/captures/status` | **0 idle writes**; 1 write on graduation; 1 read on status check |
| **MCP Server** | `omniroute_mcp.py` (**v3.2.0**) | JSON-RPC 2.0 stdio server exposing `web_execute`, `web_result`, `capture_execute`, and `capture_status` | 300s cached door URL; zero `/health` polling |
| **Sync & Gate** | `sync_fleet_v32.ps1` | Enforces Python/notebook `compile()` gate, mirrors files across all 3 workspaces, runs local CPU smoke tests | Zero cloud quota cost (runs locally on laptop) |

---

## 4. PERMANENT DOOR v3.2 API EXTENSIONS (`worker.js`)

### 4.1 `POST /v1/tools/web.execute?token=T` (Capture-Aware Routing)
When the request body includes `"capture_id"`:
1. Calls `kvGet(env, "capture:" + spec.capture_id)`.
2. **If found in KV:** Attaches `spec.capture_recipe` and routes to `ledger:WEBEXEC` (if `execution_pin == "wire_verified"`) or `ledger:PLAYWRIGHT` (if `execution_pin == "playwright"`).
3. **If missing in KV:** Sets `spec.harvest = true`, `spec.mode = "playwright"`, and enqueues to `ledger:PLAYWRIGHT` with status `"queued_cold_harvest"`.

### 4.2 `POST /v1/tools/web.result?token=T` (Auto-Heal & Graduation)
1. **Sentinel Poison Interception:** If `result.status === "sentinel_failed"`, the Worker does **not** expose the failed payload to the agent. It increments the version suffix via `bumpCaptureVersion()` (`v1` → `v2`), re-queues the original spec to `ledger:PLAYWRIGHT` with `harvest: true` and `replaces_capture_id: oldCapId`, and updates `wx:{job_id}` to `"status": "healing_in_playwright"`.
2. **Recipe Graduation:** If `result.graduated_capture` is present, the Worker writes `capture:{graduatedId}` to `LEDGER` KV. If `result.replaces_capture_id` is set, it also updates `capture:{replaces_capture_id}` so existing agents calling `v1` automatically inherit the healed `v2` wire recipe.

### 4.3 `GET /v1/captures/status?token=T&capture_id=C` (Zero-Write Inspection)
Returns live metadata from `LEDGER` KV without consuming any KV write quota:
```json
{
  "ok": true,
  "exists_in_kv": true,
  "requested_id": "httpbin.heal_test.v1",
  "active_version_id": "httpbin.heal_test.v2",
  "synthesized_at": 1791993600,
  "execution_pin": "wire_verified",
  "verification": "shadow_curl_passed",
  "orphaned_signatures_count": 0,
  "preflight_steps": [],
  "target_method": "GET",
  "target_url": "https://httpbin.org/json",
  "sentinel": {
    "expect_status": 200,
    "min_bytes": 42,
    "reject_substrings": ["login_required", "SESSION_EXPIRED", "cf-chl-bypass"],
    "require_json_keys": ["slideshow"]
  }
}
```

---

## 5. QUOTA & SAFETY INVARIANTS PRESERVED

All Phase 5 modules adhere strictly to the **2026-10-13/14 Night Cycle Laws**:

1. **1,000 KV Writes/Day Protection:** Zero background telemetry writes. KV writes occur strictly on explicit job transitions and one-time recipe graduations.
2. **Generator `compile()` Gate:** `sync_fleet_v32.ps1` runs Python's built-in `compile()` across every `.py` file and every code cell inside every `.ipynb` notebook before copying a single byte to runtime directories.
3. **Law `6fd3b39` (Extract Normalization):** `normalize_extract_spec()` converts string extract selectors into `{str: str}` dictionaries before iterating, preventing `.get()` crashes on string characters.
4. **Hang-Proof Subprocess `curl`:** Both `playwright_harvester_hook.py` (shadow replay) and `capture_replay.py` (fleet execution) enforce `--max-time` and Python `subprocess.run(..., timeout=...)` hard kills.
5. **Laptop-First CPU Validation (Baba Order):** `sync_fleet_v32.ps1` executes local smoke tests on `capture_replay.py` and `omniroute_mcp.py` before any Cloudflare deployment.

---

## 6. OPERATIONAL RUNBOOK & VERIFICATION DRILLS

### 6.1 Synchronize & Validate Workspaces

```powershell
# Run compile gate, sync across all 3 roots, and execute local CPU smoke tests
powershell -ExecutionPolicy Bypass -File D:\omniroute-monetizer\fleet\sync_fleet_v32.ps1

# Sync + deploy Worker v3.2 to Cloudflare Edge
powershell -ExecutionPolicy Bypass -File D:\omniroute-monetizer\fleet\sync_fleet_v32.ps1 -DeployDoor
```

### 6.2 Drill 1: Cold Discovery → Auto-Graduation

```powershell
# 1. Request a capture_id that does not exist yet
curl.exe -s -X POST "https://omniroute-relay.omniroute-fleet-kd.workers.dev/v1/tools/web.execute?token=GOLD24" `
  -H "content-type: application/json" `
  -d '{\"capture_id\":\"github.auto_zen.v1\",\"url\":\"https://api.github.com/zen\",\"inputs\":{}}'

# 2. Verify graduation status in KV (expect execution_pin: "wire_verified")
curl.exe -s "https://omniroute-relay.omniroute-fleet-kd.workers.dev/v1/captures/status?token=GOLD24&capture_id=github.auto_zen.v1"
```

### 6.3 Drill 2: Poisoned `v1` → Autonomous Self-Healing to `v2`

```powershell
# 1. Seed a poisoned v1 capture requiring an impossible JSON key ("non_existent_key_999")
curl.exe -s -X POST "https://omniroute-relay.omniroute-fleet-kd.workers.dev/v1/tools/web.result?token=GOLD24" `
  -H "content-type: application/json" `
  -d '{\"job_id\":\"wx_seed_poison\",\"status\":\"seed\",\"graduated_capture\":{\"capture_id\":\"httpbin.heal_test.v1\",\"execution_pin\":\"wire_verified\",\"request\":{\"url\":\"https://httpbin.org/json\",\"method\":\"GET\",\"headers\":{}},\"sentinel\":{\"expect_status\":200,\"require_json_keys\":[\"non_existent_key_999\"]}}}'

# 2. Execute v1 -> Fleet Sentinel trips -> Door promotes to Playwright -> Graduates v2
curl.exe -s -X POST "https://omniroute-relay.omniroute-fleet-kd.workers.dev/v1/tools/web.execute?token=GOLD24" `
  -H "content-type: application/json" `
  -d '{\"capture_id\":\"httpbin.heal_test.v1\",\"url\":\"https://httpbin.org/json\"}'

# 3. Inspect via MCP stdio server (v1 now aliases active_version_id: httpbin.heal_test.v2)
'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"capture_status","arguments":{"capture_id":"httpbin.heal_test.v1"}}}' | python D:\omniroute-monetizer\fleet\omniroute_mcp.py
```
