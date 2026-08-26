#!/usr/bin/env python3
"""Where, exactly, is the model's answer inside a provider's response body?

Run after `replay_check.py` reports a session as live-but-badly-extracted. It reads the raw bodies
saved under state/replay_raw/ and prints the PATH to every short string, so the answer's position can
be pinned instead of guessed. That pinning is the difference between "the session replies" and "the
router can hand a clean answer to oioi".

Two response families needed this:

  * Google (Gemini, and by extension Flow / AI Studio) wraps the reply in a batchexecute body:
    `)]}'`, then alternating length lines and JSON payloads, each `[["wrb.fr",null,"<escaped json>"]]`
    whose third element is JSON *inside* a JSON string. Parsed here with json.loads over the
    length-prefixed framing -- NOT with a regex, which cannot survive the escaping.
  * Mistral answers `text/event-stream` but does not send SSE. It sends tRPC-style numbered chunks
    (`15:{"json":{...}}`), so every `data:`-based parser sees nothing.

Reads local files only. Prints response content, never a request header, cookie or token.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "state" / "replay_raw"

XSSI = (")]}'", "while(1);", "for(;;);")


def strip_xssi(text: str) -> str:
    t = (text or "").lstrip()
    for p in XSSI:
        if t.startswith(p):
            return t[len(p):].lstrip()
    return text


def google_chunks(text: str) -> list:
    """Parse the length-prefixed batchexecute framing into decoded payloads.

    Framing is `<len>\\n<json>\\n<len>\\n<json>...`. The length counts characters of the JSON that
    follows, but chunk boundaries are also newline-aligned, so a decoder that just tries json.loads
    on each candidate is more robust than trusting the count.
    """
    t = strip_xssi(text)
    out = []
    dec = json.JSONDecoder()
    i = 0
    while i < len(t):
        while i < len(t) and t[i] not in "[{":
            i += 1
        if i >= len(t):
            break
        try:
            obj, end = dec.raw_decode(t, i)
        except ValueError:
            i += 1
            continue
        out.append(obj)
        i = end
    return out


def unwrap_wrb(obj) -> list:
    """`[["wrb.fr",null,"<escaped json>"]]` -> the decoded inner documents."""
    found = []
    if isinstance(obj, list):
        for row in obj:
            if (isinstance(row, list) and len(row) >= 3
                    and row[0] == "wrb.fr" and isinstance(row[2], str)):
                try:
                    found.append(json.loads(row[2]))
                except ValueError:
                    found.append(row[2])
            else:
                found.extend(unwrap_wrb(row))
    return found


def walk(node, path: str = "", depth: int = 0):
    if depth > 14:
        return
    if isinstance(node, str):
        if node.strip():
            yield path, node
    elif isinstance(node, list):
        for j, v in enumerate(node):
            yield from walk(v, f"{path}[{j}]", depth + 1)
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}[{k!r}]", depth + 1)


def trpc_chunks(text: str) -> list:
    """Mistral's numbered chunks: `<n>:<json>` one per line."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        head, _, rest = line.partition(":")
        if not head.isdigit():
            continue
        try:
            out.append((head, json.loads(rest)))
        except ValueError:
            out.append((head, rest))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--needle", default="erifi",
                    help="substring that marks the answer, so its path can be reported")
    ap.add_argument("--only", default="", help="comma-separated filename substrings")
    ap.add_argument("--max-len", type=int, default=200,
                    help="ignore strings longer than this (they are payloads, not answers)")
    a = ap.parse_args()

    if not RAW.exists():
        print(f"no {RAW} -- run the raw-dump step first")
        return 1
    files = sorted(RAW.glob("*.txt"))
    if a.only:
        want = [w.strip().lower() for w in a.only.split(",") if w.strip()]
        files = [f for f in files if any(w in f.name.lower() for w in want)]

    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        print(f"=== {f.name}  {len(text)} bytes")

        docs = []
        if "wrb.fr" in text:
            for obj in google_chunks(text):
                docs.extend(unwrap_wrb(obj))
            print(f"    google batchexecute: {len(docs)} inner documents")
        elif trpc_chunks(text):
            docs = [d for _, d in trpc_chunks(text)]
            print(f"    trpc numbered chunks: {len(docs)}")
        else:
            print("    no recognised envelope")
            continue

        hits, shown = [], 0
        for n, doc in enumerate(docs):
            for path, s in walk(doc, f"doc{n}"):
                if len(s) > a.max_len:
                    continue
                if a.needle.lower() in s.lower():
                    hits.append((path, s))
                elif shown < 12:
                    print(f"    {path:44s} {s[:64]!r}")
                    shown += 1
        for path, s in hits:
            print(f"    ANSWER-> {path:36s} {s[:80]!r}")
        if not hits:
            print(f"    needle {a.needle!r} not found in any string <= {a.max_len} chars")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
