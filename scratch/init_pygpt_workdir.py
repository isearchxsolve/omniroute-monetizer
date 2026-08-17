#!/usr/bin/env python3
"""
Headlessly initialize the PyGPT (pygpt-net) workdir at ~/.config/pygpt-net.

Replicates exactly what PyGPT's provider install() methods do on first GUI run,
without launching the Qt GUI:
  - Config.prepare_workdir(): create workdir + path.cfg
  - provider.core.config.json_file.install(): copy config.json
  - provider.core.model.json_file.install(): copy models.json
  - presets provider: copy presets/
  - settings files copied from data/config

This lets us write routes/keys before the user ever opens the GUI.
"""
import os
import shutil
import sys
from pathlib import Path

import pygpt_net

APP_PATH = os.path.dirname(os.path.abspath(pygpt_net.__file__))
SRC_CONFIG = os.path.join(APP_PATH, "data", "config")
WORKDIR = os.path.join(Path.home(), ".config", "pygpt-net")


def main():
    print("APP_PATH:", APP_PATH)
    print("SRC_CONFIG:", SRC_CONFIG)
    print("WORKDIR:", WORKDIR)

    if os.path.exists(os.path.join(WORKDIR, "models.json")):
        print("Workdir already initialized (models.json exists). Nothing to do.")
        return

    os.makedirs(WORKDIR, exist_ok=True)

    # path.cfg (Config.prepare_workdir writes an empty path.cfg)
    pcfg = os.path.join(WORKDIR, "path.cfg")
    if not os.path.exists(pcfg):
        with open(pcfg, "w", encoding="utf-8") as f:
            f.write("")
        print("created path.cfg")

    # Copy top-level config files
    for fn in ["config.json", "models.json", "settings.json",
               "settings_section.json", "modes.json"]:
        src = os.path.join(SRC_CONFIG, fn)
        dst = os.path.join(WORKDIR, fn)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)
            print("copied", fn)

    # Copy presets dir
    src_presets = os.path.join(SRC_CONFIG, "presets")
    dst_presets = os.path.join(WORKDIR, "presets")
    if os.path.isdir(src_presets) and not os.path.isdir(dst_presets):
        shutil.copytree(src_presets, dst_presets)
        print("copied presets/")

    # Create standard user subdirs PyGPT expects
    for d in ["data", "history", "storage", "presets", "upload", "vector_db",
              "indexes", "cache", "logs", "profiles"]:
        p = os.path.join(WORKDIR, d)
        os.makedirs(p, exist_ok=True)

    print("Workdir initialized:")
    for item in sorted(os.listdir(WORKDIR)):
        print("  ", item)


if __name__ == "__main__":
    main()
