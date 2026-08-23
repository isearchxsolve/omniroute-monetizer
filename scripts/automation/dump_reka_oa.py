"""Dump reka and openadapter entries from server.js.
"""
from __future__ import annotations
import sys
import json
import pathlib
import tempfile
import subprocess as sp
import re

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import provider_tables as pt

src = pt.SERVER_JS.read_text(encoding="utf-8", errors="replace")
lits = {}
def resolve(name: str):
    if name in lits:
        return
    lit = pt._match_literal(src, name)
    lits[name] = lit
    for m in re.finditer(r"\.\.\.\s*([A-Z][A-Z0-9_]{3,})", lit):
        resolve(m.group(1))

resolve("APIKEY_PROVIDERS")
preamble = "\n".join(f"const {k} = {v};" for k, v in reversed(list(lits.items())))
js = preamble + "\nprocess.stdout.write(JSON.stringify({reka: APIKEY_PROVIDERS.reka, openadapter: APIKEY_PROVIDERS.openadapter}, null, 2));"

with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d) / "dump.js"
    p.write_text(js, encoding="utf-8")
    proc = sp.run(["node", str(p)], capture_output=True, text=True, timeout=30)
    print(proc.stdout)
