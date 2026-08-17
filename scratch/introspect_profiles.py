"""Introspect rookie_cookies profile APIs (no extraction, T11-safe)."""
import rookie_cookies, inspect

for name in ("chrome_profiles", "chrome_profile", "browser_profiles",
             "ProfileDescriptor", "chrome", "chromium_based_detailed"):
    obj = getattr(rookie_cookies, name, None)
    if obj is None:
        print(f"{name}: MISSING")
        continue
    print(f"--- {name} ---")
    try:
        print("  sig:", str(inspect.signature(obj)))
    except Exception as e:
        print("  sig err:", e)
    doc = (getattr(obj, "__doc__", "") or "")[:500]
    print("  doc:", doc.replace("\n", "\n       "))
