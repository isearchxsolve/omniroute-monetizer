import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts" / "automation"))

from universal_replay import UniversalSessionClient

SECRETS = HERE / "state" / "secrets"

for f in sorted(SECRETS.glob("session_*.json")):
    try:
        c = UniversalSessionClient(f)
        b = c.base_body or ""
        print(f"{f.name:45s} | body_len: {len(b):6d} | ", end="")
        found = []
        for phrase in [
            "Reply exactly one word: Omni.",
            "Reply exactly one word: Omni",
            "Reply exactly one word : Omni.",
            "Reply exactly one word : Omni",
            "Omni sentinel shot: a lone lighthouse beam sweeping across dark ocean waves at midnight",
            "Omni sentinel shot",
            "Omni.",
            "Omni",
            "Hi",
            "Hello",
        ]:
            if phrase in b:
                found.append(phrase)
        print("MATCHED:", found if found else "NONE!")
    except Exception as e:
        print(f"{f.name:45s} | ERROR: {e}")
