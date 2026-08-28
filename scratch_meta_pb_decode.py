"""P2: (a) grab auth cookies for gateway.meta.ai / www.meta.ai (the ws handshake rides these),
(b) structured protobuf field-by-field decode of the saved sent frame to identify per-message
fields and judge surgical-replay tractability. Read-only.
"""
import io, json, sys, time, pathlib, base64, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from capture_sessions_cdp import CDP, targets

tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
t = tabs[0]
c = CDP(t["webSocketDebuggerUrl"])
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(0.8)
    jar = c.call("Network.getCookies", {"urls": ["https://www.meta.ai/", "https://gateway.meta.ai/", "wss://gateway.meta.ai/ws"]}).get("cookies", [])
    print("cookies for meta.ai + gateway: %d" % len(jar))
    names = sorted(k["name"] for k in jar)
    print("cookie NAMES (no values):", names)
    # flag the auth-relevant ones
    authish = [n for n in names if any(x in n.lower() for x in ("datr","sb","c_user","xs","fr","ps_l","ps_n","wd","session","token","auth"))]
    print("auth-ish names:", authish)
finally:
    c.close()

# ---- structured protobuf decode of saved sent frame ----
prev = json.loads(pathlib.Path("state/meta_ws_frames.json").read_text(encoding="utf-8"))
frame_b64 = prev["sent"][0]
raw = base64.b64decode(frame_b64)
print("\n=== outer envelope: %d bytes ===" % len(raw))
print("outer hex head(16):", raw[:16].hex())
txt = raw.decode("utf-8","replace")
i = txt.find("{")
depth=0
for j in range(i,len(txt)):
    if txt[j]=="{": depth+=1
    elif txt[j]=="}":
        depth-=1
        if depth==0: break
env = json.loads(txt[i:j+1])
print("envelope keys:", sorted(env.keys()))
print("envelope req-id:", env.get("req-id"))
print("bytes BEFORE json (binary header):", raw[:i].hex())
print("bytes AFTER json (trailer):", raw[j+1:].hex() if j+1 < len(raw) else "(none)")

inner = base64.b64decode(env["payload"])
print("\n=== inner protobuf: %d bytes ===" % len(inner))

# minimal protobuf wire-format walker
def read_varint(b, pos):
    result=0; shift=0
    while True:
        byte=b[pos]; pos+=1
        result |= (byte & 0x7f) << shift
        if not (byte & 0x80): break
        shift+=7
    return result, pos

def walk(b, indent=0, limit=200):
    pos=0; count=0
    pad="  "*indent
    while pos < len(b) and count<limit:
        try:
            key, pos = read_varint(b, pos)
        except Exception:
            print(pad+"[stop: bad varint at %d]"%pos); break
        field = key >> 3; wt = key & 7
        if wt==0:
            v, pos = read_varint(b, pos)
            print(pad+"field %d varint = %d"%(field,v))
        elif wt==2:
            ln, pos = read_varint(b, pos)
            chunk = b[pos:pos+ln]; pos+=ln
            s = chunk.decode("utf-8","replace")
            printable = all(32<=ord(ch)<127 or ch in "\n\t" for ch in s) and len(s)>0
            if printable and ln>0:
                print(pad+"field %d len=%d str = %r"%(field,ln,s[:90]))
            else:
                print(pad+"field %d len=%d bytes = %s"%(field,ln,chunk[:24].hex()))
                # try nested
                if ln>2 and ln<400:
                    try: walk(chunk, indent+1, limit=30)
                    except Exception: pass
        elif wt==1:
            print(pad+"field %d fixed64 = %s"%(field,b[pos:pos+8].hex())); pos+=8
        elif wt==5:
            print(pad+"field %d fixed32 = %s"%(field,b[pos:pos+4].hex())); pos+=4
        else:
            print(pad+"[unknown wiretype %d at field %d]"%(wt,field)); break
        count+=1

walk(inner)
