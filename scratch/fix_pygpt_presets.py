#!/usr/bin/env python3
"""
Fix PyGPT agent presets so Agent (LlamaIndex) mode actually works:
  1. current.agent_llama.json: name "*" -> "ReAct Agent" (PyGPT silently stops
     the agent flow when preset.name == "*"), model key1 -> key2.
  2. Every preset referencing revoked key1 -> key2.
  3. agent_react.json: model gpt-4o -> key2 (TokenRouter route).
Backup-first. Secrets redacted in output.
"""
import json
import os
import shutil
import datetime
from pathlib import Path

WORKDIR = os.path.join(Path.home(), ".config", "pygpt-net")
PRESETS = os.path.join(WORKDIR, "presets")
KEY1 = "tokenrouter-qwen38max-key1"
KEY2 = "tokenrouter-qwen38max-key2"

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup = os.path.join("d:\\omniroute-monetizer\\state", "pygpt_presets_backup_" + ts)
shutil.copytree(PRESETS, backup)
print("backup:", backup)

# Load the ReAct preset as the template for the current agent_llama selection
with open(os.path.join(PRESETS, "agent_react.json"), "r", encoding="utf-8") as f:
    react = json.load(f)

changed = []
for fn in sorted(os.listdir(PRESETS)):
    if not fn.endswith(".json"):
        continue
    path = os.path.join(PRESETS, fn)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    orig = json.dumps(data, sort_keys=True)

    # fix revoked key everywhere
    if data.get("model") == KEY1:
        data["model"] = KEY2
    # point the bundled ReAct preset at our TokenRouter route
    if fn == "agent_react.json" and data.get("model") == "gpt-4o":
        data["model"] = KEY2
    # fix the "no preset selected" blocker: replicate what the UI does when the
    # user picks "ReAct Agent" — copy the preset into current.agent_llama.json
    if fn == "current.agent_llama.json" and data.get("name") == "*":
        keep_uuid = data.get("uuid")
        keep_meta = data.get("__meta__")
        data = dict(react)
        data["uuid"] = keep_uuid
        data["filename"] = "current.agent_llama"
        data["model"] = KEY2
        data["__meta__"] = keep_meta

    if json.dumps(data, sort_keys=True) != orig:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        changed.append((fn, data.get("name"), data.get("model"),
                        data.get("agent_provider")))

print("\nchanged {} file(s):".format(len(changed)))
for fn, name, model, prov in changed:
    print("  {} -> name={!r} model={!r} agent_provider={!r}".format(fn, name, model, prov))

# verify no key1 references remain anywhere in presets
leftover = []
for fn in sorted(os.listdir(PRESETS)):
    if not fn.endswith(".json"):
        continue
    with open(os.path.join(PRESETS, fn), "r", encoding="utf-8") as f:
        if KEY1 in f.read():
            leftover.append(fn)
print("\nkey1 references remaining:", leftover if leftover else "NONE")
print("DONE")
