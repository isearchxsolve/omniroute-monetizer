#!/usr/bin/env python3
"""Human-assist flag system for the autonomous signup pipeline.

When automation hits a wall it cannot pass (CAPTCHA, OTP, bot-detection 403,
payment wall, step-up auth), it raises a flag describing exactly what a human
must do, then pauses. The human completes the step in the real browser window
(plain Chrome is visible on screen), clears the flag, and automation resumes.

Flag file: state/human_assist_flags.json (gitignored)

CLI:
  python human_assist.py list                 show pending flags
  python human_assist.py clear <provider>     mark a flag resolved
  python human_assist.py clear --all          resolve everything
"""
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FLAG_FILE = os.path.join(ROOT, "state", "human_assist_flags.json")


def _load():
    if os.path.exists(FLAG_FILE):
        try:
            return json.load(open(FLAG_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(data):
    os.makedirs(os.path.dirname(FLAG_FILE), exist_ok=True)
    with open(FLAG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def raise_flag(provider: str, url: str, reason: str, action_needed: str) -> None:
    """Record a human-assist request and print a loud banner."""
    data = _load()
    data[provider] = {
        "url": url,
        "reason": reason,
        "action_needed": action_needed,
        "raised_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "PENDING",
    }
    _save(data)
    bar = "=" * 72
    print(f"\n{bar}\n🚩 HUMAN ASSIST REQUIRED: {provider}\n{bar}")
    print(f"  URL:    {url}")
    print(f"  WHY:    {reason}")
    print(f"  DO:     {action_needed}")
    print(f"  THEN:   python scripts/automation/human_assist.py clear {provider}")
    print(f"{bar}\n")


def clear_flag(provider: str) -> None:
    data = _load()
    if provider in data:
        data[provider]["status"] = "RESOLVED"
        data[provider]["resolved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save(data)
        print(f"[+] flag cleared: {provider}")
    else:
        print(f"[-] no flag for {provider}")


def is_pending(provider: str) -> bool:
    data = _load()
    return data.get(provider, {}).get("status") == "PENDING"


def wait_for_clear(provider: str, timeout_sec: int = 600, poll_sec: int = 3) -> bool:
    """Block until the human clears the flag. Returns True if cleared."""
    deadline = time.time() + timeout_sec
    print(f"[*] waiting for human assist on '{provider}' (timeout {timeout_sec}s) ...")
    while time.time() < deadline:
        if not is_pending(provider):
            print(f"[+] human assist resolved for '{provider}'")
            return True
        time.sleep(poll_sec)
    print(f"[-] timed out waiting for human assist on '{provider}'")
    return False


def list_flags():
    data = _load()
    if not data:
        print("[*] no flags")
        return
    for prov, f in data.items():
        print(f"{prov:20s} {f.get('status'):10s} raised={f.get('raised_at')}")
        print(f"    url: {f.get('url')}")
        print(f"    do:  {f.get('action_needed')}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "list":
        list_flags()
    elif args[0] == "clear":
        if len(args) > 1 and args[1] == "--all":
            for p in list(_load().keys()):
                clear_flag(p)
        elif len(args) > 1:
            clear_flag(args[1])
        else:
            print("usage: human_assist.py clear <provider|--all>")
    else:
        print(__doc__)
