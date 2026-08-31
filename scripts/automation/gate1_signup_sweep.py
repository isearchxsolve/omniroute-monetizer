#!/usr/bin/env python3
"""Gate 1 orchestrator: per-profile onboarding matrix across ALL dedicated
automation seats (providers/9222, niloy/9223, seat2/9224, seat3/9225).

For every distinct account-less / unknown chat-or-AI provider surface present in
a seat, runs the corrected seat_signup_matrix.py (one bounded, read-only CDP
attach; never navigates an existing tab whose host is not the candidate) and
collects the terminal record. Video-only hosts (rtst.ai, akool.com, Flow project
tabs) are NOT driven through the Google-SSO executor -- they are recorded as
Gate-3 scope and resolved there. Walls are terminal evidence, never bypassed.

No Chrome is launched, no service is touched, the operator profile is never
attached (chrome_live_guard enforces this inside the executor).
"""
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
SYS = str(ROOT / "scripts" / "automation")
EXEC = str(ROOT / "scripts" / "automation" / "seat_signup_matrix.py")
OUT = ROOT / "state" / "gate1_matrix.json"
VIDEO_HOSTS = {"rtst.ai", "akool.com", "digen.ai", "veoaifree.com", "creen.ai",
               "magichour.ai", "heygen.com", "kie.ai", "aistudio.google.com",
               "labs.google"}

# (seat, port, provider_slug, url) -- distinct chat/AI candidates present per seat
CANDIDATES = [
    # providers / 9222
    ("providers", 9222, "copilot_microsoft", "https://copilot.microsoft.com/"),
    ("providers", 9222, "v0_vercel", "https://v0.app/"),
    ("providers", 9222, "gemini_google", "https://gemini.google.com/app"),
    ("providers", 9222, "puter", "https://puter.com/"),
    ("providers", 9222, "deepinfra", "https://deepinfra.com/chat"),
    ("providers", 9222, "poe", "https://poe.com/"),
    # niloy / 9223
    ("niloy", 9223, "v0_vercel", "https://v0.app/"),
    ("niloy", 9223, "duck_ai", "https://duck.ai/chat"),
    ("niloy", 9223, "poe", "https://poe.com/"),
    ("niloy", 9223, "chathub", "https://app.chathub.gg/"),
    ("niloy", 9223, "together_ai", "https://api.together.ai/signin"),
    ("niloy", 9223, "arena_lmsys", "https://arena.lmsys.org/"),
    ("niloy", 9223, "multiplechat", "https://multiplechat.com/"),
    ("niloy", 9223, "blackbox_ai", "https://www.blackbox.ai/"),
    ("niloy", 9223, "puter", "https://puter.com/"),
    ("niloy", 9223, "monica", "https://monica.im/"),
    ("niloy", 9223, "copilot_microsoft", "https://copilot.microsoft.com/"),
    ("niloy", 9223, "hyperbolic", "https://app.hyperbolic.ai/"),
    ("niloy", 9223, "claude_ai", "https://claude.ai/"),
    ("niloy", 9223, "cerebras", "https://chat.cerebras.ai/"),
    ("niloy", 9223, "groq", "https://console.groq.com/playground"),
    ("niloy", 9223, "you_com", "https://you.com/"),
    ("niloy", 9223, "phind", "https://www.phind.com/"),
    ("niloy", 9223, "coze", "https://www.coze.com/sign"),
    ("niloy", 9223, "aymo", "https://aymo.ai/signin"),
    ("niloy", 9223, "1min_ai", "https://1min.ai/"),
    ("niloy", 9223, "ai_sdk_dev", "https://ai-sdk.dev/playground"),
    ("niloy", 9223, "grok", "https://grok.com/"),
    ("niloy", 9223, "deepseek", "https://chat.deepseek.com/sign_in"),
    ("niloy", 9223, "qwen", "https://chat.qwen.ai/"),
    ("niloy", 9223, "cohere", "https://dashboard.cohere.com/welcome/login"),
    ("niloy", 9223, "mistral", "https://chat.mistral.ai/chat"),
    ("niloy", 9223, "meta_ai", "https://www.meta.ai/"),
    ("niloy", 9223, "gemini_google", "https://gemini.google.com/app"),
    ("niloy", 9223, "chatgpt", "https://chatgpt.com/"),
    ("niloy", 9223, "sambanova", "https://cloud.sambanova.ai/chat"),
    ("niloy", 9223, "deepinfra", "https://deepinfra.com/chat"),
    ("niloy", 9223, "perplexity", "https://www.perplexity.ai/"),
]


def run_one(seat, port, slug, url, timeout=170):
    art = ROOT / "state" / f"signup_resolution_{seat}_{slug}.json"
    cmd = [sys.executable, EXEC, "--port", str(port), "--seat", seat,
           "--provider", slug, "--url", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(ROOT))
        out = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return {"seat": seat, "provider": slug, "url": url,
                "terminal_state": "TIMEOUT", "detail": f">{timeout}s"}
    except Exception as e:
        return {"seat": seat, "provider": slug, "url": url,
                "terminal_state": f"ERR_{type(e).__name__}", "detail": str(e)[:160]}
    rec = {"seat": seat, "provider": slug, "url": url,
           "cmd_out": (out or "").strip()[-200:]}
    if art.exists():
        try:
            rec["artifact"] = json.loads(art.read_text(encoding="utf-8"))
            rec["terminal_state"] = rec["artifact"].get("terminal_state")
        except Exception:
            pass
    else:
        rec["terminal_state"] = rec.get("terminal_state") or "NO_ARTIFACT"
    return rec


def main():
    results = []
    for seat, port, slug, url in CANDIDATES:
        if any(v in url for v in VIDEO_HOSTS):
            results.append({"seat": seat, "provider": slug, "url": url,
                            "terminal_state": "VIDEO_SEAT_GATE3"})
            continue
        rec = run_one(seat, port, slug, url)
        results.append(rec)
        # incremental write so evidence survives interruption
        OUT.write_text(json.dumps(
            {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "note": "Gate 1 per-profile onboarding matrix across all seats",
             "results": results}, indent=2), encoding="utf-8")
        ts = rec.get("terminal_state")
        print(f"[{seat}/{slug}] -> {ts}", flush=True)
    # tally
    from collections import Counter
    tally = Counter(r.get("terminal_state") for r in results)
    doc = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "note": "Gate 1 per-profile onboarding matrix across all seats",
           "tally": dict(tally), "results": results}
    OUT.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print("GATE1 TALLY:", json.dumps(tally))


if __name__ == "__main__":
    main()
