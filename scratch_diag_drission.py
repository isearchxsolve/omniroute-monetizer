"""scratch_diag_drission.py — isolate where DrissionPage hangs during replay.

Steps, each printed + flushed, each with a hard timeout:
 1. connect
 2. list tab_ids
 3. get_tab for each id (timed)
 4. trivial run_js function-mode
 5. trivial async-IIFE as_expr
 6. real fetch against one session (perplexity) both ways
"""
import json, pathlib, sys, time, urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts" / "automation"))

def step(name):
    print(f"[{time.strftime('%H:%M:%S')}] {name}", flush=True)

step("1. connect")
from DrissionPage import ChromiumPage
page = ChromiumPage(addr_or_opts="127.0.0.1:9222")
step(f"   connected, tab_ids={len(page.tab_ids)}")

step("2. iterate get_tab")
origin_map = {}
t0 = time.perf_counter()
for tid in page.tab_ids:
    ta = time.perf_counter()
    try:
        t = page.get_tab(tid)
        u = t.url
    except Exception as e:
        print(f"   tab {tid[:8]} get_tab FAILED: {e}", flush=True)
        continue
    o = urllib.parse.urlsplit(u)
    origin = f"{o.scheme}://{o.netloc}"
    origin_map.setdefault(origin, t)
    print(f"   tab {tid[:8]} {time.perf_counter()-ta:5.2f}s {origin}", flush=True)
step(f"   iterate total {time.perf_counter()-t0:.1f}s, {len(origin_map)} origins")

# pick a tab to test JS on — use perplexity if present, else first
test_origin = next((o for o in origin_map if "perplexity" in o), next(iter(origin_map)))
tab = origin_map[test_origin]
step(f"3. JS tests on {test_origin}")

step("   3a. function-mode: return 1+1")
try:
    r = tab.run_js("return 1+1;", timeout=10)
    print(f"       -> {r!r}", flush=True)
except Exception as e:
    print(f"       FAILED: {e}", flush=True)

step("   3b. as_expr async IIFE: await Promise.resolve(42)")
try:
    r = tab.run_js("(async () => { return await Promise.resolve(42); })()", as_expr=True, timeout=10)
    print(f"       -> {r!r}", flush=True)
except Exception as e:
    print(f"       FAILED: {e}", flush=True)

step("   3c. function-mode async fetch (window-stash + poll)")
JS_STASH = r"""
window.__diag = null;
(async () => {
  try {
    const r = await fetch('https://www.perplexity.ai/rest/thread/list_recent', {
      method: 'GET', credentials: 'include'
    });
    window.__diag = { status: r.status, ok: true };
  } catch (e) {
    window.__diag = { ok: false, error: String(e) };
  }
})();
return 'launched';
"""
try:
    r = tab.run_js(JS_STASH, timeout=10)
    print(f"       launch -> {r!r}", flush=True)
    for i in range(20):
        time.sleep(0.5)
        st = tab.run_js("return window.__diag;", timeout=5)
        if st is not None:
            print(f"       result after {(i+1)*0.5:.1f}s -> {st}", flush=True)
            break
    else:
        print("       TIMEOUT waiting for window.__diag", flush=True)
except Exception as e:
    print(f"       FAILED: {e}", flush=True)

step("DONE")
