import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts" / "automation"))

from universal_replay import UniversalSessionClient

prompt = "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"

for session_name in ["session_qwen_chat_(alibaba).json", "session_mistral_le_chat.json", "session_cohere_coral_web.json", "session_cerebras_inference_chat.json", "session_zhipu_glm_chat.json", "session_felo_ai_web.json"]:
    path = HERE / "state" / "secrets" / session_name
    if not path.exists():
        continue
    client = UniversalSessionClient(path)
    injected_body = client._inject_prompt(prompt)
    print("="*60)
    print("FILE:", session_name)
    print("URL:", client.url)
    print("BASE BODY SNIPPET:", client.base_body[:200] if client.base_body else None)
    print("INJECTED BODY SNIPPET:", injected_body[:200] if injected_body else None)
