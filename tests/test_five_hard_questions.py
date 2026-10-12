"""Comprehensive test suite for the 5 Hard Architectural Questions in OmniRoute:
  Q1: Token Expiry & State Inversion (Set-Cookie rotation, JWT header sync, atomic persistence, Heartbeat)
  Q2: Polymorphic Dynamic Crypto / Nonce / PoW (X-Timestamp, X-Nonce, X-Sign, DeepSeek WASM PoW)
  Q3: Multi-Step Workflows (2-Leg / N-Leg dynamic ID extraction & request threading)
  Q4: Datacenter ASN & Egress TLS Impersonation (Proxy resolution + curl_cffi Chrome TLS + WS proxy)
  Q5: Binary Protobuf / gRPC-Web / WebSocket Frame Surgery (Varint & 5-byte big-endian frame length recomputation)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "scripts" / "automation"
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

from universal_replay import (  # noqa: E402
    UniversalSessionClient,
    _encode_varint,
    _decode_varint,
    _is_grpc_web_framed,
    substitute_protobuf_bytes,
    extract_protobuf_strings,
)
from multistep_replay import (  # noqa: E402
    resolve_egress_proxy,
    apply_dynamic_headers,
    extract_bootstrap_tokens,
    thread_bootstrap_into_leg,
)
from ws_replay import WebSocketSessionClient, _parse_ws_proxy_kwargs  # noqa: E402


# ===========================================================================
# Q1: Token Expiry & State Inversion
# ===========================================================================

def test_q1_absorb_cookies_rotates_jar_and_syncs_jwt_bearer_atomically(tmp_path: Path):
    session_file = tmp_path / "session_stytch_example.json"
    old_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.old_payload.old_sig"
    new_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.new_payload.new_sig"
    blueprint = {
        "host": "stytch.example.com",
        "cookie_header": f"sid=init123; __stytch_session_jwt={old_jwt}; theme=dark",
        "recorded_exchange": {
            "url": "https://stytch.example.com/api/chat",
            "method": "POST",
            "request_headers": {
                "Content-Type": "application/json",
                "Cookie": f"sid=init123; __stytch_session_jwt={old_jwt}; theme=dark",
                "Authorization": f"Bearer {old_jwt}",
            },
            "request_body": '{"prompt": "Reply exactly one word: Omni."}',
        },
        "recorded_exchanges": [
            {
                "url": "https://stytch.example.com/api/prepare",
                "method": "POST",
                "request_headers": {
                    "Cookie": f"sid=init123; __stytch_session_jwt={old_jwt}; theme=dark",
                    "Authorization": f"Bearer {old_jwt}",
                },
                "request_body": "{}",
            }
        ],
    }
    session_file.write_text(json.dumps(blueprint, indent=2), encoding="utf-8")

    client = UniversalSessionClient(session_file)

    # Simulate redirect history + final response rotating `sid` and `__stytch_session_jwt`
    hist_resp = SimpleNamespace(
        cookies=[SimpleNamespace(name="sid", value="rot456")],
        headers={},
        history=[],
    )
    final_resp = SimpleNamespace(
        cookies=[SimpleNamespace(name="__stytch_session_jwt", value=new_jwt)],
        headers={"x-auth-token": "fresh-custom-token"},
        history=[hist_resp],
    )

    changed = client._absorb_cookies(final_resp)
    assert changed >= 2
    assert f"sid=rot456" in client.headers["Cookie"]
    assert f"__stytch_session_jwt={new_jwt}" in client.headers["Cookie"]
    # Authorization Bearer header must automatically track the rotated JWT cookie!
    assert client.headers["Authorization"] == f"Bearer {new_jwt}"

    # Verify atomic persistence to disk across top-level, recorded_exchange, and recorded_exchanges
    persisted = json.loads(session_file.read_text(encoding="utf-8"))
    assert f"__stytch_session_jwt={new_jwt}" in persisted["cookie_header"]
    assert persisted["recorded_exchange"]["request_headers"]["Authorization"] == f"Bearer {new_jwt}"
    assert persisted["recorded_exchanges"][0]["request_headers"]["Authorization"] == f"Bearer {new_jwt}"
    assert "cookieRotatedAt" in persisted


# ===========================================================================
# Q2: Polymorphic Dynamic Crypto / Nonce / PoW (Adapter Thesis Mode B)
# ===========================================================================

def test_q2_dynamic_headers_refresh_timestamps_nonces_and_chatglm_x_sign():
    recorded_headers = {
        "Content-Type": "application/json",
        "X-Request-Id": "11111111-2222-3333-4444-555555555555",
        "X-Nonce": "abcdef0123456789abcdef0123456789",
        "X-Timestamp": "1700000000",
        "X-Sign": "stale_signature_0000000000000000",
    }
    updated = apply_dynamic_headers("chatglm.cn", recorded_headers, '{"prompt":"test"}')

    assert updated["X-Request-Id"] != recorded_headers["X-Request-Id"]
    assert len(updated["X-Request-Id"]) == 36
    assert updated["X-Nonce"] != recorded_headers["X-Nonce"]
    assert len(updated["X-Nonce"]) == 32
    assert updated["X-Timestamp"] != "1700000000"
    assert updated["X-Timestamp"].isdigit() and len(updated["X-Timestamp"]) == 10

    expected_raw = f"{updated['X-Timestamp']}-{updated['X-Nonce']}-8a1317a7468aa3ad86e997d08f3f31cb"
    expected_sign = hashlib.md5(expected_raw.encode("utf-8")).hexdigest()
    assert updated["X-Sign"] == expected_sign


def test_q2_deepseek_wasm_pow_solver_live_execution():
    import shutil
    import subprocess

    adapters_dir = AUTOMATION / "adapters"
    if str(adapters_dir) not in sys.path:
        sys.path.insert(0, str(adapters_dir))
    from deepseek_adapter import solve_deepseek_pow

    default_node = Path(r"D:\DOWNLOADS\node-v24.18.0-win-x64\node-v24.18.0-win-x64\node.exe")
    node_bin = str(default_node) if default_node.exists() else (shutil.which("node") or "node")
    extract_dir = ROOT / "scratch" / "ds_pow_extract"
    salt = "a1b2c3d4e5f60718293a"
    expire_at = 1999999999
    target_answer = 42

    # Generate the authentic DeepSeekHashV1 challenge digest for target_answer=42
    # using DeepSeek's own 76608.js + 8138.js bundle (piped via stdin, zero synthetic mocks)
    gen_js = f"""
