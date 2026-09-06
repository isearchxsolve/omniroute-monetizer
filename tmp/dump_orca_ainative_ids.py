"""Read-only: dump native orcarouter/ainative/llm7 model ids from the serving chunk."""
import pathlib
import re

f = pathlib.Path(
    r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"
    r"\.build\next\server\chunks\open-sse_00r5dfh._.js")
src = f.read_text(encoding="utf-8", errors="replace")

for name in ["orcarouter", "ainative"]:
    i = src.find(f"{name}:{{id:")
    if i < 0:
        print(name, "-> no literal")
        continue
    j = src.find("{", i)
    depth = 0
    k = j
    while k < len(src):
        c = src[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    lit = src[j:k + 1]
    ids = re.findall(r'\{id:"([^"]+)"', lit)
    print(f"{name}: {len(ids)} native models")
    for mid in ids:
        print(f"  {mid}")
    print()
