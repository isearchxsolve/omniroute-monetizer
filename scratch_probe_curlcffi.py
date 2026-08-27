"""Probe curl_cffi API surface so the universal_replay wiring is exact, not guessed."""
import curl_cffi

print("has curl_cffi.request :", hasattr(curl_cffi, "request"))
print("has curl_cffi.Session :", hasattr(curl_cffi, "Session"))

# exceptions module
try:
    from curl_cffi.requests import exceptions as e
    print("exceptions:", [n for n in dir(e) if n[0].isupper()])
except Exception as ex:
    print("exc import fail:", ex)

# Does default_headers=False work + does response expose the attrs we rely on?
r = curl_cffi.request(
    "GET", "https://httpbin.org/headers",
    headers={"User-Agent": "ProbeUA/1.0", "X-Probe": "1"},
    impersonate="chrome",
    default_headers=False,
    timeout=30,
)
print("status_code:", r.status_code)
print("has .ok     :", hasattr(r, "ok"), getattr(r, "ok", None))
print("has .text   :", hasattr(r, "text"))
print("has .cookies:", hasattr(r, "cookies"), type(r.cookies).__name__)
print("has .history:", hasattr(r, "history"))
print("has raise_for_status:", hasattr(r, "raise_for_status"))
import json
sent = json.loads(r.text)["headers"]
print("sent UA     :", sent.get("User-Agent"))
print("sent X-Probe:", sent.get("X-Probe"))
print("sent sec-ch-ua present (should be ABSENT w/ default_headers=False):", "Sec-Ch-Ua" in sent)

# POST with content= bytes
r2 = curl_cffi.request(
    "POST", "https://httpbin.org/post",
    headers={"Content-Type": "application/json"},
    content=b'{"hello":"world"}',
    impersonate="chrome",
    default_headers=False,
    timeout=30,
)
d = json.loads(r2.text)
print("POST status :", r2.status_code)
print("POST data   :", d.get("data"))
print("POST ct     :", d.get("headers", {}).get("Content-Type"))

# cookie iteration shape (for _absorb_cookies)
r3 = curl_cffi.request("GET", "https://httpbin.org/cookies/set/foo/bar",
                       impersonate="chrome", timeout=30)
for c in r3.cookies:
    print("cookie obj:", type(c).__name__, "name=", getattr(c, "name", "?"), "value=", getattr(c, "value", "?"))
