#!/usr/bin/env python3
"""Gate 2 + 4: pure-Python chat graduation through :8190 with Law-3 exact
computed answers and explicit provider/session attribution.

For every live seat-pool chat host advertised by :8190, send ONE fresh
arithmetic question ("Reply with only the number: <a> + <b>") via the
unpinned+pinned model syntax, accept ONLY an exact normalized computed answer
(no substring acceptance), and record the provider+session the shim attributes
in the response body. Failing hosts are recorded honestly (status + detail),
never counted as capacity. No browser, no retries that would hammer a seat.

Attribution note: the :8190 shim already returns `provider`/`session` inside the
OpenAI-compatible JSON body (session_pool_shim.py:819-820). The shim is a
task-owned process that MUST NOT be restarted, so attribution is captured from
the live response body rather than by adding headers that would need a reload.
"""
import json
import pathlib
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
SHIM = "http://127.0.0.1:8190"
OUT = ROOT / "state" / "chat_graduation.json"


# Static seat-host list: the live chat seat hosts aggregated by the pool across
# ALL seats (discovered earlier from :8190 /v1/models). Used instead of calling
# /v1/models live because, during this run, the OmniRoute upstream (:20128) is
# unresponsive (timeout) which makes /v1/models hang; the seat-pool chat path
# itself is independent of :20128 and remains valid. If :20128 recovers, this
# list can be regenerated dynamically.
SEAT_CHAT_HOSTS = [
    "api.1min.ai", "chatgpt.com", "claude.ai", "api.cohere.com",
    "chat.deepseek.com", "felo.ai", "api.groq.com", "chat.mistral.ai",
    "www.perplexity.ai", "chat.qwen.ai",
]


def live_seat_chat_hosts():
    return list(SEAT_CHAT_HOSTS)


def exact_ok(content, expect):
    """Exact normalized computed-answer check (Law 3). No substring acceptance.

    Normalization: strip surrounding whitespace and smart/straight quotes, and
    tolerate a single trailing period (a common provider quirk). The expected
    value is the arithmetic result, e.g. 58, which appears in neither an echo
    nor a generated title, so equality is a true correctness signal.
    """
    if content is None:
        return False
    norm = content.strip().strip('"\u201c\u201d')
    if norm.endswith('.'):
        cand = norm[:-1].strip()
        if cand == str(expect):
            return True
    return norm == str(expect)


def probe(model, question, expect, timeout=45):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": question}],
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{SHIM}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer sk-omniroute"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            h = {k.lower(): v for k, v in resp.headers.items()}
            d = json.loads(resp.read().decode())
        latency = round(time.monotonic() - t0, 2)
        content = ((d.get("choices") or [{}])[0].get("message", {})
                   .get("content", "") or "")
        ok = exact_ok(content, expect)
        return {
            "model_requested": model, "model_served": d.get("model"),
            "status": "ok", "latency_s": latency, "answer": content[:80],
            "computed_ok": ok, "expected": expect,
            "provider": d.get("provider"), "session": d.get("session"),
            "x_pool_source": h.get("x-pool-source"),
            "x_pool_fallback_reason": h.get("x-pool-fallback-reason"),
            "attribution_source": "response_body",
        }
    except urllib.error.HTTPError as e:
        return {"model_requested": model, "status": f"http_{e.code}",
                "latency_s": round(time.monotonic() - t0, 2),
                "detail": e.read().decode()[:200], "computed_ok": False}
    except Exception as e:
        return {"model_requested": model, "status": f"error_{type(e).__name__}",
                "latency_s": round(time.monotonic() - t0, 2),
                "detail": str(e)[:200], "computed_ok": False}


def main():
    rows = []
    admitted = []
    balanced_note = []
    hosts = live_seat_chat_hosts()
    for i, host in enumerate(hosts):
        a, b = 41 + i * 3, 17 + i
        q = f"Reply with only the number: {a} + {b}"
        expect = a + b
        best = None
        rows_for_host = []
        # Correct pin syntax is "<host>/auto" (mandate). "session-pool/auto" is the
        # balanced consumer form; probe it only as a reachability fallback when the
        # explicit pin fails, and tag its attribution as pool-chosen.
        for model in (f"{host}/auto", "session-pool/auto"):
            r = probe(model, q, expect)
            if model == "session-pool/auto":
                r["pin"] = "balanced"
            else:
                r["pin"] = "host"
            r["host"] = host
            r["question"] = q
            r["timestamp_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            rows.append(r)
            rows_for_host.append(r)
            print(json.dumps({k: r[k] for k in
                              ("host", "model_requested", "status", "computed_ok",
                               "provider", "session", "latency_s") if k in r}))
            if r["status"] == "ok":
                if best is None or r["computed_ok"]:
                    best = r
                if r["computed_ok"]:
                    break
            time.sleep(3)
        # Rigor: a host is ADMITTED only when its own PINNED form
        # (<host>/auto) returned the exact computed answer -- that alone proves
        # that specific seat is graduated. A balanced session-pool/auto answer
        # proves the pool is alive but must NOT credit a host whose pinned form
        # failed (it would mis-attribute another provider's seat to this host).
        pinned_ok = None
        for rr in rows_for_host:
            if rr.get("model_requested") == f"{host}/auto" and rr.get("computed_ok"):
                pinned_ok = rr
                break
        if pinned_ok:
            admitted.append({"host": host, "provider": pinned_ok.get("provider"),
                             "session": pinned_ok.get("session"),
                             "model": pinned_ok["model_requested"],
                             "latency_s": pinned_ok["latency_s"]})
        elif best and best.get("computed_ok"):
            # balanced pool answered but the host's own pinned seat did not;
            # record as pool-alive, not as this host's capacity.
            balanced_note.append({"host": host,
                                  "pool_answered_as": best.get("provider"),
                                  "session": best.get("session")})
    doc = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "gate": "2_chat_graduation", "endpoint": f"{SHIM}/v1",
        "transport": "pure-python urllib (no browser)",
        "exact_normalized_check": True,
        "hosts_discovered": hosts, "rows": rows,
        "computed_ok_hosts": [s["host"] for s in admitted],
        "admitted": admitted,
        "pool_alive_balanced_only": balanced_note,
        "summary": f"{len(admitted)}/{len(hosts)} live seat-pool chat hosts answered "
                   "a fresh exact computed Law-3 question through :8190 on their OWN "
                   "pinned seat with provider/session attribution "
                   f"(+{len(balanced_note)} host(s) whose pinned seat did not answer "
                   "but the balanced pool was alive)",
    }
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp.replace(OUT)
    print("SUMMARY:", doc["summary"])


if __name__ == "__main__":
    main()
