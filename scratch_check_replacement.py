import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts" / "automation"))

from universal_replay import UniversalSessionClient

prompt = "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"

for session_name in [
    "session_cohere_coral_web.json",
    "session_cerebras_inference_chat.json",
    "session_zhipu_glm_chat.json",
    "session_qwen_chat_(alibaba).json",
    "session_chatgpt_free_web.json",
    "session_digen_ai.json",
]:
    path = HERE / "state" / "secrets" / session_name
    if not path.exists():
        continue
    client = UniversalSessionClient(path)
    injected_body = client._inject_prompt(prompt)
    print("=" * 60)
    print("FILE:", session_name)
    has_prompt = prompt in injected_body or json.dumps(prompt)[1:-1] in injected_body
    print("INJECTED HAS PROMPT?", has_prompt)
    if not has_prompt:
        print("  Base body excerpt:", client.base_body[:400])
        print("  Injected body excerpt:", injected_body[:400])
