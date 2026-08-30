# OmniRoute Readiness Handoff

## Certified chat routing state

The chat-side OmniRoute Monetizer was certified on 2026-08-30 by
`python acceptance_tests.py`: **20 passed, 0 failed, `MONETIZER_READY`**.

Verified operational contracts:

- `/v1/models` serves the live catalog (9,450 models at certification).
- Management routes require authentication.
- `frontier`, `auto/pro-coding`, `auto/pro-reasoning`, and `auto/pro-chat` each completed a live inference request.
- `frontier` produced OpenAI-compatible SSE frames and a terminal `[DONE]` event.
- `auto/pro-coding` produced an OpenAI-compatible function `tool_calls` response.
- ZCode and VS Code configuration point at OmniRoute.

## Combo repair and restore point

The previous cascades included unavailable or non-working heads. Before any update, all 16
current combos were backed up through the native management API:

`state/combo_backups/combos_20260830T055047Z.json`

Seven combos were then non-destructively reordered through the supported API. No entry was
deleted; models that failed a probe remain as tails. Verified heads include:

| Combos | Current verified head order |
| --- | --- |
| `frontier`, `Frontier Max`, `fusion-coder`, `auto/pro-coding`, `auto/best-coding` | `codex/gpt-5.6-sol` then `mistral/codestral-2508` |
| `auto/free-chat` | `cloudflare-ai/@cf/meta/llama-3.2-3b-instruct` then `codex/gpt-5.6-sol` |
| `auto/qual-noplus` | `agy/gemini-3.6-flash-high` then `cohere/c4ai-aya-expanse-32b` |

The probe accepts both regular OpenAI JSON and SSE replies. This matters because the installed
OmniRoute may send `text/event-stream` even when a client requests `stream: false`.

## Evidence artifacts

- `state/supervisor_status_v2.json` — authoritative app-health report, isolated from the legacy writer race.
- `state/fleet_provider_audit.json` — sanitized native connection tests (71 valid of 117 at the audit time).
- `state/omniroute_combo_catalog_audit.json` — configured-model versus live-catalog drift.
- `state/combo_optimization.json` — last live probe/order result.
- `state/omniroute_contract_probe.json` — streaming and function-tool protocol result.
- `state/video_capability_audit.json` — redacted, read-only video inventory.

## Video boundary

The local video router is healthy and its inventory is visible without spend. Its live quote and
generation paths can drive existing browser tabs. Those tabs are adjacent to the currently parked
seat/Chrome layer, so no new quote or generation job was submitted during this work.

This handoff therefore certifies **chat routing**, not a newly generated video. The video inventory
must not be mistaken for a current paid-generation test.

## Safe recurring checks

```powershell
python scripts/automation/omni_supervisor.py --once --json
python scripts/automation/omniroute_capability_matrix.py
python scripts/automation/omniroute_contract_probe.py
python scripts/automation/video_capability_audit.py
python acceptance_tests.py
```

Do not run a video quote or generation from this handoff without first re-evaluating the Chrome
and seat-layer boundary in `CHROME_RULES_FOR_AGENTS.md`.
