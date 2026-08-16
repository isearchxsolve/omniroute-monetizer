#!/usr/bin/env python3
"""Read Gemini API key from the Windows clipboard (user copied it manually).

Human-in-the-loop handoff: user clicked copy in AI Studio; we grab the
clipboard value, validate the AIza pattern, mask for display, and persist
ONLY to state/generated_keys.json (gitignored). T11-safe: never prints the
full key."""
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_FILE = os.path.join(ROOT, "state", "generated_keys.json")
# Classic format AIza... (39 chars) OR newer Google key formats (e.g. AQ....)
KEY_RX = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
KEY_RX_NEW = re.compile(r"^[A-Z]{2}\.[0-9A-Za-z_\-]{20,}$")


def read_clipboard() -> str:
    """Read clipboard via PowerShell (handles Chromium-owned clipboards that
    ctypes CF_UNICODETEXT sometimes misses)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, text=True, timeout=15,
        )
        return (out.stdout or "").strip()
    except Exception as e:
        raise RuntimeError(f"clipboard read failed: {e}")


def mask(k):
    return k[:8] + "..." + k[-4:] if k and len(k) > 14 else "<short>"


def main():
    text = read_clipboard().strip()
    if not text:
        print("[-] clipboard empty")
        return 1
    # Accept classic AIza... OR new Google format (two uppercase letters + dot + token)
    m = KEY_RX.search(text)
    if m:
        key = m.group(0)
        fmt = "classic_AIza"
    elif KEY_RX_NEW.match(text):
        key = text
        fmt = "new_google_format"
    else:
        print(f"[-] clipboard has no Gemini key pattern (len={len(text)}, starts={text[:12]!r})")
        return 2
    print(f"[+] clipboard contains gemini key [{fmt}]: {mask(key)} (len={len(key)})")

    data = {}
    if os.path.exists(KEYS_FILE):
        try:
            data = json.load(open(KEYS_FILE, encoding="utf-8"))
        except Exception:
            data = {}
    entry = data.get("gemini", {})
    keys = entry.get("keys", [])
    if key not in keys:
        keys.append(key)
    data["gemini"] = {
        "keys": keys,
        "key": key,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "clipboard_human_handoff",
    }
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[+] saved to state/generated_keys.json (total gemini keys: {len(keys)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
