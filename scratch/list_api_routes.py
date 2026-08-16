#!/usr/bin/env python3
import os
from pathlib import Path

api_root = Path(r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\app\api")
if api_root.exists():
    routes = []
    for root, dirs, files in os.walk(api_root):
        if "route.js" in files:
            rel = os.path.relpath(root, api_root)
            routes.append(f"/api/{rel.replace(os.sep, '/')}")
    for r in sorted(routes):
        print(r)
