"""Probe ALL media on the P2 tab after player open, then test CDP fetch of the asb stream.

Also try the DOM path the #1637 harvest used: maybe the tile is an <video> whose player
mounts a <flow-player> with a .getMediaUrl() or a <source> child. Deep-DOM dump of the
player subtree attributes.
"""
import json
import sys
import time

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page

DUMP = r"""
(() => {
  const out = [];
  document.querySelectorAll('video, source, [src], [data-src], flow-player, media-player').forEach(el => {
    const row = {tag: el.tagName, src: (el.src || el.getAttribute('data-src') || el.currentSrc || '').slice(0, 160)};
    for (const a of el.attributes || []) {
      if (/url|src|media/i.test(a.name)) row[a.name] = a.value.slice(0, 160);
    }
    out.push(row);
  });
  return JSON.stringify(out);
})()
"""

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    srcs = json.loads(pg.evaluate(DUMP, timeout=30))
    print("media elements:", len(srcs))
    for s in srcs:
        print(json.dumps(s))

    # try intercepting fetch/XHR of the CDN via injected hook, then re-click
    hook = r"""
(() => {
  if (window.__hooked) return 'ALREADY';
  window.__hits = [];
  const of = window.fetch;
  window.fetch = function(...a) {
    try { const u = String(a[0] && a[0].url || a[0]); if (/flow-content\.google\/video\//.test(u)) window.__hits.push(u); } catch (e) {}
    return of.apply(this, a);
  };
  const ox = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(m, u) {
    try { if (/flow-content\.google\/video\//.test(String(u))) window.__hits.push(String(u)); } catch (e) {}
    return ox.apply(this, arguments);
  };
  window.__hooked = true;
  return 'HOOKED';
})()
"""
    print("hook:", pg.evaluate(hook, timeout=30))
    opened = pg.evaluate(
        r"""
(() => {
  const vids = Array.from(document.querySelectorAll('video'));
  if (!vids.length) return JSON.stringify({ok: false});
  const v = vids[vids.length - 1];
  const card = v.closest('[role="button"], button, [tabindex]') || v;
  card.click();
  return JSON.stringify({ok: true});
})()
""", timeout=60)
    print("click:", opened)
    time.sleep(15)
    hits = pg.evaluate("(() => JSON.stringify(window.__hits || []))()", timeout=30)
    print("fetch/XHR hits:", json.loads(hits))
