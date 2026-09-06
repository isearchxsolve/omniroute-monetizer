"""Search the P2 page's full HTML for signed flow-content CDN URLs (read-only)."""
import json
import sys

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from cdp import Page

JS = r"""
(() => {
  const html = document.documentElement.outerHTML;
  const re = /flow-content\.google\/(?:video|image)\/[0-9a-f-]{36}\?[^"'\\ ]+/g;
  const m = html.match(re) || [];
  return JSON.stringify(Array.from(new Set(m)).slice(0, 30));
})()
"""

with Page(match="flow.google.com/project/", timeout=30, port=9226) as pg:
    raw = pg.evaluate(JS, timeout=60)
urls = json.loads(raw)
print(f"found {len(urls)} signed CDN url(s) in page HTML:")
for u in urls:
    print(" ", u[:180])