const fs = require('fs');
const path = require('path');
const dir = {json.dumps(str(extract_dir))};
global.self = global;
global.importScripts = (url) => {{
    const fname = path.basename(url).split('.')[0] + '.js';
    eval(fs.readFileSync(path.join(dir, fname), 'utf8'));
}};
let code76608 = fs.readFileSync(path.join(dir, '76608.js'), 'utf8');
code76608 = code76608.replace(
    'onmessage=t=>{{',
    'global.onmessage=t=>{{'
).replace(
    'if(n.copy().update(String(i)).digest("hex")===t)return i;',
    'if(i==={target_answer})return n.copy().update(String(i)).digest("hex");'
).replace(
    'if("number"!=typeof s)',
    'if(!s)'
);
global.postMessage = (msg) => {{
    if (msg.type === 'pow-answer') {{
        console.log('DIGEST:' + msg.answer.answer);
        process.exit(0);
    }} else {{
        console.error(msg);
        process.exit(1);
    }}
}};
eval(code76608);
setTimeout(() => {{
    global.onmessage({{
        data: {{
            type: 'pow-challenge',
            challenge: {{
                algorithm: 'DeepSeekHashV1',
                challenge: '00',
                salt: {json.dumps(salt)},
                difficulty: 100,
                expireAt: {expire_at},
                signature: 'sig'
            }}
        }}
    }});
}}, 80);
"""
    proc = subprocess.run(
        [node_bin, "-"],
        input=gen_js,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    assert proc.returncode == 0, f"Digest generator failed: {proc.stderr}"
    real_challenge_hex = ""
    for line in proc.stdout.splitlines():
        if line.startswith("DIGEST:"):
            real_challenge_hex = line.split("DIGEST:", 1)[1].strip()
            break
    assert len(real_challenge_hex) == 64, f"Expected 64-char hex digest, got: {real_challenge_hex!r}"

    challenge = {
        "algorithm": "DeepSeekHashV1",
        "challenge": real_challenge_hex,
        "salt": salt,
        "difficulty": 100.0,
        "expireAt": expire_at,
        "expireAfter": 300000,
        "signature": "sig_test_vector_123",
        "target_path": "/api/v0/chat/completion",
    }
    token_b64 = solve_deepseek_pow(challenge)
    decoded = json.loads(base64.b64decode(token_b64).decode("utf-8"))
    assert decoded["algorithm"] == "DeepSeekHashV1"
    assert decoded["challenge"] == challenge["challenge"]
    assert decoded["salt"] == challenge["salt"]
    assert decoded["answer"] == target_answer



# ===========================================================================
# Q3: Multi-Step Workflows (2-Leg / N-Leg Flow Threading)
# ===========================================================================

def test_q3_generic_multistep_threads_bootstrap_ids_and_replays_leg2(tmp_path: Path, monkeypatch):
    session_file = tmp_path / "session_multistep_provider.json"
    blueprint = {
        "host": "multi.example.ai",
        "cookie_header": "session=initial_cookie",
        "recorded_exchange": {
            "url": "https://multi.example.ai/api/v1/conversation/init",
            "method": "POST",
            "request_headers": {"Content-Type": "application/json"},
            "request_body": '{"action": "init"}',
        },
        "recorded_exchanges": [
            {
                "url": "https://multi.example.ai/api/v1/conversation/init",
                "method": "POST",
                "request_headers": {"Content-Type": "application/json"},
                "request_body": '{"action": "init"}',
                "response_body": '{"conversation_id": "conv_old_111", "conduit_token": "tok_old_111"}',
            },
            {
                "url": "https://multi.example.ai/api/v1/conversation/chat?conversation_id=conv_old_111",
                "method": "POST",
                "request_headers": {
                    "Content-Type": "application/json",
                    "X-Conduit-Token": "tok_old_111",
                },
                "request_body": json.dumps({
                    "conversationId": "conv_old_111",
                    "prompt": "Reply exactly one word: Omni.",
                }),
            },
        ],
    }
    session_file.write_text(json.dumps(blueprint, indent=2), encoding="utf-8")

    # Unit check on extract_bootstrap_tokens + thread_bootstrap_into_leg
    boot_json = '{"data": {"conversation_id": "conv_live_999", "conduit_token": "tok_live_888"}}'
    tokens = extract_bootstrap_tokens(boot_json)
    assert tokens["conversation_id"] == "conv_live_999"
    assert tokens["conduit_token"] == "tok_live_888"

    old_tokens = extract_bootstrap_tokens(blueprint["recorded_exchanges"][0]["response_body"])
    threaded_leg2 = thread_bootstrap_into_leg(
        blueprint["recorded_exchanges"][1], tokens, old_tokens=old_tokens
    )
    assert "conversation_id=conv_live_999" in threaded_leg2["url"]
    assert threaded_leg2["request_headers"]["X-Conduit-Token"] == "tok_live_888"
    assert json.loads(threaded_leg2["request_body"])["conversationId"] == "conv_live_999"

    # End-to-end check through UniversalSessionClient.chat()
    client = UniversalSessionClient(session_file)
    captured_calls = []

    def fake_fire(method, url, headers, body, timeout):
        captured_calls.append((method, url, dict(headers), body))
        return SimpleNamespace(
            status_code=200,
            ok=True,
            text=boot_json,
            headers={"content-type": "application/json"},
            cookies=[SimpleNamespace(name="leg1_cookie", value="val1")],
            history=[],
            raise_for_status=lambda: None,
        )

    import multistep_replay

    def fake_curl_request(method, url, **kwargs):
        captured_calls.append((method, url, dict(kwargs.get("headers") or {}), kwargs.get("content") or kwargs.get("data")))
        return SimpleNamespace(
            status_code=200,
            ok=True,
            text='data: {"choices":[{"delta":{"content":"58"}}]}\ndata: [DONE]\n',
            headers={"content-type": "text/event-stream"},
            cookies=[SimpleNamespace(name="leg2_cookie", value="val2")],
            history=[],
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr(client, "_fire", fake_fire)
    if multistep_replay._HAVE_CURL_CFFI:
        monkeypatch.setattr(multistep_replay.curl_cffi, "request", fake_curl_request)
    else:
        monkeypatch.setattr(multistep_replay.requests, "request", fake_curl_request)

    res = client.chat([{"role": "user", "content": "What is 41 + 17?"}])
    assert res["text"] == "58"
    assert "multistep:generic_multistep" in res["label"]
    assert len(captured_calls) == 2
    leg2_method, leg2_url, leg2_hdrs, leg2_body = captured_calls[1]
    assert "conv_live_999" in leg2_url
    assert leg2_hdrs["X-Conduit-Token"] == "tok_live_888"
    assert b"What is 41 + 17?" in leg2_body
    # Both Leg 1 and Leg 2 cookies must be absorbed into the client jar
    assert "leg1_cookie=val1" in client.headers["Cookie"]
    assert "leg2_cookie=val2" in client.headers["Cookie"]


# ===========================================================================
# Q4: Datacenter ASN & Egress TLS Impersonation
# ===========================================================================

def test_q4_egress_proxy_resolution_and_ws_proxy_parsing(monkeypatch):
    monkeypatch.delenv("OMNIROUTE_PROXY", raising=False)
    monkeypatch.delenv("OMNIROUTE_PROXY_CHAT_EXAMPLE_COM", raising=False)

    # 1. Global env fallback
    monkeypatch.setenv("OMNIROUTE_PROXY", "http://global-proxy.local:8080")
    assert resolve_egress_proxy({}, "chat.example.com") == "http://global-proxy.local:8080"

    # 2. Host-specific env overrides global
    monkeypatch.setenv("OMNIROUTE_PROXY_CHAT_EXAMPLE_COM", "socks5://user:pass@res-proxy.local:1080")
    assert resolve_egress_proxy({}, "chat.example.com") == "socks5://user:pass@res-proxy.local:1080"

    # 3. Per-seat blueprint key overrides env
    assert (
        resolve_egress_proxy({"proxy": "http://seat-proxy.local:3128"}, "chat.example.com")
        == "http://seat-proxy.local:3128"
    )

    # 4. WebSocket proxy kwargs parsing
    ws_kw = _parse_ws_proxy_kwargs("socks5h://alice:secret123@res.proxy.net:9050")
    assert ws_kw == {
        "http_proxy_host": "res.proxy.net",
        "http_proxy_port": 9050,
        "proxy_type": "socks5h",
        "http_proxy_auth": ("alice", "secret123"),
    }


# ===========================================================================
# Q5: Binary Protobuf / gRPC-Web / WebSocket Frames
# ===========================================================================

def _make_proto_field_string(field_num: int, text: str) -> bytes:
    b = text.encode("utf-8")
    tag = (field_num << 3) | 2
    return _encode_varint(tag) + _encode_varint(len(b)) + b


def _make_proto_field_bytes(field_num: int, payload: bytes) -> bytes:
    tag = (field_num << 3) | 2
    return _encode_varint(tag) + _encode_varint(len(payload)) + payload


def _make_proto_field_varint(field_num: int, val: int) -> bytes:
    tag = (field_num << 3) | 0
    return _encode_varint(tag) + _encode_varint(val)


def test_q5_binary_protobuf_and_grpc_web_varint_and_frame_recomputation(tmp_path: Path):
    sentinel = "Reply exactly one word: Omni."
    # Construct a nested Protobuf message:
    # OuterMessage {
    #   field 1 (varint) = 42
    #   field 2 (SubMessage) = {
    #     field 1 (string) = "user"
    #     field 3 (string) = "Reply exactly one word: Omni."
    #   }
    #   field 5 (string) = "model-v1"
    # }
    inner_msg = _make_proto_field_string(1, "user") + _make_proto_field_string(3, sentinel)
    outer_msg = (
        _make_proto_field_varint(1, 42)
        + _make_proto_field_bytes(2, inner_msg)
        + _make_proto_field_string(5, "model-v1")
    )

    # Wrap in a 5-byte gRPC-Web envelope: \x00 + 4-byte big-endian length
    grpc_frame = b"\x00" + struct.pack(">I", len(outer_msg)) + outer_msg
    assert _is_grpc_web_framed(grpc_frame)

    # Replace sentinel with a much longer prompt (>128 bytes so varint transitions from 1 byte to 2 bytes!)
    long_prompt = "Compute the exact arithmetic sum of 41 + 17 and reply with only the numeric digits without any extra prose or punctuation marks at all: " + ("X" * 30)
    patched_frame, hits = substitute_protobuf_bytes(
        grpc_frame, long_prompt, content_type="application/grpc-web+proto"
    )
    assert hits == 1
    assert _is_grpc_web_framed(patched_frame)

    # Verify outer 5-byte gRPC-Web big-endian length header matches exact payload size
    new_frame_len = struct.unpack(">I", patched_frame[1:5])[0]
    assert new_frame_len == len(patched_frame) - 5

    # Verify recursive Protobuf extraction recovers all strings intact without corruption
    extracted = extract_protobuf_strings(patched_frame)
    assert extracted == ["user", long_prompt, "model-v1"]

    # Also test `application/grpc-web-text` (base64-encoded gRPC-Web frame)
    b64_input = base64.b64encode(grpc_frame)
    patched_b64, hits_b64 = substitute_protobuf_bytes(
        b64_input, "Short prompt?", content_type="application/grpc-web-text"
    )
    assert hits_b64 == 1
    decoded_b64 = base64.b64decode(patched_b64)
    assert _is_grpc_web_framed(decoded_b64)
    assert extract_protobuf_strings(decoded_b64) == ["user", "Short prompt?", "model-v1"]

    # Test binary frame injection in WebSocketSessionClient
    ws_file = tmp_path / "session_ws_binary.json"
    ws_file.write_text(
        json.dumps({
            "host": "binary-ws.example.com",
            "transport": "websocket",
            "recorded_ws": {
                "url": "wss://binary-ws.example.com/ws",
                "sent_frames": [
                    {"type": "binary", "data_b64": base64.b64encode(grpc_frame).decode("ascii")}
                ],
            },
        }),
        encoding="utf-8",
    )
    ws_client = WebSocketSessionClient(ws_file)
    injected_frames = ws_client._inject("What is 41 + 17?")
    assert len(injected_frames) == 1
    assert isinstance(injected_frames[0], bytes)
    assert _is_grpc_web_framed(injected_frames[0])
    assert extract_protobuf_strings(injected_frames[0]) == ["user", "What is 41 + 17?", "model-v1"]
