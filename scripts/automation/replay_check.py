#!/usr/bin/env python3
"""Does a captured session actually REPLAY? One request per session file, serial, no retries.

This is the question that decides whether capture count means anything. A capture proves the
browser made a request we could see; it does not prove that request can be re-sent. Two captures
already failed on re-send for the same underlying reason -- the body carried single-use state:

    deepseek  {"code":40301,"msg":"INVALID_POW_RESPONSE"}   proof-of-work token, spent
    qwen      {"code":"internal_error"}                     looks like a one-shot chat/message id

So the verdicts here are about REPLAYABILITY, not about whether the site works:

    REPLAY_OK      answered, and the answer is not an error shape       -> real supply
    SINGLE_USE     rejected in a way that names a nonce/pow/token/id    -> needs a live browser
    AUTH           401/403 -- cookie no longer accepted
    WALL           credits/quota/captcha -- STOP, never hammered
    RATE           429
    HTTP_<code>    rejected, reason not classifiable
    ERROR          transport failure

Costs nothing on any paid route: this talks to the provider directly, not through OmniRoute.
No cookie, token or nonce is printed -- only the host, the verdict, and a short reply excerpt.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SECRETS = ROOT / "state" / "secrets"
OUT = ROOT / "state" / "replay_check.json"

sys.path.insert(0, str(HERE))

# Substrings that mean "the body carried state that was already spent". This is the verdict worth
# the script: it separates "this provider is dead to us" from "this provider needs a live browser
# per call", which are completely different answers for the pipeline.
SINGLE_USE_HINTS = ("pow", "proof_of_work", "nonce", "invalid_token", "csrf", "signature",
                    "expired", "already", "duplicate", "invalid_request_id", "chat_id",
                    "message_id", "not found", "internal_error", "invalid_param")

WALL_HINTS = ("credit", "quota", "billing", "payment", "captcha", "upgrade", "subscribe",
              "limit reached", "insufficient")

# The replay client hands failures back as TEXT rather than raising, so an HTTP 401 arrives as a
# string like "auth rejected: {"error":"unauthorized"}" with no status field. Scored on the text or
# the check declares dead routes healthy -- the precise way this repo's registry came to claim 88
# working routes when 15 answered.
AUTH_TEXT = ("unauthorized", "not authenticated", "forbidden", "auth rejected", "invalid api key",
             "invalid token", "login required", "please log in", "session expired")


def http_status_in(text: str) -> int | None:
    """Pull the status out of a stringified requests error, e.g. "409 client error: conflict"."""
    m = re.search(r"\b([1-5]\d\d)\s+(?:client|server)\s+error", text)
    return int(m.group(1)) if m else None


def classify(text: str, status: int | None, err: str | None, expect: str = "58") -> tuple[str, str]:
    low = (text or "").lower()
    if err:
        return "ERROR", err[:140]
    # Checked before anything else: these are OUR file's problem, not the provider's, and
    # SENTINEL_NOT_FOUND contains the substring "not found" which would otherwise be read as a
    # provider rejecting a stale id.
    if "sentinel_not_found" in low or "sentinel not found" in low:
        return "BAD_FILE", "no sentinel in the recorded body -- capture is not replayable at all"
    # The extractor now refuses to pass an unparseable body off as a model reply, so these arrive as
    # errors rather than as false answers. They are not HTTP failures and must not be scored as such.
    if "unparseable_html" in low:
        return "HTML_PAGE", "served an HTML page, not an API response -- not supply"
    if "unparseable" in low:
        return "UNPARSEABLE", "200 but no recognised response shape -- not scored as an answer"
    status = status or http_status_in(low)
    if any(w in low for w in AUTH_TEXT) or status in (401, 403):
        return "AUTH", f"auth refused ({status or 'in body'}) -- cookie alone is not enough"
    if status == 429 or "rate limit" in low or "too many requests" in low:
        return "RATE", f"rate limited ({status or 'in body'}) -- left alone, not retried"
    if any(w in low for w in WALL_HINTS):
        return "WALL", "wall text in reply -- left alone, not retried"
    if status and status >= 400:
        hint = next((h for h in SINGLE_USE_HINTS if h in low), None)
        if hint:
            return "SINGLE_USE", f"http {status}, matched {hint!r}"
        return f"HTTP_{status}", low[:140]
    hint = next((h for h in SINGLE_USE_HINTS if h in low), None)
    if hint and len(low) < 400:
        return "SINGLE_USE", f"matched {hint!r} in a short body"
    if not low.strip():
        return "EMPTY", "200 but nothing in the body"
    # A pass has to show the model actually answered. The check word must be something the model
    # COMPUTES, never something it can echo: with the earlier prompt "Reply exactly one word:
    # Verified", aymo.ai answered "Confirmed." (a reasonable reading of an ambiguous instruction, so
    # a live provider scored as failing) while chat.mistral.ai's server generated a chat *title*
    # containing the asked word, so a bootstrap response with no answer in it scored as passing.
    # An arithmetic result appears in neither an echo nor a title.
    if expect not in low:
        return "NO_ANSWER", f"200 but the reply never contains {expect!r}: {low[:90]}"
    return "REPLAY_OK", low[:140]


def replay(path: pathlib.Path, prompt: str, expect: str) -> dict[str, Any]:
    row: dict[str, Any] = {"file": path.name}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        row.update(host="?", verdict="ERROR", detail=f"unreadable: {type(e).__name__}")
        return row

    row["host"] = payload.get("host") or "?"
    rec = payload.get("recorded_exchange") or {}
    row["recordedUrl"] = str(rec.get("url") or "")[:120]
    row["bodyBytes"] = len(str(rec.get("request_body") or ""))

    started = time.perf_counter()
    try:
        from universal_replay import UniversalSessionClient
        # The PATH, not the parsed dict: providers that rotate their session cookie on use expect the
        # new one next time, and the client can only write the rotation back if it knows the file.
        # Handing it the dict silently throws the rotation away and the next call arrives stale.
        client = UniversalSessionClient(path)
        res = client.chat([{"role": "user", "content": prompt}])
        text = str((res or {}).get("text") or "")
        status = (res or {}).get("status")
        verdict, detail = classify(text, status if isinstance(status, int) else None, None, expect)
    except Exception as e:                        # a replay failure is data, never a crash
        text, status = "", None
        verdict, detail = classify(str(e), None, None, expect)
        if verdict == "ERROR":
            verdict, detail = classify(str(e), 400, None, expect)
    row["latencyMs"] = round((time.perf_counter() - started) * 1000)
    row["verdict"] = verdict
    row["detail"] = detail
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prompt", default="Reply with only the number: 41 + 17")
    ap.add_argument("--expect", default="58",
                    help="token the reply must contain; must be COMPUTED by the model, never a word "
                         "it could echo from the prompt or a server-generated chat title")
    ap.add_argument("--only", default="", help="comma-separated host substrings")
    a = ap.parse_args()

    files = sorted(SECRETS.glob("session_*.json"))
    if a.only:
        want = [s.strip().lower() for s in a.only.split(",") if s.strip()]
        files = [f for f in files if any(w in f.name.lower() for w in want)]
    if not files:
        print(f"no session_*.json in {SECRETS}")
        return 1

    print(f"replay check: {len(files)} captured sessions, direct to provider, 1 request each\n")
    rows = []
    for f in files:
        row = replay(f, a.prompt, a.expect)
        rows.append(row)
        mark = "OK " if row["verdict"] == "REPLAY_OK" else "   "
        print(f"  {mark}{row['host'][:32]:32s} {row['verdict']:12s} "
              f"{row['latencyMs']:6d}ms  {row['detail'][:70]}")

    ok = [r["host"] for r in rows if r["verdict"] == "REPLAY_OK"]
    single = [r["host"] for r in rows if r["verdict"] == "SINGLE_USE"]
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "question": "does a captured browser request survive being re-sent from python?",
        "results": rows,
        "summary": {
            "replayable": sorted(set(ok)),
            "singleUseBound": sorted(set(single)),
            "other": sorted({r["host"] for r in rows
                             if r["verdict"] not in ("REPLAY_OK", "SINGLE_USE")}),
        },
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nreplayable      ({len(set(ok))}): {', '.join(sorted(set(ok))) or 'none'}")
    print(f"single-use bound({len(set(single))}): {', '.join(sorted(set(single))) or 'none'}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
