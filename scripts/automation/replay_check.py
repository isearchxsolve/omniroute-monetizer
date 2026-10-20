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
import hashlib
import json
import os
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

# Multi-step agent pipelines (measured 2026-09-06, worklog #1679): a 200 whose body is an SSE
# agent-project stream (genspark ask_proxy: project_start + keepalive events, answer arrives
# minutes later) or a completed planner envelope (giz inferenceServer.infer: status completed +
# output object, the answer lives in a follow-up render leg the single exchange never sees).
# Neither is a wall nor a dead end -- the single-exchange replay transport simply cannot carry
# them. The label names the transport to build (Doctrine 3a).
PIPELINE_MARKERS = ('"project_start"', '"notification_type": "keepalive"', '"mediatool"')


def looks_like_pipeline(low: str) -> bool:
    if any(m in low for m in PIPELINE_MARKERS):
        return True
    # giz planner shape: a COMPLETED status envelope whose output is routing metadata, not text
    if '"status": "completed"' in low or '"status":"completed"' in low:
        return '"output"' in low and '"responseformat"' in low


def apply_pipeline_override(verdict: str, detail: str, raw: str) -> tuple[str, str]:
    """Classify an unparsed agent stream without hiding an explicit wall.

    A provider can return a project/keepalive stream whose extracted assistant text is
    itself a quota or plan refusal.  The explicit wall is stronger evidence than the
    transport marker and must remain WALL; only an otherwise unanswered stream becomes
    the PIPELINE build target.
    """
    if verdict == "NO_ANSWER" and looks_like_pipeline((raw or "").lower()):
        return "PIPELINE", ("raw body is an agent/planner stream -- multi-step build "
                             "target, not a wall")
    return verdict, detail


def http_status_in(text: str) -> int | None:
    """Pull the status out of a stringified requests error, e.g. "409 client error: conflict"."""
    m = re.search(r"\b([1-5]\d\d)\s+(?:client|server)\s+error", text)
    return int(m.group(1)) if m else None


