#!/usr/bin/env python3
"""
End-to-end verification of the exact code path PyGPT uses for the TokenRouter
routes: open_router.llama() -> llama_index OpenAILike(**args) -> chat().

Uses key #1 (all 7 keys already verified live via direct HTTP earlier).
Secrets redacted in output.
"""
import json
import os
import time
from pathlib import Path

WORKDIR = os.path.join(Path.home(), ".config", "pygpt-net")
MODELS_JSON = os.path.join(WORKDIR, "models.json")


def redact(k):
    return k[:6] + "****" + k[-4:] if k and len(k) > 12 else "****"


def main():
    with open(MODELS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    entry = data["items"]["tokenrouter-qwen38max-key2"]
    args = {}
    for opt in entry["llama_index"]["args"]:
        args[opt["name"]] = opt["value"]

    print("provider:", entry["provider"])
    print("model:", args.get("model"))
    print("api_base:", args.get("api_base"))
    print("api_key:", redact(args.get("api_key")))

    # Replicate open_router.llama(): OpenAILike(**args) with is_chat_model=True
    from llama_index.llms.openai_like import OpenAILike
    llm = OpenAILike(
        model=args["model"],
        api_key=args["api_key"],
        api_base=args["api_base"],
        is_chat_model=True,
        is_function_calling_model=bool(entry.get("tool_calls", False)),
        timeout=60,
        max_retries=2,
    )

    from llama_index.core.llms import ChatMessage
    t0 = time.time()
    resp = llm.chat([ChatMessage(role="user", content="Reply with exactly: OK")])
    dt = time.time() - t0
    text = resp.message.content
    print("chat() -> {!r} in {:.2f}s".format(text, dt))
    print("RESULT:", "PASS" if text else "FAIL")
    return 0 if text else 1


if __name__ == "__main__":
    raise SystemExit(main())
