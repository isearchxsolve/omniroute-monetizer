"""Check baseUrl for agentrouter in server.js.
"""
from __future__ import annotations
import pathlib
import re

server_js = pathlib.Path(r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\open-sse\mcp-server\server.js")
txt = server_js.read_text(encoding="utf-8", errors="replace")

for m in re.finditer(r"agentrouter[^\n]{0,150}", txt):
    print(m.group(0))
