"""Verify the runtime:replay graduation lever dispatches correctly.
Zero cost: builds raw dicts, calls _client_for, never touches a provider."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from session_pool import _client_for

EX = {"url": "https://x/api", "method": "POST", "request_headers": {}, "request_body": "{}"}

cases = [
    # (name, raw, expected_class_name)
    ("graduated chat", {"host": "chat.deepseek.com", "chrome": True,
                        "recorded_exchange": EX, "runtime": "replay"},
     "UniversalSessionClient"),
    ("graduated video (modality)", {"host": "labs.google", "modality": "video",
                                    "recorded_exchange": EX, "runtime": "replay"},
     "VideoUniversalSessionClient"),
    ("graduated video (job only)", {"host": "digen.ai", "modality": "video",
                                    "recorded_job": {"submit": {}}, "runtime": "replay"},
     "VideoUniversalSessionClient"),
    ("NOT graduated chat -> Chrome", {"host": "chat.deepseek.com", "chrome": True,
                                      "recorded_exchange": EX},
     "ChromeReplayClient"),
    ("NOT graduated video -> Chrome", {"host": "labs.google", "modality": "video",
                                       "recorded_exchange": EX},
     "ChromeVideoClient"),
    ("runtime:replay but NO blueprint -> falls to Chrome", {"host": "chat.deepseek.com",
                                                            "chrome": True, "runtime": "replay"},
     "ChromeReplayClient"),
    ("api kind rtst wins over everything", {"host": "rtst.ai", "api": {"kind": "rtst"},
                                            "recorded_exchange": EX, "runtime": "replay"},
     "RtstApiClient"),
]

ok = True
for name, raw, want in cases:
    cls = _client_for(raw.get("host"), raw)
    got = cls.__name__ if cls else "None"
    mark = "PASS" if got == want else "FAIL"
    if got != want:
        ok = False
    print(f"[{mark}] {name:42} -> {got} (want {want})")

print()
print("ALL PASS" if ok else "FAILURES PRESENT")
