# -*- coding: utf-8 -*-
"""End-to-end: dispatch a chat through the shim's HTTP face for each live chrome host.
Proves pool -> _client_for -> ChromeReplayClient -> tab works, not just direct calls."""
import json, time, urllib.request

HOSTS = ["claude.ai", "grok.com", "copilot.microsoft.com", "v0.app"]

def call(host):
    body = json.dumps({
        "model": host + "/auto",
        "messages": [{"role": "user", "content": "Reply with exactly one word: Omni."}],
        "max_tokens": 64,
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8190/v1/chat/completions",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=180).read())
        text = d["choices"][0]["message"]["content"]
        return "OK %dms text=%r" % (int((time.time()-t0)*1000), text[:80])
    except Exception as e:
        return "ERR %s" % e

for h in HOSTS:
    print("%-24s %s" % (h, call(h)))
