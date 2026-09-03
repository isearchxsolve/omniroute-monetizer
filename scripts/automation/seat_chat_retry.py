#!/usr/bin/env python3
"""Bounded single-retry pass for seat-lane chat rows that failed one sample.

Per worklog #1617/#1620: failures from the first sweep are single-sample
verdicts.  This script gives each named seat exactly ONE fresh Law-3 request
through the canonical consumer endpoint :8190 -- no internal retries, no
hammering.  Timeouts and 5xx stay non-retried here; per policy a seat that
fails twice in a row is left to a later, separately-scheduled increment.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.request
import urllib.error

STATE = pathlib.Path(__file__).resolve().parents[2] / "state"
CONSUMER = "http://127.0.0.1:8190/v1"
PROMPT = "Reply with only the number: 41 + 17"
EXPECTED = "58"
DEFAULT_SEATS = [
    "api.1min.ai/auto",
    "api.groq.com/auto",
    "app.chathub.gg/auto",
    "chat.deepseek.com/auto",
    "felo.ai/auto",
]


def tenant_bearer(tenant: str = "tenant_001") -> str:
    """One key from the hot-read tenant map; the value is never printed."""
    try:
        mapping = json.loads((STATE / "secrets" / "tenant_map.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    for key, name in mapping.items():
        if name == tenant and isinstance(key, str):
            return key
    return ""


def probe(seat: str, timeout: float, bearer: str = "") -> dict:
    started = time.perf_counter()
    body = json.dumps({
        "model": seat,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0,
        "max_tokens": 200,
        "stream": False,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(
        f"{CONSUMER}/chat/completions", data=body, method="POST", headers=headers)
    out: dict = {"seat": seat}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            out["http"] = resp.status
            try:
                payload = json.loads(raw)
                answer = "".join(
                    ch.get("message", {}).get("content", "")
                    or ch.get("delta", {}).get("content", "") or ""
                    for ch in (payload.get("choices") or []) if isinstance(ch, dict))
                out["answer"] = (answer or "")[:40]
            except json.JSONDecodeError:
                out["answer"] = ""
            out["verdict"] = "LIVE" if EXPECTED in (out.get("answer") or "") else "NO_ANSWER"
    except urllib.error.HTTPError as exc:
        out["http"] = exc.code
        out["verdict"] = "ERROR"
        out["detail"] = f"HTTPError: HTTP Error {exc.code}: {exc.reason}"
    except Exception as exc:  # transport family
        out["verdict"] = "ERROR"
        out["detail"] = f"{type(exc).__name__}: {exc}"[:200]
    out["latencyMs"] = round((time.perf_counter() - started) * 1000)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seats", nargs="*", default=DEFAULT_SEATS)
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--out", default=str(STATE / "seat_chat_retry_latest.json"))
    ap.add_argument("--tenant", default="tenant_001")
    args = ap.parse_args()
    bearer = tenant_bearer(args.tenant)
    if not bearer:
        print("no tenant key resolved; consumer calls would 401 at the tenant gate", flush=True)
        return 2
    results = []
    for seat in args.seats:  # serial, one request each
        row = probe(seat, args.timeout, bearer)
        results.append(row)
        print(f"{seat} -> {row['verdict']} {row.get('detail', '')} {row['latencyMs']}ms", flush=True)
        time.sleep(2.0)  # light spacing between seats
    live = [r["seat"] for r in results if r["verdict"] == "LIVE"]
    report = {"sweep": "seat_chat_law3_single_retry", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "prompt": PROMPT, "expected": EXPECTED, "results": results, "live": live,
              "counts": {"probed": len(results), "live": len(live)}}
    tmp = pathlib.Path(args.out).with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=1), encoding="utf-8")
    pathlib.Path(tmp).replace(pathlib.Path(args.out))
    print(json.dumps(report["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
