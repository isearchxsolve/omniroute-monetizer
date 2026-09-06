"""Update state/omni_video_routes.json: reclassify BUILD_TARGET rows with upstream evidence.

Evidence gathered 2026-09-06 (zero spend, all read-only probes):
- deepinfra: public /v1/openai/models lists google/veo-3.1, google/veo-3.1-fast,
  Wan-AI/Wan2.6-T2V with tags ['video-gen'] and per-second pricing. The installed
  native registry chunk predates them -> registry-patch + restart build stands.
  The stored deepinfra connection key is DEAD (401 same as bogus key) -> key wall.
- orcarouter: upstream /v1/models lists exactly the 8 kling ids with
  supported_endpoint_types ['openai-video']; /v1/videos endpoint exists (401 pattern).
  Stored key DEAD (401 Invalid API key) -> transport known, key wall.
- llm7: upstream /v1/models lists kling-v3.0-pro/turbo (model_type 'video',
  capabilities.video_generation true, video_async true); POST /v1/videos exists (401
  pattern vs 404 elsewhere). Stored key DEAD (invalid_api_key) -> transport known, key wall.
- ainative: upstream /v1/models (HTTP 200, 94 models) has ZERO video ids -> the
  'ainative/text-to-video-model' chat-catalog row is noise; not a video supply unit.

Idempotent, atomic write; secrets never written to the ledger.
"""
import json
import pathlib
import tempfile

P = pathlib.Path(r"D:\omniroute-monetizer\state\omni_video_routes.json")

doc = json.loads(P.read_text(encoding="utf-8"))
routes = doc["routes"]

updates = {
    # model-prefix -> (new status, error/rationale)
    "orcarouter/kling": (
        "BUILD_TARGET",  # stays a build target, but now with a NAMED transport
        "UPSTREAM-VERIFIED 2026-09-06: orcarouter /v1/models lists all 8 kling ids with "
        "supported_endpoint_types=['openai-video']; POST /v1/videos exists (401 pattern). "
        "Build = openai-video request-field mapping in the shim + registry add; BLOCKED by dead "
        "stored key (401 Invalid API key upstream). Needs fresh orcarouter key.",
    ),
    "llm7/kling-v3.0-pro": (
        "BUILD_TARGET",
        "UPSTREAM-VERIFIED 2026-09-06: llm7 /v1/models lists kling-v3.0-pro (model_type=video, "
        "video_generation+video_async true, $0.15/s pro tier). POST /v1/videos exists (401 vs 404 "
        "pattern). Build = /v1/videos request-field mapping + registry add; BLOCKED by dead stored "
        "key (invalid_api_key). Needs fresh llm7 key.",
    ),
    "llm7/kling-v3.0-turbo": (
        "BUILD_TARGET",
        "UPSTREAM-VERIFIED 2026-09-06: llm7 /v1/models lists kling-v3.0-turbo (model_type=video, "
        "video_generation+video_async true, $0.095/s). POST /v1/videos exists. Build = /v1/videos "
        "request-field mapping + registry add; BLOCKED by dead stored key (invalid_api_key).",
    ),
    "deepinfra/Wan-AI/Wan2.6-T2V": (
        "BUILD_TARGET",
        "UPSTREAM-VERIFIED 2026-09-06: deepinfra public /v1/openai/models lists Wan-AI/Wan2.6-T2V "
        "tags=['video-gen'] $0.10/output-sec. Installed native registry chunk predates the model "
        "(registry-patch + service restart build stands). Connection key also DEAD (401 = same as "
        "bogus key) -> needs fresh deepinfra key for the spend-gated validation.",
    ),
    "deepinfra/google/veo-3.1": (
        "BUILD_TARGET",
        "UPSTREAM-VERIFIED 2026-09-06: deepinfra public /v1/openai/models lists google/veo-3.1 "
        "tags=['video-gen'] $0.40/output-sec. #1674's 'likely catalog noise' is CORRECTED: the ids "
        "are real upstream video models; the installed registry chunk is stale. Build = registry "
        "patch + restart + format mapping; connection key DEAD (401).",
    ),
    "deepinfra/google/veo-3.1-fast": (
        "BUILD_TARGET",
        "UPSTREAM-VERIFIED 2026-09-06: deepinfra public /v1/openai/models lists google/veo-3.1-fast "
        "tags=['video-gen'] $0.15/output-sec. Registry chunk stale; build = registry patch + "
        "restart + format mapping; connection key DEAD (401).",
    ),
    "ainative/text-to-video-model": (
        "NOT_VIDEO",
        "UPSTREAM-VERIFIED 2026-09-06: ainative /v1/models (HTTP 200, 94 models) contains ZERO "
        "video ids and no 'text-to-video-model' entry - the chat-catalog row is classifier noise, "
        "not an upstream video route. No native adapter exists; reversible with rationale.",
    ),
}

changed = []
for r in routes:
    model = r.get("model", "")
    for prefix, (status, err) in updates.items():
        if model == prefix or model.startswith(prefix + " ") or (
            prefix.endswith("*") and model.startswith(prefix[:-1])
        ) or model == prefix.replace("*", ""):
            pass
    # exact matching below
for r in routes:
    model = r.get("model", "")
    if model in updates:
        status, err = updates[model]
        if r.get("status") != status or r.get("error") != err:
            r["status"] = status
            r["error"] = err
            r["probedAt"] = "2026-09-06T06:45:00Z"
            changed.append((model, status))

# orcarouter rows: match the 8 kling ids exactly
for r in routes:
    m = r.get("model", "")
    if m.startswith("orcarouter/kling/"):
        status, err = updates["orcarouter/kling"]
        if r.get("status") != status or r.get("error") != err:
            r["status"] = status
            r["error"] = err
            r["probedAt"] = "2026-09-06T06:45:00Z"
            changed.append((m, status))

doc["generatedAt"] = "2026-09-06T06:45:00Z"

tmp = P.with_suffix(".json.tmp")
tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
tmp.replace(P)

print(f"changed {len(changed)} rows:")
for m, s in changed:
    print(f"  {m} -> {s}")

from collections import Counter
print(Counter(r["status"] for r in routes))
