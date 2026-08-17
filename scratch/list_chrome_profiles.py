"""List Chrome profiles via rookie-cookies (names/paths only, T11-safe, no elevation)."""
import rookie_cookies as rc

try:
    profs = rc.chrome_profiles()
except Exception as e:
    print("chrome_profiles FAILED:", type(e).__name__, str(e)[:300])
    raise SystemExit(1)

print(f"{len(profs)} profiles discovered")
for p in profs:
    prof = p.get("profile", {})
    print("-" * 60)
    print("  profile_id   :", prof.get("profile_id"))
    print("  display_name :", prof.get("display_name"))
    print("  path         :", prof.get("path"))
    print("  path_lossy   :", prof.get("path_lossy"))
    print("  is_default   :", p.get("is_default"))
    for s in p.get("sources", []):
        print("    source role=%s format=%s path=%s" % (
            s.get("role"), s.get("format"), s.get("path")))
