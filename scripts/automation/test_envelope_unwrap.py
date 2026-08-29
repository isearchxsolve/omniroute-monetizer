"""Regression tests for the no-tool envelope unwrap (worklog #1160).

The tool contract (chat_pool_server.tool_instruction) tells seats to reply
{"tool": null, "text": "<answer>"} when no tool applies. That envelope is OUR wire format,
never the model's words -- and a seat whose recorded request carries the contract (Cohere's
captured exchange does) answers EVERY probe inside it, so the replay extractor receives the
envelope as "the reply" and the strict numeric verify fails on wire format, not on the answer.

Run: python scripts/automation/test_envelope_unwrap.py   (also pytest-collectable)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from chat_pool_server import unwrap_no_tool_text            # noqa: E402
from universal_replay import UniversalSessionClient          # noqa: E402
from replay_check import classify                            # noqa: E402


def test_envelope_unwraps():
    assert unwrap_no_tool_text('{"tool": null, "text": "58"}') == "58"


def test_fenced_envelope_unwraps():
    assert unwrap_no_tool_text('```json\n{"tool": null, "text": "58"}\n```') == "58"


def test_real_tool_call_untouched():
    assert unwrap_no_tool_text('{"tool": "Bash", "text": "irrelevant"}') is None


def test_plain_text_untouched():
    assert unwrap_no_tool_text("58") is None


def test_json_with_non_null_tool_key_untouched():
    assert unwrap_no_tool_text('{"answer": "58", "tool": "Tool0"}') is None


def test_empty_and_empty_text():
    assert unwrap_no_tool_text("") is None
    assert unwrap_no_tool_text('{"tool": null, "text": ""}') is None


def _client():
    client = UniversalSessionClient.__new__(UniversalSessionClient)
    client._last_prompt = "Reply with only the number: 41 + 17"
    return client


def test_sse_envelope_end_to_end():
    """The Cohere chain, offline: escaped envelope inside an SSE stream assembles as the
    envelope, the unwrap surfaces '58', and the strict numeric check accepts it."""
    sse = (
        'event: message-start\ndata: {"type":"message-start"}\n\n'
        'event: content-delta\ndata: {"type":"content-delta","delta":{"message":'
        '{"content":{"text":"{\\"tool\\": null, \\"text\\": \\"58\\"}"}}}}\n\n'
        'event: message-end\ndata: {"type":"message-end"}\n'
    )
    assembled, err = _client()._extract_response(sse)
    assert assembled == '{"tool": null, "text": "58"}' and err is None
    final = unwrap_no_tool_text(assembled) or assembled
    assert final == "58"
    assert classify(final, 200, None, "58")[0] == "REPLAY_OK"


def test_whole_body_envelope_extracts_directly():
    assembled, err = _client()._extract_response('{"tool": null, "text": "58"}')
    assert (assembled, err) == ("58", None)


def test_tool_call_body_not_rewritten():
    assembled, _ = _client()._extract_response('{"tool": "Bash", "text": "ls -la output"}')
    assert unwrap_no_tool_text(assembled) is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except AssertionError as exc:
            failed += 1
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
