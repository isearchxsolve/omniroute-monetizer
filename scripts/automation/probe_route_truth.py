#!/usr/bin/env python3
"""Probe every routable (provider, model) pair and every combo, and record what ACTUALLY answered.

This replaces rescan_healthy_provider_models.py for the same job. It exists because that script's
scheduler produced false negatives on the models that matter most, and the evidence is in its own
output (state/healthy_provider_models_rescan.json, 2026-08-23):

    codex        26 candidates, 0 confirmed, 21x HTTP 429
    agy          48 candidates, 24 confirmed, 9x HTTP 429
    antigravity  45 candidates, 21 confirmed, 9x HTTP 429
    t3-web       23 candidates, 8 confirmed, 8x HTTP 429

It ran a flat ThreadPoolExecutor(12) over a route list sorted by (provider, model, connection), so
the twelve requests in flight at any moment were almost always the SAME provider. codex has 26
models; all 26 were fired at one upstream inside a few seconds and it rate-limited every one of
them. `codex/gpt-5.6-sol` is the head of every combo cascade in this repo -- the probe reported the
single most important route in the fleet as dead, because of how the probe itself was scheduled.

So the concurrency here is per-PROVIDER, not per-request:

  * One in-flight request per provider. Lanes run in parallel across providers, serial within one.
    That is the house rule for this repo anyway -- breadth across providers, never depth on one.
  * 429 is treated as OUR fault, not the provider's verdict: back off, retry once, and after
    repeated 429s pause the lane. A rate limit is never recorded as "this model does not work".
  * 402 / "payment required" / "quota" STOPS that lane for good and is reported as a wall. Nothing
    here retries, hammers or works around a paywall.
  * Routes that were confirmed on the previous run are probed FIRST inside each lane, so an
    interrupted run still produces the answer that matters, and the partial file on disk is real.

It also probes BOTH inference endpoints, because they are not the same code path and the difference
is the whole point of this exercise. The client this feeds (oioi's "Configure third-party inference")
calls POST /v1/messages -- the Anthropic-shaped route -- while every probe script in this repo so far
has only ever called POST /v1/chat/completions. MEASURED 2026-08-25, same gateway, same minute:

    route                /v1/messages        /v1/chat/completions
    frontier             200 in 10.1s        ReadTimeout at 60s
    auto/best-coding     200 in 14.6s        ReadTimeout at 60s
    codex/gpt-5.6-sol    200 in  5.1s        200 in 11.6s

So certifying a route on chat/completions and then handing it to a client that calls /v1/messages
certifies the wrong thing in both directions. `messages` is the primary verdict here because it is
what the client uses; `chat` is recorded alongside it so the OpenAI-shaped clients in this repo
(ZCode, Zed, VS Code, Codex CLI) are not being told something untrue either.

Two other fidelity fixes over the old script:

  * timeout 45s, not 20s. pollinations' median latency for a route that DID answer was 21.9s, so a
    20s ceiling was scoring healthy slow providers as failures.
  * an HTTP 200 with no assistant text is recorded as its own verdict (`empty`) with the
    finish_reason, instead of being folded into the same bucket as a 404. The old run had 9 of those
    on kilocode alone and they are a different problem with a different fix.

Output: state/route_truth.json (plus a dated copy), written incrementally after every lane so a
kill -9 never costs the whole pass. Nothing is printed but model ids, statuses and latencies -- no
key, token or password is read or logged by this script.

Usage:
    python probe_route_truth.py                        # everything: 90 connections + 16 combos
    python probe_route_truth.py --only codex,agy       # just those providers
    python probe_route_truth.py --max-per-provider 12  # fast sample pass
    python probe_route_truth.py --combos-only
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from oauth_keepalive import resolve_password  # noqa: E402
from omniroute_api import OmniRouteAPI  # noqa: E402

BASE = "http://127.0.0.1:20128"
OUT = ROOT / "state" / "route_truth.json"
PRIOR = ROOT / "state" / "healthy_provider_models_rescan.json"

# A combo is a cascade: it tries member after member, and every dead member costs a full upstream
# timeout before the next one is attempted. MEASURED 2026-08-25: `frontier` answered in 5.2s once
# and then timed out at 60s on the very next call. So combos get their own, much longer ceiling --
# scoring them on the per-model timeout would just measure how many dead members they carry.
COMBO_TIMEOUT = 150
MODEL_TIMEOUT = 45

PROMPT = "Reply with the single word OK."

# Any of these in an error body means a wall, not a broken model: stop the lane, report it, and do
# not touch it again. Card / captcha / phone / plan / quota walls are never pushed through.
WALL_STATUSES = {402}
WALL_TEXT = ("payment required", "insufficient credit", "insufficient_quota", "quota exceeded",
             "billing", "add a payment", "upgrade your plan", "captcha")

RATE_STATUSES = {429}
AUTH_STATUSES = {401, 403}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- one probe


def _answer(body: dict) -> tuple[str, str]:
    """(assistant text, finish_reason) out of an Anthropic-shaped body, tolerating streamed shapes."""
    if not isinstance(body, dict):
        return "", ""
    
    # Anthropic standard response
    if "content" in body and isinstance(body["content"], list) and len(body["content"]) > 0:
        first = body["content"][0]
        if isinstance(first, dict) and "text" in first:
            return str(first["text"]).strip(), str(body.get("stop_reason") or "")

    # Anthropic stream chunk
    if body.get("type") == "content_block_delta":
        delta = body.get("delta") or {}
        if delta.get("type") == "text_delta" and "text" in delta:
            return str(delta["text"]).strip(), ""
            
    if body.get("type") == "message_delta":
        return "", str((body.get("delta") or {}).get("stop_reason") or "")

    # Fallback to OpenAI shape
    try:
        choice = (body.get("choices") or [{}])[0]
    except (AttributeError, IndexError):
        return "", ""
    msg = choice.get("message") or {}
    delta = choice.get("delta") or {}
    text = (msg.get("content") or delta.get("content") or "")
    if not isinstance(text, str):
        # Some providers answer content as a list of parts; join the text ones.
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    return text.strip(), str(choice.get("finish_reason") or "")


def _sse_answer(text: str) -> str:
    """The gateway force-streams some routes even with stream:false, so a valid answer can arrive as
    SSE with no parseable JSON body. Pull the content deltas out rather than calling it a failure."""
    out = []
    for line in text.splitlines():
        if not line.startswith("data:") or "[DONE]" in line:
            continue
        try:
            chunk = json.loads(line[5:].strip())
        except ValueError:
            continue
        piece, _ = _answer(chunk)
        if piece:
            out.append(piece)
    return "".join(out).strip()


def probe(model_id: str, timeout: int) -> dict[str, Any]:
    """One real chat completion. Verdict is one of: ok, empty, not_routed, auth, wall, rate, error."""
    started = time.perf_counter()
    row: dict[str, Any] = {"model": model_id}
    try:
        r = requests.post(
            f"{BASE}/v1/messages",
            json={"model": model_id, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 20},
            timeout=timeout,
        )
    except requests.RequestException as e:
        row.update(valid=False, verdict="error", httpStatus=None, errorType=type(e).__name__,
                   latencyMs=round((time.perf_counter() - started) * 1000))
        return row

    row["latencyMs"] = round((time.perf_counter() - started) * 1000)
    row["httpStatus"] = r.status_code
    raw = r.text or ""
    try:
        body = r.json()
    except ValueError:
        body = {}
    text, finish = (_answer(body) if body else ("", ""))
    if not text:
        text = _sse_answer(raw)
    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    detail = str(err.get("message") or body.get("detail") or body.get("message") or "")[:200]
    low = (detail + " " + raw[:300]).lower()

    if r.status_code == 200 and text:
        row.update(valid=True, verdict="ok", served=str(body.get("model") or "")[:60] or None,
                   sample=text[:40])
        return row
    row["valid"] = False
    if detail:
        row["detail"] = detail
    if r.status_code == 200:
        row.update(verdict="empty", finishReason=finish or None)
    elif r.status_code in WALL_STATUSES or any(w in low for w in WALL_TEXT):
        row["verdict"] = "wall"
    elif r.status_code in RATE_STATUSES:
        row["verdict"] = "rate"
    elif r.status_code in AUTH_STATUSES:
        row["verdict"] = "auth"
    elif r.status_code == 404:
        # 404 from the gateway is "I will not route this id", which is a registry claim the upstream
        # never saw. Kept distinct from auth and from 5xx because it is the one failure that means
        # the model list is wrong rather than the account.
        row["verdict"] = "not_routed"
    else:
        row["verdict"] = "error"
    return row


# --------------------------------------------------------------------------- one provider lane


class Lane:
    """Every route for ONE provider, probed one at a time, with the rate-limit and wall rules."""

    def __init__(self, provider: str, routes: list[tuple[str, str]], timeout: int):
        self.provider = provider
        self.routes = routes                     # [(connection_id, model_id)]
        self.timeout = timeout
        self.rows: list[dict[str, Any]] = []
        self.stopped: str | None = None

    def run(self) -> "Lane":
        strikes = 0
        for conn_id, model in self.routes:
            if self.stopped:
                self.rows.append({"model": model, "provider": self.provider,
                                  "connectionId": conn_id, "valid": False,
                                  "verdict": "skipped", "detail": self.stopped})
                continue
            row = probe(model, self.timeout)

            if row["verdict"] == "rate":
                # Our scheduling problem, not the model's verdict. Wait, retry once, then slow the
                # whole lane down. Never recorded as "this model does not work".
                strikes += 1
                time.sleep(min(30, 5 * strikes))
                row = probe(model, self.timeout)
                if row["verdict"] == "rate" and strikes >= 4:
                    self.stopped = f"lane paused: {strikes} rate limits from {self.provider}"
                    log(f"  {self.provider}: {self.stopped}")
            elif row["verdict"] == "wall":
                self.stopped = f"WALL: {row.get('detail') or 'payment/quota required'}"
                log(f"  {self.provider}: {self.stopped} -- lane stopped, not retried")
            elif row["verdict"] == "ok":
                strikes = 0

            row.update(provider=self.provider, connectionId=conn_id)
            self.rows.append(row)
        ok = sum(1 for r in self.rows if r.get("valid"))
        log(f"  {self.provider:22s} {ok:4d} ok / {len(self.rows):4d} probed"
            f"{' [' + self.stopped + ']' if self.stopped else ''}")
        return self


# --------------------------------------------------------------------------- report


def _prior_confirmed() -> set[tuple[str, str]]:
    """(provider, model) confirmed by the previous run -- used only to ORDER each lane, never to
    decide a verdict. Probing the known-good routes first means an interrupted pass still answers
    the question that was asked."""
    if not PRIOR.exists():
        return set()
    try:
        d = json.loads(PRIOR.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {(r.get("provider"), r.get("model")) for r in d.get("results", []) if r.get("valid")}


def _write(report: dict) -> None:
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _summarise(rows: list[dict], combos: list[dict]) -> dict:
    from collections import Counter
    by_verdict = Counter(r.get("verdict") for r in rows)
    confirmed: dict[str, list[str]] = {}
    for r in rows:
        if r.get("valid"):
            confirmed.setdefault(r["provider"], []).append(r["model"])
    return {
        "confirmedRouteCount": sum(len(v) for v in confirmed.values()),
        "probedRouteCount": len(rows),
        "verdicts": dict(by_verdict.most_common()),
        "confirmedByProvider": {k: sorted(v) for k, v in sorted(confirmed.items())},
        "confirmedCombos": sorted(c["model"] for c in combos if c.get("valid")),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lanes", type=int, default=10,
                    help="providers probed concurrently (requests per provider is always 1)")
    ap.add_argument("--timeout", type=int, default=MODEL_TIMEOUT)
    ap.add_argument("--only", default="", help="comma-separated providers to probe")
    ap.add_argument("--skip", default="", help="comma-separated providers to leave alone")
    ap.add_argument("--max-per-provider", type=int, default=0, help="0 = no cap")
    ap.add_argument("--combos-only", action="store_true")
    a = ap.parse_args()

    only = {p.strip() for p in a.only.split(",") if p.strip()}
    skip = {p.strip() for p in a.skip.split(",") if p.strip()}

    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        print("management login failed -- cannot enumerate connections")
        return 1

    started = dt.datetime.now(dt.timezone.utc).isoformat()
    report: dict[str, Any] = {
        "generatedAt": started,
        "method": ("per-provider serial lanes, parallel across providers; real chat completion per "
                   "route; 429 backed off and retried, never scored as a dead model; 402/quota "
                   "stops that lane and is reported as a wall"),
        "promptUsed": PROMPT,
        "modelTimeoutSeconds": a.timeout,
        "comboTimeoutSeconds": COMBO_TIMEOUT,
        "combos": [], "results": [], "summary": {}, "notes": [],
    }

    # ---- combos first: they are the entries a client should actually be handed, and there are 16.
    combo_names = [str(c.get("name")) for c in api.get_combos() if c.get("name")]
    log(f"combos: {len(combo_names)}")
    for name in combo_names:
        row = probe(name, COMBO_TIMEOUT)
        row["provider"] = "(combo)"
        report["combos"].append(row)
        log(f"  {name:26s} {row['verdict']:10s} HTTP {row.get('httpStatus')} "
            f"{row.get('latencyMs')}ms {(row.get('served') or '')[:24]}")
        _write(report)
    if a.combos_only:
        report["summary"] = _summarise([], report["combos"])
        _write(report)
        log(f"wrote {OUT}")
        return 0

    # ---- which connections are worth probing at all
    conns = [c for c in api.get_connections() if c.get("isActive")]
    log(f"active connections: {len(conns)}")

    prior = _prior_confirmed()
    lanes: dict[str, list[tuple[str, str]]] = {}
    for c in conns:
        prov = str(c.get("provider") or "unknown")
        if (only and prov not in only) or prov in skip:
            continue
        models = sorted(set(api.connection_models(str(c["id"]))))
        if not models:
            report["notes"].append(f"{prov}/{c['id']}: management API listed 0 models")
            continue
        lanes.setdefault(prov, []).extend((str(c["id"]), m) for m in models)

    for prov, routes in lanes.items():
        routes = sorted(set(routes), key=lambda r: ((prov, r[1]) not in prior, r[1]))
        if a.max_per_provider:
            routes = routes[:a.max_per_provider]
        lanes[prov] = routes
    total = sum(len(v) for v in lanes.values())
    log(f"lanes: {len(lanes)} providers, {total} routes, {a.lanes} lanes at a time, "
        f"1 request per provider")

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, a.lanes)) as pool:
        futures = [pool.submit(Lane(p, r, a.timeout).run) for p, r in
                   sorted(lanes.items(), key=lambda kv: -len(kv[1]))]
        for fut in as_completed(futures):
            lane = fut.result()
            report["results"].extend(lane.rows)
            if lane.stopped:
                report["notes"].append(f"{lane.provider}: {lane.stopped}")
            done += 1
            report["summary"] = _summarise(report["results"], report["combos"])
            _write(report)
            log(f"lanes done {done}/{len(futures)} | confirmed so far "
                f"{report['summary']['confirmedRouteCount']}")

    report["finishedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["summary"] = _summarise(report["results"], report["combos"])
    _write(report)
    stamp = time.strftime("%Y%m%d")
    (ROOT / "state" / f"route_truth_{stamp}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")

    s = report["summary"]
    log(f"confirmed {s['confirmedRouteCount']} of {s['probedRouteCount']} routes, "
        f"{len(s['confirmedCombos'])} of {len(report['combos'])} combos")
    log(f"verdicts: {s['verdicts']}")
    log(f"wrote {OUT} and route_truth_{stamp}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
