# -*- coding: utf-8 -*-
"""Debug: test kw/aggregated against saved groq body."""
import json
import re

EXPECT = "the holy cow jumps over the stricks"
t = open(r"d:\omniroute-monetizer\state\groq_last_body.txt", encoding="utf-8").read()


def kw(text):
    flat = re.sub(r"[^a-z ]", " ", text.lower())
    flat = re.sub(r"\s+", " ", flat).strip()
    return EXPECT.lower() in flat


def aggregated(text):
    parts = re.findall(r'"(?:text|value|content|message|delta|answer|reply)"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.I)
    out = []
    for p in parts:
        try:
            out.append(json.loads('"' + p + '"'))
        except Exception:
            out.append(p)
    return " ".join(out)


print("kw(raw)=", kw(t))
agg = aggregated(t)
print("agg_len=", len(agg))
print("kw(agg)=", kw(agg))
print("agg sample=", repr(agg[:300]))
