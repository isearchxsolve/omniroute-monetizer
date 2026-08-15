import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r"C:\Users\Admin\.gemini\antigravity-ide\brain\66113465-2986-4b2f-a97a-0f5e23d17c33\.system_generated\steps\5256\content.md"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

idx = text.find("Copy the Details:")
if idx != -1:
    print(text[idx:idx+1500].replace(r"\n", "\n").replace(r"\"", '"'))




