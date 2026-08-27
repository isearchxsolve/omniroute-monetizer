import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts" / "automation"))

from browser_replay import list_pages, TabSession, build_fetch_js, get_tab_session, origin_of
from universal_replay import UniversalSessionClient

SECRETS = HERE / "state" / "secrets"
pages = list_pages(9222)
tab_cache = {}

prompt = "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"
expect = "the holy cow jumps over the stricks"

for file_name in [
    "session_cohere_coral_web.json",
    "session_qwen_chat_(alibaba).json",
    "session_zhipu_glm_chat.json",
    "session_cerebras_inference_chat.json",
]:
    f = SECRETS / file_name
    if not f.exists():
        continue
    client = UniversalSessionClient(f)
    new_body = client._inject_prompt(prompt)
    origin = origin_of(client.url)
    sess = tab_cache.get(origin)
    if sess is None:
        sess = get_tab_session(9222, pages, origin)
        tab_cache[origin] = sess
    js = build_fetch_js(client.url, client.method, client.headers, new_body, expect)
    res = sess.evaluate(js, timeout=60)
    print("=" * 70)
    print("FILE:", file_name)
    print("STATUS:", res.get("status"))
    body = res.get("body", "")
    print("BODY LENGTH:", len(body))
    print("BODY (first 2000 chars):")
    print(body[:2000])

for s in tab_cache.values():
    s.close()

