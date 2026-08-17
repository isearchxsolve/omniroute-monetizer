#!/usr/bin/env python3
"""Extract provider slug -> upstream baseUrl map from OmniRoute's open-sse bundles.

Scans all open-sse*.js chunks, finds objects of the form:
    slug:{id:"slug",baseUrl:"https://...",authType:"...",...}
and builds a deduplicated map. Output: state/provider_baseurls.json
"""
import json
import re
import sys
from pathlib import Path

CHUNKS_DIR = Path(r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks")
OUT = Path(__file__).resolve().parent.parent / "state" / "provider_baseurls.json"


def extract_from(text: str, out: dict) -> int:
    added = 0
    # slug:{id:"slug",baseUrl:"..."  (baseUrl may appear before or after id)
    for m in re.finditer(r'"?([A-Za-z0-9_\-]+)"?:\{', text):
        slug = m.group(1)
        start = text.index("{", m.start())
        # brace-match the object body
        depth = 0
        i = start
        end = -1
        in_str = False
        esc = False
        while i < len(text):
            ch = text[i]
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
        body = text[start:end + 1]
        # must contain both id:"slug" and baseUrl:"http"
        idm = re.search(r'\bid:"([^"]+)"', body)
        bum = re.search(r'baseUrl:"((?:[^"\\]|\\.)*)"', body)
        if not (idm and bum):
            continue
        if idm.group(1) != slug:
            continue
        url = bum.group(1)
        if not url.startswith("http"):
            continue
        atm = re.search(r'authType:"([^"]+)"', body)
        ahm = re.search(r'authHeader:"([^"]+)"', body)
        if slug not in out:
            out[slug] = {
                "baseUrl": url,
                "authType": atm.group(1) if atm else None,
                "authHeader": ahm.group(1) if ahm else None,
            }
            added += 1
    return added


def main() -> int:
    if not CHUNKS_DIR.exists():
        print(f"chunks dir not found: {CHUNKS_DIR}")
        return 1
    out = {}
    files = sorted(CHUNKS_DIR.glob("*.js"))
    # Only the provider-config chunk families carry baseUrl maps. Skip the
    # thousands of i18n/ssr/locale/route chunks that never contain them.
    keep = re.compile(r"^(open-sse|src_shared|\[root-of-the-server\]|src_)", re.I)
    files = [f for f in files if keep.search(f.name)]
    files = [f for f in files if not re.search(r"i18n|messages_|_json_|ssr|locale", f.name, re.I)]
    print(f"scanning {len(files)} chunks (provider-config families only)")
    for idx, f in enumerate(files):
        if f.stat().st_size > 8_000_000:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        n = extract_from(text, out)
        if n:
            print(f"  {f.name}: +{n} (total {len(out)})")
            # incremental save so progress is never lost
            OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\ntotal providers with baseUrl: {len(out)}")
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
