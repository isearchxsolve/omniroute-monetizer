#!/usr/bin/env python3
"""Set agent.iterations to a safe non-zero value (backup-first)."""
import json
import os
import shutil
import datetime
from pathlib import Path

WORKDIR = os.path.join(Path.home(), ".config", "pygpt-net")
CFG = os.path.join(WORKDIR, "config.json")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup = os.path.join("d:\\omniroute-monetizer\\state", "pygpt_config_backup_" + ts + ".json")
shutil.copy2(CFG, backup)
print("backup:", backup)

with open(CFG, "r", encoding="utf-8") as f:
    data = json.load(f)

items = data.get("items", data)
before = items.get("agent.iterations")
items["agent.iterations"] = 10
if "items" in data:
    data["items"] = items

with open(CFG, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4, ensure_ascii=False)

print("agent.iterations: {} -> {}".format(before, items.get("agent.iterations")))
print("DONE")
