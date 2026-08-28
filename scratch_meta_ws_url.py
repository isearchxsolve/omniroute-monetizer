"""P2: locate meta.ai's websocket URL + auth without reloading. Search page runtime, loaded
scripts, and any global socket refs. Read-only.
"""
import io, json, sys, time, pathlib, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from capture_sessions_cdp import CDP, targets

tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
t = tabs[0]
c = CDP(t["webSocketDebuggerUrl"])
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(1.0)
    c.call("Runtime.enable", timeout=25)

    # 1) search all loaded script sources for ws url patterns
    r = c.evaluate("""(() => {
      const out = {hits: [], globals: []};
      // scan window keys for websocket-ish objects
      for (const k of Object.keys(window)) {
        try {
          const v = window[k];
          if (v && typeof v === 'object') {
            const s = String(v);
            if (/WebSocket|wss?:\\/\\//.test(s) && s.length < 400) out.globals.push(k + ' => ' + s.slice(0,200));
          }
          if (typeof v === 'string' && /^wss?:\\/\\//.test(v)) out.globals.push(k + ' = ' + v);
        } catch(e){}
      }
      return out;
    })()""")
    print("window globals ws-ish:", json.dumps(r, indent=1)[:800])

    # 2) fetch each loaded script and grep for wss:// or websocket endpoint strings
    scripts = c.evaluate("""(() => [...document.querySelectorAll('script[src]')].map(s=>s.src))()""") or []
    print("loaded scripts:", len(scripts))
    import re
    found = set()
    for src in scripts:
        try:
            body = c.evaluate("(async()=>{const r=await fetch(%r);return await r.text();})()" % src)
        except Exception:
            body = None
        if not body: 
            # fallback: fetch via python
            try:
                body = urllib.request.urlopen(src, timeout=10).read().decode("utf-8","replace")
            except Exception:
                continue
        for m in re.findall(r'wss?://[A-Za-z0-9._/\\-]+', body):
            found.add(m)
        for m in re.findall(r'["\'](/api/[A-Za-z0-9._/\\-]*(?:ws|socket|stream|abracadabra|kadabra|realtime)[A-Za-z0-9._/\\-]*)["\']', body, re.I):
            found.add("PATH:" + m)
    print("ws-ish strings in scripts:")
    for f in sorted(found)[:40]: print("   ", f)

    # 3) check __NEXT_DATA__ / config blobs
    nd = c.evaluate("(() => { try { return JSON.stringify(window.__NEXT_DATA__||{}).slice(0,400);} catch(e){return 'err'} })()")
    print("__NEXT_DATA__ head:", nd)
finally:
    c.close()
