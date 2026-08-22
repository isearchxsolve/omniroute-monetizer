"""Wire the upstream-verified Gemini key into OmniRoute's gemini connection.

Why this exists: state/generated_keys.json held three AQ.-prefixed Google AI Studio keys.
All three returned HTTP 200 against generativelanguage.googleapis.com/v1beta/models
(50 models each) on 2026-08-22, and gemini-flash-latest:generateContent replied "working".
So the key is proven upstream BEFORE being written anywhere -- Anti-pattern #7.

Keys are masked in every line this prints.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]


def mask(k: str) -> str:
    return f"{k[:5]}...{k[-4:]}" if len(k) > 12 else "<short>"


def main() -> int:
    keys = json.loads((ROOT / "state" / "generated_keys.json").read_text(encoding="utf-8"))
    gem = keys["gemini"]["key"]

    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        print("[-] OmniRoute login failed -- nothing changed")
        return 2

    conns = api.get_connections()
    print(f"[*] {len(conns)} connections")

    # Show every Google-family connection before touching anything.
    fam = [c for c in conns if any(t in str(c.get("provider", "")).lower()
                                   or t in str(c.get("name", "")).lower()
                                   for t in ("gemini", "vertex", "google"))]
    print("\nBEFORE:")
    for c in fam:
        print(f"  {str(c.get('provider','?')):14} id={c.get('id')} active={c.get('isActive')} "
              f"authType={c.get('authType')} testStatus={c.get('testStatus')} "
              f"hasKey={bool(c.get('apiKey'))}")

    target = next((c for c in conns if str(c.get("provider", "")).lower() == "gemini"), None)
    if target is None:
        print("\n[-] no connection with provider == 'gemini'; nothing changed")
        return 3

    cid = target.get("id")
    print(f"\n[*] writing verified key {mask(gem)} into gemini connection id={cid}")
    r = api.update_connection(cid, {"apiKey": gem, "isActive": True})
    print(f"[*] PUT -> HTTP {getattr(r, 'status_code', r)}")

    t = api.test_connection(cid)
    body = getattr(t, "text", str(t))[:300].replace("\n", " ")
    print(f"[*] TEST -> HTTP {getattr(t, 'status_code', '?')}  {body}")

    after = next((c for c in api.get_connections() if c.get("id") == cid), {})
    print(f"\nAFTER: active={after.get('isActive')} testStatus={after.get('testStatus')} "
          f"hasKey={bool(after.get('apiKey'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
