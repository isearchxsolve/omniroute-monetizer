"""Suppress the remaining broken-but-active connections stalling [CredentialHealth].

Evidence-first: test each suspect connection via POST /api/providers/{id}/test,
print the diagnosis, and set isActive=false ONLY on confirmed failures.
"""
import requests

BASE_URL = "http://localhost:20128"
PASSWORD = "Keross@321"

# (id-prefix, provider, identity) — the 6 broken connections still active
SUSPECTS = [
    ("811ba58f", "ainative", "main"),
    ("c0338023", "agy", "isearch.xsolve@gmail.com"),
    ("5b6bb68a", "antigravity", "isearch.xsolve@gmail.com"),
    ("e00b5169", "antigravity", "kunal.colab@gmail.com"),
    ("a6e1728a", "grok-cli", "kunal_nit@yahoo.co.in"),
    ("54efdf9f", "lmarena", "main"),
]


def main() -> None:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=10)
    r.raise_for_status()

    conns = s.get(f"{BASE_URL}/api/providers", timeout=60).json()["connections"]
    by_prefix = {c["id"][:8]: c for c in conns}

    suppressed = 0
    for prefix, provider, identity in SUSPECTS:
        conn = by_prefix.get(prefix)
        if not conn:
            print(f"[?] {provider}/{identity}: connection {prefix} not found")
            continue
        cid = conn["id"]
        if not conn.get("isActive"):
            print(f"[=] {provider}/{identity}: already inactive, skip")
            continue

        # Test it
        try:
            t = s.post(f"{BASE_URL}/api/providers/{cid}/test", timeout=30).json()
        except Exception as e:
            print(f"[!] {provider}/{identity}: test errored: {e}")
            t = {}
        result = t.get("result", {})
        valid = result.get("valid")
        msg = (result.get("error") or result.get("message") or "")[:80]
        print(f"[*] {provider}/{identity}: valid={valid} msg={msg!r}")

        if valid:
            print(f"    -> healthy, leaving active")
            continue

        # Confirmed broken -> suppress
        try:
            pr = s.put(f"{BASE_URL}/api/providers/{cid}", json={"isActive": False}, timeout=15)
            ok = pr.status_code in (200, 204)
            print(f"    -> SUPPRESSED (isActive=false) status={pr.status_code}")
            if ok:
                suppressed += 1
        except Exception as e:
            print(f"    -> suppress FAILED: {e}")

    # Final count
    conns2 = s.get(f"{BASE_URL}/api/providers", timeout=60).json()["connections"]
    act = sum(1 for c in conns2 if c.get("isActive"))
    print(f"\n[+] Done. Suppressed {suppressed}. Active now: {act}/{len(conns2)}")


if __name__ == "__main__":
    main()
