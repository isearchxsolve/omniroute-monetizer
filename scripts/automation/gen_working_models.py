"""Generate WORKING_MODELS.md -- the definitive working-models list for the operator."""
import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
d = json.loads((ROOT / "state" / "healthy_provider_models_rescan.json").read_text(encoding="utf-8"))
ok = [r for r in d["results"] if r.get("valid")]
by = collections.defaultdict(list)
for r in ok:
    by[r["provider"]].append(r["model"])

vid = json.loads((ROOT / "state" / "video_proofs" / "proof_report.json").read_text(encoding="utf-8"))
vr = vid["results"][0] if vid.get("results") else {}

L = []
A = L.append
A("# WORKING MODELS LIST")
A("")
A("Generated from measured probes, not from catalogue listings. A route counts as working only")
A("when the model returned real generated content.")
A("")
A("## The short answer")
A("")
A(f"- **Chat / text: {len(ok)} routes work**, across **{len(by)} providers**.")
A("- **Video: 0 routes proven.** See below -- this is the current focus.")
A("")
A(f"Chat source: `state/healthy_provider_models_rescan.json`, probed {d['generatedAt'][:16]} UTC.")
A(f"{d['totalConnections']} connections tested, {d['healthyConnectionCount']} healthy,")
A(f"{d['candidateModelRouteCount']} candidate routes tried, {len(ok)} confirmed by a real completion.")
A("")
A("## VIDEO -- the current focus")
A("")
A("**Proven working video models: 0.** Only one video generation has ever been attempted:")
A(f"`{vr.get('model')}` on {vid.get('generated','')[:10]}, which returned")
A(f"HTTP {vr.get('generate_status')} -- \"{vr.get('detail','')}\". No other video model has been tried.")
A("")
A("Video models that EXIST and are already wired -- the ones to prove next:")
A("")
A("| provider | connection | video models |")
A("|---|---|---|")
A("| **segmind** | ACTIVE, key stored | `wan2.1-t2v`, `wan2.7-i2v`, `hunyuan-video-t2v`, "
  "`ltx-video-t2v`, `kling-video-t2v` |")
A("| kie | ACTIVE | **none mapped** -- its 17 routes are Claude/GPT/Gemini text plus 6 ElevenLabs "
  "audio models. The `grok-imagine/text-to-video` route that was tried is not in OmniRoute's kie "
  "catalogue at all. |")
A("| fal-ai | **INACTIVE** | none -- all 12 routes are image-only (flux, seedream, ideogram, recraft) |")
A("| pollinations | ACTIVE | image only (`zimage`, `qwen-image-3`, `grok-imagine-image-2.0`); the "
  "`pollinations-video` handler is missing in OmniRoute |")
A("")
A("**So segmind is the only provider with real text-to-video routes wired and ready to test.**")
A("Five of its eleven routes are video; the other six are image (flux, sdxl, sd3.5, kandinsky).")
A("")
A("## CHAT / TEXT -- confirmed working, by provider")
A("")
A("Use these exactly as written, including the provider prefix.")
A("")
for prov in sorted(by, key=lambda p: -len(by[p])):
    A(f"### {prov} ({len(set(by[prov]))})")
    for m in sorted(set(by[prov])):
        A(f"- `{prov}/{m}`")
    A("")

(ROOT / "WORKING_MODELS.md").write_text("\n".join(L), encoding="utf-8")
print(f"wrote WORKING_MODELS.md: {len(L)} lines, {len(ok)} routes, {len(by)} providers")