def keyword_in_body(raw: str, expect: str) -> bool:
    """THE fundamental verdict, spoken in the one protocol every browser shares: did the
    response body the browser would have received actually contain the answer?

    The browser is a generic HTTP client -- it never special-cases a site, it re-sends the
    request and reads the response. So replayability reduces to: is the EXACT phrase in the
    body? The phrase is a pure character string the model is asked to REPEAT, never something
    it could generate on its own, so its presence is proof of a real model reply.

    Handles streamed responses: the phrase may be split across SSE chunks, JSON objects, or
    escaped sequences. We flatten the raw body to just lowercase letters and spaces, then
    search for the flattened phrase. This cuts through all framing (SSE `data:` prefixes,
    JSON quotes/escapes, chunk boundaries) to the actual text content.
    """
    if not raw or not expect:
        return False
    # A raw-body fallback is intentionally unavailable for numeric answers.  The
    # earlier normalisation removed every digit from ``"58"``, producing an empty
    # expected string; in Python, ``"" in any_nonempty_string`` is true.  That
    # could promote any non-empty unparsed provider response to REPLAY_OK.  A
    # numeric Law-3 probe still passes normally when UniversalSessionClient has
    # structurally extracted the answer, but a parser-blind raw response must be
    # fixed rather than certified from an ID, timestamp, byte count, or error body.
    #
    # The alphabetical exact-phrase probe remains available for carefully
    # scoped parser diagnostics.  It has at least one meaningful letter after
    # normalisation and therefore cannot collapse into a vacuous match.
    if not re.search(r"[a-z]", expect, flags=re.IGNORECASE):
        return False
    # Flatten both to just letters and spaces -- strips SSE framing, JSON structure, escapes,
    # chunk boundaries, punctuation. The phrase "the holy cow jumps over the stricks" becomes
    # "the holy cow jumps over the stricks" regardless of how it was chunked or encoded.
    flat_raw = re.sub(r"[^a-z ]", " ", raw.lower())
    flat_raw = re.sub(r"  +", " ", flat_raw)
    flat_expect = re.sub(r"[^a-z ]", " ", expect.lower()).strip()
    flat_expect = re.sub(r"  +", " ", flat_expect)
    return flat_expect in flat_raw


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
    if looks_like_pipeline(low):
        return "PIPELINE", ("200 agent/planner stream -- multi-step build target, not a wall "
                            "(submit+poll transport needed)")
    # A 403 is ambiguous: it can be an expired/forbidden credential, but
    # providers also use it for exhausted trials and plan gates.  A named wall
    # in the body is stronger evidence than the generic status code.  A 401,
    # or explicit auth text, remains an authentication failure.
    if any(w in low for w in AUTH_TEXT) or status == 401:
        return "AUTH", f"auth refused ({status or 'in body'}) -- cookie alone is not enough"
    if status == 429 or "rate limit" in low or "too many requests" in low:
        return "RATE", f"rate limited ({status or 'in body'}) -- left alone, not retried"
    if any(w in low for w in WALL_HINTS):
        return "WALL", "wall text in reply -- left alone, not retried"
    if status == 403:
        return "AUTH", "auth refused (403) -- cookie alone is not enough"
    # A multistep client can reject its own capture before contacting a provider
    # (for example V0's one-leg artifact has no conversation id).  These are
    # capture/adapter defects, not evidence that a provider consumed a nonce.
    if low.startswith("v0_") or "v0_no_chat_id" in low:
        return "BAD_FILE", "V0 replay adapter could not derive a conversation id from the capture"
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
    # A numeric computed probe has a deliberately narrow success surface: the
    # extracted model text must be the requested number (with at most harmless
    # trailing terminal punctuation).  Matching a standalone 58 inside an
    # arbitrary error/metadata string would recreate the false-supply bug this
    # check exists to prevent.
    if expect.isdigit():
        numeric_answer = re.fullmatch(rf"\s*{re.escape(expect)}\s*[.!]?\s*", text or "")
        if not numeric_answer:
            # Narrow rescue for real models that ignore the "only the number" instruction yet
            # verifiably answered. Two shapes observed live (2026-08-30): the reply OPENS with the
            # exact value before UI noise ("58what is 58 times 3...", Perplexity), or it restates
            # the arithmetic in reasoning and then answers ("okay, the user is asking for the
            # number 41 ... 58", 1min.AI). Both prove live supply. Neither can fire on an error
            # body or an id: a standalone word-bounded token plus the literal restated arithmetic
            # does not occur in timestamps, hashes, or server metadata.
            if re.match(rf"\s*{re.escape(expect)}(?!\d)", text or ""):
                return "REPLAY_OK", f"reply opens with the computed value ({low[:60]})"
            if re.search(r"41\s*\+\s*17|41 plus 17|41 and 17", low) and \
                    re.search(rf"(?<!\d){re.escape(expect)}(?!\d)", text or ""):
                return "REPLAY_OK", f"restated arithmetic + computed value ({low[:60]})"
            return "NO_ANSWER", f"200 but the extracted reply is not only {expect!r}: {low[:90]}"
    elif expect not in low:
        return "NO_ANSWER", f"200 but the reply never contains {expect!r}: {low[:90]}"
    return "REPLAY_OK", low[:140]


