#!/usr/bin/env python3
"""Debug: inspect what OpenAILike actually sends (base_url, headers)."""
import json
import os
from pathlib import Path

WORKDIR = os.path.join(Path.home(), ".config", "pygpt-net")
MODELS_JSON = os.path.join(WORKDIR, "models.json")


def redact(k):
    return k[:6] + "****" + k[-4:] if k and len(k) > 12 else "****"


with open(MODELS_JSON, "r", encoding="utf-8") as f:
    data = json.load(f)
entry = data["items"]["tokenrouter-qwen38max-key1"]
args = {}
for opt in entry["llama_index"]["args"]:
    args[opt["name"]] = opt["value"]

from llama_index.llms.openai_like import OpenAILike

llm = OpenAILike(
    model=args["model"],
    api_key=args["api_key"],
    api_base=args["api_base"],
    is_chat_model=True,
    timeout=60,
    max_retries=1,
)

print("llm.api_base =", llm.api_base)
print("llm.api_key  =", redact(llm.api_key or ""))
print("llm.model    =", llm.model)

client = llm._get_client()
print("client.base_url =", client.base_url)
req = client._build_request(
    client._FinalRequestOptions(
        method="post",
        url="/chat/completions",
        json_data={"model": args["model"], "messages": [{"role": "user", "content": "hi"}]},
    ),
)
print("request url:", req.url)
auth = req.headers.get("authorization", "")
print("authorization header:", auth[:12] + "****" if len(auth) > 12 else auth)
