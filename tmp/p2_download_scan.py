"""Try Flow's own downloads: click the newest tile's download affordance if present.

Flow tiles expose a download button in the expanded view. Read-only-ish: a click on the
app's own download control triggers the browser to fetch the signed CDN URL, which our
hooked fetch/XHR + Network events can observe. No keyboard, no credentials.
"""
import json
import sys
import time

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page

SCAN = r"""
(() => {
  const btns = Array.from(document.querySelectorAll('button, a, [role="button"]'));
  const hits = btns.filter(b => {
    const t = ((b.getAttribute('aria-label') || '') + ' ' + (b.textContent || '')).toLowerCase();
    return /download|save/.test(t);
  }).map(b => ({
    tag: b.tagName, label: (b.getAttribute('aria-label') || b.textContent || '').slice(0, 40),
    visible: b.getBoundingClientRect().width > 0
  }));
  return JSON.stringify(hits);
})()
"""

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    hits = json.loads(pg.evaluate(SCAN, timeout=30))
    print("download-ish controls:", json.dumps(hits, indent=2))
