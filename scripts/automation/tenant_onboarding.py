"""Tenant onboarding for the :8190 consumer gateway (worklog #1110 gate, #1618).

Creating ``state/secrets/tenant_map.json`` switches the shim's Bearer-key
multi-tenancy ON instantly (the map is re-read per request; no restart).
Presence of the file means every consumer path requires
``Authorization: Bearer <api_key>`` while ``/healthz`` stays open for the
scheduled owner chain.

Secrets discipline (T11 / Law 5): full keys are written ONLY to gitignored
``state/secrets/``; stdout shows tenant names and 12-char key prefixes at most.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP = ROOT / "state" / "secrets" / "tenant_map.json"
DEFAULT_OUT = ROOT / "state" / "secrets"
SHIM = "http://127.0.0.1:8190"
KEY_PREFIX = "sk-omni-"


def _no_proxy() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(24)


def load_map(path: Path) -> dict[str, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}


def write_map_atomic(path: Path, mapping: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(mapping, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def redact(key: str) -> str:
    return key[:12] + "..."


def _status(method: str, url: str, key: str | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url, method=method)
    if key:
        request.add_header("Authorization", f"Bearer {key}")
    try:
        with _no_proxy().open(request, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def verify_gate(one_key: str, expected_tenant: str) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    status, _ = _status("GET", f"{SHIM}/healthz")
    checks.append(("healthz_open_without_key", status == 200, f"HTTP {status}"))
    status, _ = _status("GET", f"{SHIM}/v1/models")
    checks.append(("models_401_without_key", status == 401, f"HTTP {status}"))
    status, _ = _status("GET", f"{SHIM}/v1/models", key=KEY_PREFIX + "bogus-not-a-key")
    checks.append(("models_401_bad_key", status == 401, f"HTTP {status}"))
    status, _ = _status("GET", f"{SHIM}/v1/models", key=one_key)
    checks.append(("models_200_valid_key", status == 200, f"HTTP {status}"))
    # Tenant tagging shows on request-scoped responses (chat/job receipts and
    # 400 error echoes), not on the static models list. A malformed chat POST
    # is free and deterministic: 400 + {"tenant": <name>}.
    bad = json.dumps({"model": "session-pool/auto"}).encode()
    request = urllib.request.Request(
        SHIM + "/v1/chat/completions", data=bad,
        headers={"Content-Type": "application/json"})
    request.add_header("Authorization", f"Bearer {one_key}")
    try:
        with _no_proxy().open(request, timeout=20) as resp:
            status, body = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status, body = exc.code, exc.read().decode("utf-8", "replace")
    tagged = expected_tenant in body
    checks.append(("chat_400_valid_key_tenant_tagged", status == 400 and tagged,
                   f"HTTP {status} tenant_tagged={tagged}"))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10,
                        help="number of wave-1 tenant keys to create")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verify-only", action="store_true",
                        help="re-run gate verification against the existing map")
    args = parser.parse_args()

    mapping = load_map(args.map)
    if args.verify_only:
        if not mapping:
            print("tenant_map absent; gate open (single-operator mode)")
            return 1
        any_key = next(iter(mapping))
        for name, ok, detail in verify_gate(any_key, mapping[any_key]):
            print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
        return 0 if all(ok for _, ok, _ in verify_gate(next(iter(mapping)), mapping[next(iter(mapping))])) else 1

    if not 1 <= args.count <= 500:
        raise SystemExit("--count must be between 1 and 500")

    created: dict[str, str] = {}
    wave = len(mapping) + 1
    for i in range(wave, wave + args.count):
        tenant = f"tenant_{i:03d}"
        key = generate_key()
        mapping[key] = tenant
        created[tenant] = key

    write_map_atomic(args.map, mapping)

    stamp = time.strftime("%Y%m%dT%H%M%S")
    out = args.out_dir / f"tenant_keys_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"wave": wave, "created": created}, indent=1) + "\n",
                   encoding="utf-8")

    print(f"tenants_total={len(mapping)} created={len(created)} map={args.map.name}")
    print(f"full_keys_written_to={out.name} (gitignored; distribute from there)")
    for tenant, key in created.items():
        print(f"{tenant} {redact(key)}")

    one_tenant, one_key = next(iter(created.items()))
    failures = 0
    for name, ok, detail in verify_gate(one_key, one_tenant):
        print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
        failures += 0 if ok else 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
