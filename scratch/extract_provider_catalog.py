#!/usr/bin/env python3
"""Extract the full OmniRoute provider catalog from the app's bundled JS.

The catalog lives in the Next.js server chunk and maps each provider slug to:
  id, alias, name, website, hasFree, freeNote, authHint, signupUrl, baseUrl (if present)

Output: state/provider_catalog_extracted.json
This replaces the ASSUMED 'EXTERNAL_ACCOUNT_REQUIRED' classification with the
app's own per-provider metadata, which is the input for a real per-provider scan.
"""
import json
import re
import sys
from pathlib import Path

CHUNK = Path(r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\src_0gt0n9b._.js")
OUT = Path(__file__).resolve().parent.parent / "state" / "provider_catalog_extracted.json"


def main() -> int:
    if not CHUNK.exists():
        print(f"chunk not found: {CHUNK}")
        return 1
    c = CHUNK.read_text(encoding="utf-8", errors="replace")
    print(f"chunk length: {len(c)}")

    # Field occurrence counts (sanity)
    for field in ("id:", "signupUrl:", "hasFree:", "authHint:", "baseUrl:", "website:"):
        print(f"  {field:12s} {len(re.findall(re.escape(field), c))}")

    # The catalog is a big object literal:  slug:{id:"slug",...},slug2:{...}
    # Strategy: find each `slug:{` start, then brace-match to the closing `}`.
    providers = {}
    # Match object keys that look like provider slugs followed by :{id:"..."
    # Keys may be unquoted (foo:) or quoted ("360ai":) — handle both.
    for m in re.finditer(r'"?([A-Za-z0-9_\-]+)"?:\{id:"([^"]+)"', c):
        slug = m.group(1)
        start = c.index("{", m.start())
        # brace match
        depth = 0
        i = start
        end = -1
        in_str = False
        esc = False
        while i < len(c):
            ch = c[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            i += 1
        if end == -1:
            continue
        body = c[start:end + 1]

        def grab(field):
            mm = re.search(field + r':"((?:[^"\\]|\\.)*)"', body)
            return mm.group(1) if mm else None

        def grabbool(field):
            mm = re.search(field + r':(!0|!1|true|false)', body)
            if not mm:
                return None
            return mm.group(1) in ("!0", "true")

        providers[slug] = {
            "id": grab("id"),
            "alias": grab("alias"),
            "name": grab("name"),
            "website": grab("website"),
            "signupUrl": grab("signupUrl"),
            "baseUrl": grab("baseUrl"),
            "authHint": grab("authHint"),
            "freeNote": grab("freeNote"),
            "hasFree": grabbool("hasFree"),
            "passthroughModels": grabbool("passthroughModels"),
        }

    print(f"\nextracted providers: {len(providers)}")
    with_base = sum(1 for p in providers.values() if p["baseUrl"])
    with_free = sum(1 for p in providers.values() if p["hasFree"])
    with_signup = sum(1 for p in providers.values() if p["signupUrl"])
    print(f"  with baseUrl:   {with_base}")
    print(f"  with hasFree:   {with_free}")
    print(f"  with signupUrl: {with_signup}")

    OUT.write_text(json.dumps(providers, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
