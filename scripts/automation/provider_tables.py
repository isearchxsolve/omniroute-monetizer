"""Extract OmniRoute's provider tables from the readable server bundle.

Why this exists
---------------
`video_registry.py` reads the Next.js *chunks* and only knows the media registries
(VIDEO/MUSIC/IMAGE/AUDIO_*). But `dist/open-sse/mcp-server/server.js` is NOT minified -- it
still carries its original source paths -- and it holds the tables that classify EVERY provider
by how it authenticates:

    src/shared/constants/providers/noauth.ts      -> NOAUTH_PROVIDERS
    src/shared/constants/providers/local.ts       -> LOCAL_PROVIDERS
    src/shared/constants/providers/oauth.ts       -> OAUTH_PROVIDERS
    src/shared/constants/providers/web-cookie.ts  -> WEB_COOKIE_PROVIDERS
    src/shared/constants/providers/apikey.ts      -> APIKEY_PROVIDERS

This matters because the catalog file `state/all_295_providers_catalog.json` carries NO auth
field -- every entry reads `auth=?` -- so there was no way to tell which of the 220 unwired
providers need money and which need nothing. NOAUTH + LOCAL are precisely the ones that need
neither a payment nor a signup.

Measured 2026-08-22: 296 catalog providers, 92 connection rows covering 76 distinct providers,
so 220 providers had never been wired at all.

Read-only. Touches nothing but the installed build.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import video_registry as vr  # noqa: E402

SERVER_JS = (
    pathlib.Path(vr.DEFAULT_OMNIROUTE_DIST) / "open-sse" / "mcp-server" / "server.js"
)

TABLES = (
    "NOAUTH_PROVIDERS",
    "LOCAL_PROVIDERS",
    "OAUTH_PROVIDERS",
    "WEB_COOKIE_PROVIDERS",
    "APIKEY_PROVIDERS",
)

# Auth classes that cost neither money nor a signup.
FREE_TABLES = ("NOAUTH_PROVIDERS", "LOCAL_PROVIDERS")


def _match_literal(src: str, name: str) -> str:
    """Return the `{...}` object literal assigned to `name` in server.js.

    video_registry._extract_object_literal cannot be reused here: it looks for the export /
    local-binding shapes used by the Next.js chunks, but server.js wraps these tables as

        var NOAUTH_PROVIDERS;
        var init_noauth = __esm({
          "src/shared/constants/providers/noauth.ts"() {
            NOAUTH_PROVIDERS = { opencode: { id: "opencode", ... } };

    so the binding is a plain assignment inside a function. We find `NAME =` followed by `{`
    and brace-match forward, skipping over string literals, template literals and comments so
    that a `}` inside a URL or a description never ends the scan early.
    """
    import re

    m = re.search(rf"\b{re.escape(name)}\s*=\s*\{{", src)
    if m is None:
        raise vr.RegistryNotFound(f"no assignment `{name} = {{` found in server.js")

    i = src.index("{", m.start())
    depth = 0
    quote = None          # active string delimiter, or None
    n = len(src)
    while i < n:
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = src[i + 1]
            if nxt == "/":
                i = src.find("\n", i)
                if i == -1:
                    break
                continue
            if nxt == "*":
                end = src.find("*/", i + 2)
                i = n if end == -1 else end + 2
                continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[src.index("{", m.start()): i + 1]
        i += 1
    raise vr.RegistryNotFound(f"unbalanced braces while reading {name}")


def load_table(name: str, server_js: pathlib.Path = SERVER_JS) -> dict:
    """Return one provider table as JSON. Node evaluates the literal (it contains JS-isms)."""
    src = server_js.read_text(encoding="utf-8", errors="replace")
    return vr._eval_literal_to_json(_match_literal(src, name))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table", default="", help=f"one of {', '.join(TABLES)}; default = all")
    ap.add_argument("--json", action="store_true", help="dump raw JSON")
    ap.add_argument("--server-js", default=str(SERVER_JS))
    args = ap.parse_args()

    server_js = pathlib.Path(args.server_js)
    if not server_js.exists():
        print(f"[-] not found: {server_js}")
        return 3

    wanted = [args.table] if args.table else list(TABLES)
    out = {}
    for name in wanted:
        try:
            out[name] = load_table(name, server_js)
        except Exception as exc:
            print(f"[!] {name}: {type(exc).__name__}: {exc}")

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    total = 0
    for name, table in out.items():
        ids = sorted(table)
        total += len(ids)
        tag = "  <-- FREE: no key, no signup" if name in FREE_TABLES else ""
        print(f"\n=== {name}: {len(ids)} providers{tag}")
        for pid in ids:
            entry = table[pid] if isinstance(table[pid], dict) else {}
            base = entry.get("baseUrl") or entry.get("base_url") or ""
            models = entry.get("models")
            nmodels = len(models) if isinstance(models, list) else "?"
            print(f"    {pid:32} models={str(nmodels):>4}  {base[:60]}")
    print(f"\ntotal across {len(out)} tables: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
