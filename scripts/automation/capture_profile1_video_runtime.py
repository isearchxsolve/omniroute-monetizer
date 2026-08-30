"""Record a non-spending snapshot of profile-1 video routes from :8189."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "state" / "profile1_video_runtime.json"
PROFILE1 = {"flow", "rtst", "digen"}


def main() -> int:
    with urllib.request.urlopen("http://127.0.0.1:8189/v1/models", timeout=20) as response:
        payload = json.load(response)
    rows = [
        {
            k: item.get(k)
            for k in ("id", "model", "provider", "title", "proven", "note", "est_cost", "quotes_before_spending")
        }
        for item in payload.get("data", [])
        if item.get("provider") in PROFILE1
    ]
    output = {
        "source": "http://127.0.0.1:8189/v1/models",
        "httpStatus": 200,
        "total": len(rows),
        "providers": {p: sum(x["provider"] == p for x in rows) for p in sorted(PROFILE1)},
        "models": rows,
    }
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"total": output["total"], "providers": output["providers"], "output": str(OUT)}, indent=2))
    assert output["total"] == 21
    assert output["providers"] == {"digen": 2, "flow": 12, "rtst": 7}
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
