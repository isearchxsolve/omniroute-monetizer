"""Reverse-engineer DeepSeekHashV1 by testing hash hypotheses against the known
challenge/salt/answer/signature tuple from the recorded x-ds-pow-response."""
import base64, hashlib, hmac, itertools, json

pow_b64 = "eyJhbGdvcml0aG0iOiJEZWVwU2Vla0hhc2hWMSIsImNoYWxsZW5nZSI6IjlkMjEyZWY2NmQzODI5MTEyZDAyMGNjYTYzNTE3MzViNzdjMDNkM2E1YWEwYjI4ZWEyMWRmMjM2ZDg2YWE3ZTciLCJzYWx0IjoiNzFlN2QwYWM4MzRiNjE1NjQ0MzYiLCJhbnN3ZXIiOjE5OTk1LCJzaWduYXR1cmUiOiJlOTg3MzQwNWQzZjBkYTdlMTI5ZjY5ZWM1ODU3ZDE0N2IzMTVmZTkyN2NmNDU0OWIzOGJmNjFmMTYzZDNlYWJiIiwidGFyZ2V0X3BhdGgiOiIvYXBpL3YwL2NoYXQvY29tcGxldGlvbiJ9"
d = json.loads(base64.b64decode(pow_b64))
chal = d["challenge"]; salt = d["salt"]; ans = d["answer"]; sig = d["signature"]
print("challenge:", chal)
print("salt:     ", salt)
print("answer:   ", ans)
print("signature:", sig)
print()

def h(s):
    if isinstance(s, str): s = s.encode()
    return hashlib.sha256(s).hexdigest()

# ---- Hypothesis A: what does the SIGNATURE commit to? ----
print("=== signature hypotheses ===")
cands = {
    "sha256(chal+salt+ans)":        h(chal + salt + str(ans)),
    "sha256(ans+chal+salt)":        h(str(ans) + chal + salt),
    "sha256(chal+ans+salt)":        h(chal + str(ans) + salt),
    "sha256(salt+chal+ans)":        h(salt + chal + str(ans)),
    "sha256(chal+salt)+ans":        h(h(chal + salt) + str(ans)),
    "sha256(ans+sha256(chal+salt))":h(str(ans) + h(chal + salt)),
    "sha256(sha256(chal)+salt+ans)":h(h(chal) + salt + str(ans)),
    "sha256(chal+salt+ans bytes)":  hashlib.sha256((chal+salt).encode()+ans.to_bytes(8,'big')).hexdigest(),
}
for name, v in cands.items():
    mark = "  <== MATCH" if v == sig else ""
    print(f"  {name:34s} {v[:16]}...{mark}")

# ---- Hypothesis B: what is the PoW ACCEPTANCE condition? ----
# The answer 19995 should make some hash 'easy' (leading zeros / below target).
print("\n=== PoW condition hypotheses (does answer=19995 produce an 'easy' hash?) ===")
def leading_zeros_hex(hs):
    n = 0
    for c in hs:
        if c == '0': n += 1
        else: break
    return n

cond_cands = {
    "sha256(chal+salt+ans)":        h(chal + salt + str(ans)),
    "sha256(ans+salt+chal)":        h(str(ans) + salt + chal),
    "sha256(chal+ans+salt)":        h(chal + str(ans) + salt),
    "sha256(salt+ans+chal)":        h(salt + str(ans) + chal),
    "sha256(h(chal+salt)+ans)":     h(h(chal + salt) + str(ans)),
    "sha256(ans+h(chal+salt))":     h(str(ans) + h(chal + salt)),
}
for name, v in cond_cands.items():
    print(f"  {name:28s} zeros={leading_zeros_hex(v)}  {v[:24]}...")

# Also: maybe the condition is on int value < target, or specific prefix == challenge prefix
print("\n=== does any candidate hash relate to the challenge string? ===")
for name, v in cond_cands.items():
    if v.startswith(chal[:4]) or chal.startswith(v[:4]):
        print(f"  {name}: shares 4-hex prefix with challenge")
