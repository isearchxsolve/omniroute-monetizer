#!/usr/bin/env python3
"""
Verify the PyGPT TokenRouter configuration using PyGPT's own code paths:
  1. models.json parses as valid JSON.
  2. Each of the 7 tokenrouter entries deserializes into a ModelItem via the
     real JsonFileProvider.deserialize().
  3. Each entry's llama_index.args resolves model/api_key/api_base (simulating
     open_router.llama() arg resolution).
  4. config.json holds the global open_router fallback key + endpoint.
Secrets are redacted in all output.
"""
import json
import os
from pathlib import Path

WORKDIR = os.path.join(Path.home(), ".config", "pygpt-net")
MODELS_JSON = os.path.join(WORKDIR, "models.json")
CONFIG_JSON = os.path.join(WORKDIR, "config.json")
BASE_URL = "https://api.tokenrouter.com/v1"
MODEL_ID = "qwen/qwen3.8-max-free"
EXPECTED = 7

from pygpt_net.item.model import ModelItem
from pygpt_net.provider.core.model.json_file import JsonFileProvider


def redact(k):
    return k[:6] + "****" + k[-4:] if k and len(k) > 12 else "****"


def parse_args(options):
    """Replicate BaseLLM.parse_args for the no-placeholder case."""
    args = {}
    if options is None:
        return args
    for opt in options.get("args", []):
        if isinstance(opt, dict):
            name = opt.get("name")
            value = opt.get("value")
            if name is not None:
                args[name] = value
    return args


def main():
    ok = True

    # 1. models.json valid JSON
    with open(MODELS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items", {})
    print("[1] models.json valid JSON, total items:", len(items))

    # 2+3. deserialize + resolve each tokenrouter entry
    provider = JsonFileProvider(window=None)
    routes = {k: v for k, v in items.items() if k.startswith("tokenrouter-")}
    print("[2] tokenrouter entries found:", len(routes))
    if len(routes) != EXPECTED:
        print("    FAIL: expected", EXPECTED)
        ok = False

    seen_keys = set()
    for i in range(1, EXPECTED + 1):
        mid = "tokenrouter-qwen38max-key{}".format(i)
        entry = items.get(mid)
        if entry is None:
            print("    FAIL: missing", mid)
            ok = False
            continue
        model = ModelItem()
        provider.deserialize(entry, model)
        args = parse_args(model.llama_index)
        m = args.get("model")
        k = args.get("api_key")
        b = args.get("api_base")
        prov = model.provider
        modes = model.mode
        good = (m == MODEL_ID and b == BASE_URL and prov == "open_router"
                and k and k.startswith("sk-") and "llama_index" in modes)
        seen_keys.add(k)
        print("    {} provider={} mode={} model={} api_base={} key={} -> {}".format(
            mid, prov, modes, m, b, redact(k), "OK" if good else "FAIL"))
        if not good:
            ok = False

    if len(seen_keys) == EXPECTED:
        print("[3] all {} keys distinct".format(EXPECTED))
    else:
        print("[3] FAIL: only {} distinct keys".format(len(seen_keys)))
        ok = False

    # 4. config.json global fallback
    with open(CONFIG_JSON, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    target = cfg.get("items", cfg) if isinstance(cfg, dict) else cfg
    gk = target.get("api_key_open_router", "")
    ge = target.get("api_endpoint_open_router", "")
    good_cfg = gk.startswith("sk-") and ge == BASE_URL
    print("[4] config.json api_key_open_router={} api_endpoint_open_router={} -> {}".format(
        redact(gk), ge, "OK" if good_cfg else "FAIL"))
    if not good_cfg:
        ok = False

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
