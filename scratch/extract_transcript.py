import sys
sys.stdout.reconfigure(encoding='utf-8')
import re
import json

path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\66113465-2986-4b2f-a97a-0f5e23d17c33\.system_generated\steps\5256\content.md"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# Find transcript data or player captions
print("Searching for transcript/captions...")
for m in re.finditer(r'"captionTracks":\s*(\[[^\]]+\])', text):
    print("Caption tracks:", m.group(1))

# Extract all text runs in transcript renderer if any
for m in re.finditer(r'"transcriptSegmentRenderer":\s*\{.*?"snippet":\s*\{"runs":\s*\[\{"text":\s*"([^"]+)"', text):
    print(m.group(1), end=" ")

# Search for Token Router steps in the text
for m in re.finditer(r'tokenrouter|token router|k3', text, re.I):
    idx = m.start()
    print("\n--- TOKENROUTER CONTEXT ---")
    print(text[max(0, idx-200):min(len(text), idx+300)])