def replay(path: pathlib.Path, prompt: str, expect: str) -> dict[str, Any]:
    row: dict[str, Any] = {"file": path.name}
    attempt_id = os.environ.get("OMNI_GRADUATION_ATTEMPT_ID", "")
    row["attemptId"] = attempt_id
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        row.update(host="?", verdict="ERROR", detail=f"unreadable: {type(e).__name__}")
        return row

    row["host"] = payload.get("host") or "?"
    row["inputArtifactSha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    rec = payload.get("recorded_exchange") or {}
    row["recordedUrl"] = str(rec.get("url") or "")[:120]
    row["bodyBytes"] = len(str(rec.get("request_body") or ""))

    started = time.perf_counter()
    try:
        from universal_replay import make_session_client
        # The PATH, not the parsed dict: providers that rotate their session cookie on use expect the
        # new one next time, and the client can only write the rotation back if it knows the file.
        # Handing it the dict silently throws the rotation away and the next call arrives stale.
        # The factory routes on transport: HTTP sessions get UniversalSessionClient, a capture
        # whose exchange left over a websocket gets the ws adapter (Chrome-gap doctrine).
        client = make_session_client(path)
        res = client.chat([{"role": "user", "content": prompt}])
        text = str((res or {}).get("text") or "")
        status = (res or {}).get("status")
        raw = str((res or {}).get("raw") or "")
        verdict, detail = classify(text, status if isinstance(status, int) else None, None, expect)
        # Raw envelopes may contain the expected number in token counts, IDs,
        # titles, or error metadata. Only extracted assistant text can prove a
        # completion; a raw match is diagnostic evidence, never admission.
        verdict, detail = apply_pipeline_override(verdict, detail, raw)
    except Exception as e:                        # a replay failure is data, never a crash
        text, status = "", None
        # Preserve failure classification without treating raw exception data
        # or the exception message itself as a completed assistant answer.
        raw_status = getattr(e, "status", None)
        # HTTP refusals carry useful, non-secret evidence in the response body.  Prefer that body
        # for classification (e.g. a 403 CAPTCHA is WALL, while a 403 with no named wall is AUTH),
        # falling back to the exception text for transports that have no response at all.  This
        # keeps the exact provider status without ever treating exception text as assistant output.
        raw_body = getattr(e, "raw", None)
        if isinstance(raw_body, str) and raw_body:
            verdict, detail = classify(raw_body, raw_status, None, expect)
        else:
            verdict, detail = classify(str(e), raw_status, None, expect)
        if verdict == "REPLAY_OK":
            # Exception text itself is not an assistant response, even if it
            # happens to equal the expected answer.
            verdict, detail = "ERROR", "client raised before producing an assistant response"
    row["latencyMs"] = round((time.perf_counter() - started) * 1000)
    row["verdict"] = verdict
    row["detail"] = detail
    # Bind the actual post-execution artifact: clients may legitimately rotate cookies.
    # This metadata is local evidence, never a substitute for a provider answer.
    row["artifactSha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    row["verification"] = {"version": "terminal-exact-v1", "prompt": prompt,
                           "expected": expect, "exactAnswer": verdict == "REPLAY_OK" and text.strip() == expect}
    return row


def main() -> int:
    # Verdict details carry raw provider text (Chinese providers reply in CJK). Under a Windows
    # cp1252 pipe a plain print() of such text raises UnicodeEncodeError and the whole check
    # dies mid-run -- replace un-encodable characters instead of losing the report.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    # EXACT-RESPONSE SENTINEL: a pure character phrase, not a number. Numbers hide inside ids,
    # timestamps, hashes, and split across stream chunks (Mistral's "5"+"8" proved it). A nonsense
    # phrase cannot appear in any UUID, hash, timestamp, byte count, or server-generated title --
    # so its presence in the response body is unambiguous proof the model answered. We ask the
    # model to REPEAT the exact phrase, so the verdict is a plain exact-string search over the
    # full response surface.
    ap.add_argument("--prompt",
                    default="Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks")
    ap.add_argument("--expect", default="the holy cow jumps over the stricks",
                    help="exact phrase the reply must contain; a pure character string that cannot "
                         "collide with any id, hash, timestamp, or title")
    ap.add_argument("--only", default="", help="comma-separated host substrings")
    ap.add_argument("--secrets-dir", type=pathlib.Path, default=SECRETS,
                    help="directory containing candidate session_*.json files (default: active state/secrets)")
    ap.add_argument("--out", type=pathlib.Path, default=OUT,
                    help="non-secret replay report path (default: state/replay_check.json)")
    a = ap.parse_args()

    files = sorted(a.secrets_dir.glob("session_*.json"))
    if a.only:
        want = [s.strip().lower() for s in a.only.split(",") if s.strip()]
        files = [f for f in files if any(w in f.name.lower() for w in want)]
    if not files:
        print(f"no session_*.json in {a.secrets_dir}")
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

    # ONE ROW PER HOST. Two session files can carry the same host -- chatgpt.com arrived via
    # BOTH session_chatgpt_free_web.json and session_chatx.json, and veoaifree.com has a WALL
    # row plus a REPLAY_OK row. results[] is consumed per-host (chat_pool_server keys off it),
    # so duplicates became phantom duplicate providers in the pool. Keep the best verdict per
    # host: REPLAY_OK outranks everything (proven supply must not be hidden by its sibling's
    # wall/auth row); among equal verdicts the first file wins, which keeps runs deterministic.
    _rank = {"REPLAY_OK": 0, "SINGLE_USE": 1, "RATE": 2, "AUTH": 3, "WALL": 4}
    best: dict[str, dict] = {}
    for row in rows:
        host = str(row.get("host") or "")
        prior = best.get(host)
        if prior is None or _rank.get(row.get("verdict"), 9) < _rank.get(prior.get("verdict"), 9):
            best[host] = row
    rows = list(best.values())

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
    a.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = a.out.with_suffix(a.out.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(a.out)

    print(f"\nreplayable      ({len(set(ok))}): {', '.join(sorted(set(ok))) or 'none'}")
    print(f"single-use bound({len(set(single))}): {', '.join(sorted(set(single))) or 'none'}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
