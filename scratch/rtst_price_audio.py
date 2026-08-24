"""The audio=True half of the grid. Free: GET /video/estimate-credits only."""
from __future__ import annotations
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts" / "automation"))
import rtst_client as rt          # noqa: E402
import video_provider as vp       # noqa: E402
import video_provider_rtst as vpr # noqa: E402

P, A = vp.get("rtst"), vp.Account("rtst", 9222, "rtst-1")
P.probe(A); assert A.ready, A.reason
print(f"balance {A.credits}")
print(f"{'model':<14} {'cat_cps':>7} {'qual':>5} {'audio_rate':>10} {'mute_rate':>9} "
      f"{'exact?':>7}")
with rt.Rtst(A.port) as c:
    for name, m in P.catalogue.items():
        if not m.get("is_audio_supported"):
            print(f"{name:<14} {'-':>7} {'':>5} {'no audio support':>10}"); continue
        durs, quals = P._allowed(name)
        for q in quals:
            got = {}
            for audio in (True, False):
                try:
                    got[audio] = c.quote(model=name, duration=durs[0], resolution=str(q),
                                         aspect="16:9", audio=audio)
                except Exception as e:                                     # noqa: BLE001
                    got[audio] = {"err": f"{type(e).__name__}: {str(e)[:50]}"}
            ar, mr = got[True].get("credits_per_second"), got[False].get("credits_per_second")
            ok = all(isinstance(g.get("credits_required"), int)
                     and isinstance(g.get("credits_per_second"), int)
                     and g["credits_required"] == g["credits_per_second"] * durs[0]
                     for g in got.values())
            print(f"{name:<14} {m.get('credits_per_second'):>7} {q:>5} {str(ar):>10} {str(mr):>9} "
                  f"{str(ok):>7}   d={durs[0]} {got[True].get('err','')}{got[False].get('err','')}")
print(f"balance after {A.credits} (quotes are free)")
