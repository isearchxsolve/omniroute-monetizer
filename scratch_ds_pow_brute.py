"""Brute-force the DeepSeekHashV1 acceptance condition.

The signature is almost certainly server-side (signs the challenge). The client
finds `answer`. So the condition is: some hash f(challenge, salt, answer) must be
'easy'. We find f by requiring answer=19995 to be SPECIAL (more leading zeros, or
lower int value) than its immediate neighbors 19994 and 19996.
"""
import hashlib, hmac, itertools

chal = "9d212ef66d3829112d020cca6351735b77c03d3a5aa0b28ea21df236d86aa7e7"
salt = "71e7d0ac834b61564436"
ANS = 19995

def sha(b):
    if isinstance(b, str): b = b.encode()
    return hashlib.sha256(b).digest()

def hexd(b): return b.hex()

def lead_zero_bits(hbytes):
    n = 0
    for byte in hbytes:
        if byte == 0: n += 8; continue
        # count leading zeros in this byte
        for i in range(7, -1, -1):
            if byte & (1 << i): return n
            n += 1
        return n
    return n

def lead_zero_nybbles(hx):
    n = 0
    for c in hx:
        if c == '0': n += 1
        else: break
    return n

# Build candidate formulations as functions of answer
def formulations(ans):
    a = str(ans)
    ab = ans.to_bytes(8, 'big')
    ab4 = ans.to_bytes(4, 'big')
    out = {}
    out["sha(c+s+a)"]        = sha(chal + salt + a)
    out["sha(a+c+s)"]        = sha(a + chal + salt)
    out["sha(c+a+s)"]        = sha(chal + a + salt)
    out["sha(s+c+a)"]        = sha(salt + chal + a)
    out["sha(s+a+c)"]        = sha(salt + a + chal)
    out["sha(a+s+c)"]        = sha(a + salt + chal)
    out["sha(c+s+ab8)"]      = sha((chal+salt).encode() + ab)
    out["sha(c+s+ab4)"]      = sha((chal+salt).encode() + ab4)
    out["sha(ab8+c+s)"]      = sha(ab + (chal+salt).encode())
    out["sha(sha(c+s)+a)"]   = sha(sha(chal+salt) + a.encode())
    out["sha(a+sha(c+s))"]   = sha(a.encode() + sha(chal+salt))
    out["sha(sha(c)+s+a)"]   = sha(sha(chal) + salt.encode() + a.encode())
    out["sha(c+sha(s)+a)"]   = sha(chal.encode() + sha(salt) + a.encode())
    out["sha(sha(c+s)+ab8)"] = sha(sha(chal+salt) + ab)
    out["sha(c|s|a colon)"]  = sha(f"{chal}|{salt}|{a}")
    out["sha(c:s:a)"]        = sha(f"{chal}:{salt}:{a}")
    out["sha(c-s-a)"]        = sha(f"{chal}-{salt}-{a}")
    out["sha(csa nosp)"]     = sha(f"{chal}{salt}{a}")
    out["hmac(c, s+a)"]      = hmac.new(chal.encode(), (salt+a).encode(), hashlib.sha256).digest()
    out["hmac(s, c+a)"]      = hmac.new(salt.encode(), (chal+a).encode(), hashlib.sha256).digest()
    out["hmac(c+s, a)"]      = hmac.new((chal+salt).encode(), a.encode(), hashlib.sha256).digest()
    out["sha(sha(a)+c+s)"]   = sha(sha(a) + (chal+salt).encode())
    out["sha(c+sha(a)+s)"]   = sha(chal.encode() + sha(a) + salt.encode())
    # double sha
    out["sha2(sha(c+s+a))"]  = sha(sha(chal+salt+a))
    return out

print("Testing which formulation makes answer=19995 special vs 19994/19996...\n")
names = list(formulations(ANS).keys())
found = []
for name in names:
    h_ans  = formulations(ANS)[name]
    h_prev = formulations(ANS-1)[name]
    h_next = formulations(ANS+1)[name]
    z_ans  = lead_zero_bits(h_ans)
    z_prev = lead_zero_bits(h_prev)
    z_next = lead_zero_bits(h_next)
    # special if more leading zero bits than both neighbors
    if z_ans > z_prev and z_ans > z_next and z_ans >= 8:
        found.append((name, z_ans, z_prev, z_next, hexd(h_ans)))
        print(f"  CANDIDATE {name}: bits(ans)={z_ans} prev={z_prev} next={z_next}  {hexd(h_ans)[:24]}")

if not found:
    print("  no leading-zero-bit candidate found; trying int-value minimality over a window...")
    # maybe answer is the MINIMUM hash over a search window
    for name in names:
        vals = {a: int.from_bytes(formulations(a)[name], 'big') for a in range(ANS-50, ANS+51)}
        amin = min(vals, key=vals.get)
        if amin == ANS:
            print(f"  CANDIDATE(min over +-50) {name}: answer {ANS} is the minimum-hash nonce")
            found.append((name, None, None, None, None))

if not found:
    print("\n  No formulation found. Dumping leading-zero-bit profile for all at answer=19995:")
    for name in names:
        print(f"    {name:22s} bits={lead_zero_bits(formulations(ANS)[name]):2d}  {hexd(formulations(ANS)[name])[:20]}")
