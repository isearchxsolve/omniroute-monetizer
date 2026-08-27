import re
raw = 'r_437d0b74e309db58 and ["58"] and 1787806985 and x58y and " 58." and is 58\n'
pat = r"(?<![0-9A-Za-z])58(?![0-9A-Za-z])"
for m in re.finditer(pat, raw):
    s, e = max(0, m.start()-8), min(len(raw), m.end()+8)
    print("MATCH:", repr(raw[s:e]))
print("total matches:", len(re.findall(pat, raw)))
