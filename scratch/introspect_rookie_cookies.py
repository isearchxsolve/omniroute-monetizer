"""Introspect rookie_cookies API (no cookie extraction, T11-safe)."""
import rookie_cookies
print("module:", rookie_cookies.__file__)
print("has chrome:", hasattr(rookie_cookies, "chrome"))
import inspect
try:
    print("chrome doc:", (rookie_cookies.chrome.__doc__ or "")[:400])
except Exception as e:
    print("doc err:", e)
print("dir:", [x for x in dir(rookie_cookies) if not x.startswith("_")])
