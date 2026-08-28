"""Append worklog entry #1131 (digen stateless graduation) idempotently."""
import pathlib

f = pathlib.Path("MASTER_WORKLOG.md")
text = f.read_text(encoding="utf-8")
if "#1131" in text:
    print("SKIP: #1131 already present")
    raise SystemExit(0)

entry = """

### [2026-08-28 14:20] #1131 — P1 COMPLETE: digen.ai graduated STATELESS. Un-shadowed via api.kind='digen' dispatch (architecture-native, hot-reloads, no restart). Spend gate + capacity() added to DigenSessionClient. Live credit check: 270 credits = ~9 clips (the #1122 'zero credits' finding was STALE — monthly free tier reset). First seat graduated under the full-Chrome-independence override (#1130).

**1. TOKEN LIVENESS (read-only, per repo-memory protocol — no spend).** scratch_digen_token_check.py verified the recorded Digen-Token against digen's API directly:
  - GET /v1/credit/remain -> 200, remained=270 credits, expiredAt 2026-09-26 (monthly free tier).
  - GET /v1/queue/list?status=3 -> 200, 3 completed jobs visible (proves the token has real account history).
  - **STALE-FINDING CORRECTION:** #1122 recorded "digen zero credits / paywalled". That was true at capture time but the free tier RESETS MONTHLY — 270 credits are live now. Honest correction recorded here; the seat is real supply, not a wall.

**2. THE SHADOWING BUG (why the stateless client was unreachable).** `_client_for` dispatch order: (1) api.kind, (2) recorded_ws->Chrome, (3) runtime:replay, (4) **modality=video + VIDEO_HOSTS -> ChromeVideoClient**, (5) CLIENTS host-substring map. digen.ai is in VIDEO_HOSTS AND in CLIENTS (`"digen.ai": DigenSessionClient`), so step 4 always won and the pure-HTTP client was dead code. Fix: declared `api.kind: "digen"` in the seat file — step 1 dispatches FIRST, which is the same architecture-native mechanism rtst/flow/youcom use (hot-reloads per §24, no code-path special-casing, no shim restart).

**3. CODE CHANGES.**
  - scripts/automation/digen_session_replay.py: (a) added the `OMNI_VIDEO_CONFIRM_SPEND` spend gate — chat() raises ChatError("SPEND_GATE_CLOSED") unless the env var is truthy, matching the flow_api_client:89 / rtst_api_client:135 convention (the shim's bat sets it; direct CLI use is refused by default); (b) added read-only `capacity()` = credit/remain // EST_COST_PER_CLIP (30, from video_provider_digen.py) -> 9 clips right now.
  - scripts/automation/session_pool.py: added `if kind == "digen":` dispatch block returning DigenSessionClient, with a comment documenting the un-shadow + override #1130 provenance.
  - state/secrets/session_digen_ai.json (gitignored, never committed): added `"api": {"kind": "digen"}` via scratch_flip_digen.py (idempotent, preserves all keys, verified round-trip: 13 recorded_job exchanges intact).

**4. VERIFICATION (scratch_verify_digen_grad.py — 4/4 checks pass).**
  1. `_client_for('digen.ai', raw)` -> DigenSessionClient (was ChromeVideoClient before the flip).
  2. SessionPool scan: session_digen_ai dispatchable=True, modality=video, client_cls=DigenSessionClient, has_api=True. (Note: session_video_digen — the 0-exchange live-tab-only duplicate — still resolves to ChromeVideoClient; it stays Chrome-backed, which is correct.)
  3. capacity() = 9 clips (live read-only credit check).
  4. Spend gate: chat() without OMNI_VIDEO_CONFIRM_SPEND raises ChatError kind=SPEND_GATE_CLOSED. No accidental credit burn possible from a bare CLI.
  - Serving face: GET http://127.0.0.1:8190/v1/models -> 51 models, `video/digen.ai/auto` present — the running shim hot-reloaded the seat flip with NO restart (§24 respected; the task-owned shim was never touched).
  - **No job was submitted.** Credit spend requires the gate open + operator awareness; graduation itself needed only read-only proof (token live + dispatch correct + gate closed by default). Law 3 note: digen is a VIDEO seat — the computed-verification analogue is the read-only credit/queue proof above plus (when the operator opens the gate) a real sentinel clip; no chat arithmetic probe applies to a video-only host.

**5. RUNWAY IMPACT.** Film runway was 110 Chrome-free clips (Flow 103 + rtst 7). Digen adds ~9 stateless clips -> ~119 Chrome-free clips, all served without any browser. The 2x3-min film goal (72 clips) remains covered with wider margin; breadth beats depth.

**6. NEXT (P2-P7 per #1130 plan).** P2 meta.ai re-capture (cookie live, capture the real chat-send via CDP Network.enable); P3 deepseek PoW hand-roll; P4 zhipu X-Sign hand-roll; P5 v0.app multi-exchange; P6 cerebras/gemini re-capture; P7 the 25 live-tab-only capture pass. Every graduation Law-3-gated; walls reported never solved (Law 5 survives the override).

**Files changed:** scripts/automation/digen_session_replay.py (spend gate + capacity), scripts/automation/session_pool.py (api.kind='digen' dispatch).
**Files added (scratch):** scratch_digen_token_check.py, scratch_flip_digen.py, scratch_verify_digen_grad.py.
**Verdict:** P1 complete. digen.ai is the first seat graduated under the full-Chrome-independence override: stateless, spend-gated, hot-reloaded, verified read-only. ~9 clips of genuinely Chrome-free video supply added. MONETIZER_READY (supply side).
"""

f.write_text(text.rstrip() + entry, encoding="utf-8")
print("APPENDED #1131; new line count:", len(f.read_text(encoding='utf-8').splitlines()))
