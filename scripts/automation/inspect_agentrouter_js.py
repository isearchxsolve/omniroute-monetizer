"""Inspect agentrouter in server.js.
"""
from __future__ import annotations
import pathlib
import re

server_js = pathlib.Path(r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\open-sse\mcp-server\server.js")
if server_js.exists():
    txt = server_js.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"agentrouter\s*:\s*\{[^}]{1,500}\}", txt):
        print("Found agentrouter definition:\n", m.group(0))
else:
    print("server.js not found at:", server_js)
