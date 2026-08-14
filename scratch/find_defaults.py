import os
import glob
import re

omniroute_dir = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute"

print("Searching omniroute provider definitions for default models...")
for root, dirs, files in os.walk(omniroute_dir):
    for f in files:
        if f.endswith('.js') or f.endswith('.mjs') or f.endswith('.json'):
            fpath = os.path.join(root, f)
            if 'provider' in f.lower() or 'model' in f.lower() or 'catalog' in f.lower():
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as fp:
                        content = fp.read()
                        if 'antigravity' in content or 'github' in content or 'amazon-q' in content or 'grok-cli' in content:
                            print(f"Found match in: {fpath}")
                except:
                    pass
