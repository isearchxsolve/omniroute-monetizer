import sys, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(r"d:\omniroute-monetizer\scripts\automation")))
import googleflow_client as gf

sess = gf.FlowSession(port=9222).refresh()
print(f"email       : {sess.email}")
print(f"project_id  : {sess.project_id}")
print(f"tier        : {sess.tier}")
st, ct = gf.request(gf.CREDITS_URL, sess.token, None, method="GET")
print(f"credits HTTP: {st}")
if st == 200:
    import json
    print(f"credits     : {json.loads(ct).get('credits')}")
else:
    print(f"body        : {ct[:200]}")
