"""cookie_porter.py -- export/import provider sessions via CDP (bypasses DPAPI).

PORTING.md previously said "profiles cannot be copied." That was true for the
on-disk Cookies DB (DPAPI-sealed to this Windows user+machine). But a LIVE
Chrome with CDP enabled exposes ALL decrypted cookies via Storage.getCookies --
including HttpOnly ones. Those can be re-injected into a fresh profile on ANY
machine via Storage.setCookies.

This tool makes provider-session portability real:

  EXPORT (old machine, Chrome running with CDP):
    python cookie_porter.py --export --ports 9222,9223,9224,9225 --out D:\\omni_bundle\\provider_sessions.json

  IMPORT (new machine, fresh Chrome profile running with CDP):
    python cookie_porter.py --import --port 9222 --in D:\\omni_bundle\\provider_sessions.json

The export file is a credential store -- treat it like state/secrets/. Never
commit it, never sync it to a third party.

What this DOES port:
  - Provider site sessions (cookies for claude.ai, groq.com, perplexity.ai, etc.)
  - HttpOnly auth cookies (session tokens, JWTs)
  - localStorage is NOT included (cookies only) -- some sites may need re-login

What this does NOT port:
  - Google account sign-in (DBSC device-bound, will be revoked on new machine)
  - localStorage/sessionStorage (some SPAs store tokens there)
  - The Chrome profile itself (bookmarks, extensions, etc.)

Usage:
  python cookie_porter.py --export [--ports 9222,9223,9224,9225] [--out PATH]
  python cookie_porter.py --import --port 9222 --in PATH [--domains claude.ai,grok.com]
  python cookie_porter.py --list --in PATH          # show what's in an export
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_PORTS = [9222, 9223, 9224, 9225]
DEFAULT_OUT = Path(r"D:\omniroute-monetizer\state\secrets\provider_sessions_export.json")


def get_ws_url(port: int) -> str:
    """Get browser-level websocket URL for a CDP port."""
    url = f"http://127.0.0.1:{port}/json/version"
    with urllib.request.urlopen(url, timeout=5) as r:
        info = json.loads(r.read())
    ws = info.get("webSocketDebuggerUrl")
    if not ws:
        raise RuntimeError(f"port {port}: no webSocketDebuggerUrl")
    return ws


def cdp_call(ws, method: str, params: dict = None, timeout: int = 30):
    """Send a CDP command and return the result."""
    import websocket
    msg_id = id(method) % 100000
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        resp = json.loads(ws.recv())
        if resp.get("id") == msg_id:
            if "error" in resp:
                raise RuntimeError(f"{method}: {resp['error']}")
            return resp.get("result", {})


def export_cookies(ports: list, out_path: Path) -> int:
    """Export all cookies from all specified CDP ports."""
    import websocket
    all_cookies = {}  # domain -> [cookies]
    total = 0

    for port in ports:
        try:
            ws_url = get_ws_url(port)
        except Exception as e:
            print(f"  port {port}: SKIP ({e})")
            continue

        ws = websocket.create_connection(ws_url, timeout=15)
        try:
            result = cdp_call(ws, "Storage.getCookies")
            cookies = result.get("cookies", [])
            print(f"  port {port}: {len(cookies)} cookies")
            for c in cookies:
                domain = c.get("domain", "").lstrip(".")
                parts = domain.split(".")
                key = ".".join(parts[-2:]) if len(parts) >= 2 else domain
                if key not in all_cookies:
                    all_cookies[key] = []
                # Deduplicate by (domain, name, path)
                existing = {(x["domain"], x["name"], x.get("path", "/")) for x in all_cookies[key]}
                ident = (c["domain"], c["name"], c.get("path", "/"))
                if ident not in existing:
                    all_cookies[key].append(c)
                    total += 1
        finally:
            ws.close()

    # Build export manifest
    export = {
        "version": 1,
        "exported_at": __import__("datetime").datetime.now().isoformat(),
        "source_ports": ports,
        "total_cookies": total,
        "total_domains": len(all_cookies),
        "cookies_by_domain": all_cookies,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(export, indent=1), encoding="utf-8")
    print(f"\nEXPORTED: {total} cookies across {len(all_cookies)} domains -> {out_path}")
    print(f"WARNING: This file contains live session cookies. Treat as a credential store.")
    return 0


def import_cookies(port: int, in_path: Path, domains: list = None) -> int:
    """Import cookies into a Chrome instance via CDP Storage.setCookies."""
    import websocket

    data = json.loads(in_path.read_text(encoding="utf-8-sig"))
    cookies_by_domain = data.get("cookies_by_domain", {})

    if domains:
        # Filter to requested domains only
        filtered = {}
        for dom, cookies in cookies_by_domain.items():
            if any(d in dom for d in domains):
                filtered[dom] = cookies
        cookies_by_domain = filtered
        print(f"Filtered to {len(cookies_by_domain)} domains matching {domains}")

    total = sum(len(v) for v in cookies_by_domain.values())
    print(f"Importing {total} cookies across {len(cookies_by_domain)} domains into port {port}")

    ws_url = get_ws_url(port)
    ws = websocket.create_connection(ws_url, timeout=15)
    try:
        imported = 0
        errors = 0
        for domain, cookies in cookies_by_domain.items():
            # Storage.setCookies takes a list of cookies
            # Need to set them per-domain via Network.setCookies on a page target,
            # or use Storage.setCookies at browser level
            try:
                cdp_call(ws, "Storage.setCookies", {"cookies": cookies})
                imported += len(cookies)
            except Exception as e:
                # Fallback: try Network.setCookies (needs a target)
                errors += 1
                if errors <= 3:
                    print(f"  {domain}: {e}")
        print(f"\nIMPORTED: {imported} cookies ({errors} domain errors)")
        if imported > 0:
            print("Provider sessions injected. Reload tabs to activate.")
        return 0 if imported > 0 else 1
    finally:
        ws.close()


def list_export(in_path: Path) -> int:
    """Show what's in an export file."""
    data = json.loads(in_path.read_text(encoding="utf-8-sig"))
    print(f"Export from: {data.get('exported_at', 'unknown')}")
    print(f"Source ports: {data.get('source_ports', [])}")
    print(f"Total: {data.get('total_cookies', 0)} cookies, {data.get('total_domains', 0)} domains")
    print("\nDomains:")
    for dom in sorted(data.get("cookies_by_domain", {}).keys()):
        cnt = len(data["cookies_by_domain"][dom])
        print(f"  {dom:40s} {cnt:4d} cookies")
    return 0


def main():
    p = argparse.ArgumentParser(description="Export/import provider sessions via CDP")
    p.add_argument("--export", action="store_true", help="Export cookies from live Chrome")
    p.add_argument("--import", dest="do_import", action="store_true", help="Import cookies into Chrome")
    p.add_argument("--list", action="store_true", help="List contents of an export file")
    p.add_argument("--ports", default=",".join(map(str, DEFAULT_PORTS)),
                   help="CDP ports to export from (comma-separated)")
    p.add_argument("--port", type=int, default=9222, help="CDP port to import into")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Export output path")
    p.add_argument("--in", dest="in_path", type=Path, default=DEFAULT_OUT, help="Import input path")
    p.add_argument("--domains", default=None, help="Comma-separated domain filter for import")
    args = p.parse_args()

    if args.export:
        ports = [int(x) for x in args.ports.split(",")]
        return export_cookies(ports, args.out)
    elif args.do_import:
        domains = args.domains.split(",") if args.domains else None
        return import_cookies(args.port, args.in_path, domains)
    elif args.list:
        return list_export(args.in_path)
    else:
        p.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
