"""Offline unit tests for capture_sessions_cdp.capture_payload (multi-exchange buffering).
No CDP, no Chrome, no network."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from capture_sessions_cdp import capture_payload, has_sentinel  # noqa: E402


def _hit(url, body, method="POST"):
    return {"url": url, "method": method,
            "request_headers": {"content-type": "application/json", "User-Agent": "UA"},
            "request_body": body, "host": url.split("/")[2]}


def test_single_exchange_is_legacy_shape():
    p = capture_payload(hits=[_hit("https://x.example/api/chat", "q=Reply%20exactly")],
                        cookie_header="a=1", site="X")
    assert p["host"] == "x.example"
    assert p["recorded_exchange"]["url"] == "https://x.example/api/chat"
    assert p["recorded_exchange"]["request_body"] == "q=Reply%20exactly"
    assert p["recorded_exchange"]["cookie_header"] == "a=1"
    assert p["exchangeCount"] == 1
    assert "recorded_exchanges" not in p, "single-exchange artifact must stay legacy-shaped"
    assert p["status"]["alive"] is True
    assert p["status"]["reason"] == "capture_sessions_cdp"
    print("PASS single_exchange_is_legacy_shape")


def test_multi_exchange_keeps_first_and_orders_rest():
    hits = [
        _hit("https://x.example/api/prepare", "s=Reply exactly one word: Omni."),
        _hit("https://x.example/api/conversation", "m=Reply exactly one word: Omni."),
        _hit("https://x.example/api/stream", "m2=Reply exactly one word: Omni.", method="PUT"),
    ]
    p = capture_payload(hits=hits, cookie_header="a=1", site="X", pending=True)
    assert p["recorded_exchange"]["url"].endswith("/api/prepare"), "first stays the legacy exchange"
    assert p["exchangeCount"] == 3
    seq = p["recorded_exchanges"]
    assert [h["url"].rsplit("/", 1)[-1] for h in seq] == ["prepare", "conversation", "stream"]
    assert seq[2]["method"] == "PUT"
    for h in seq:
        assert "request_body" in h and "host" in h and "request_headers" in h
    assert p["status"]["alive"] is False and p["status"]["reason"] == "pending_replay_verification"
    print("PASS multi_exchange_keeps_first_and_orders_rest")


def test_empty_hits_refused():
    try:
        capture_payload(hits=[], cookie_header="", site="X")
    except ValueError:
        print("PASS empty_hits_refused")
        return
    raise AssertionError("empty hits must be refused")


def test_has_sentinel_forms():
    assert has_sentinel("Reply exactly one word: Omni.")
    assert has_sentinel("Reply+exactly+one+word%3A+Omni.")
    assert has_sentinel('"Reply exactly one word: Omni."')
    assert not has_sentinel("nothing here")
    print("PASS has_sentinel_forms")


if __name__ == "__main__":
    test_single_exchange_is_legacy_shape()
    test_multi_exchange_keeps_first_and_orders_rest()
    test_empty_hits_refused()
    test_has_sentinel_forms()
    print("ALL CAPTURE_PAYLOAD TESTS PASSED")
