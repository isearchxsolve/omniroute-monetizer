"""Reproduce the PyGPT agent_llama path exactly to capture the real error.

PyGPT agent_llama mode with agent.llama.provider=openai does:
  1. OpenRouterLLM.llama() -> OpenAILike(model, api_key, api_base, is_chat_model=True,
     is_function_calling_model=tool_calls)
  2. OpenAIWorkflowAgent wraps it in llama_index FunctionAgent
  3. FunctionAgent.run("HI") streams events

This script replicates steps 1-3 with the exact args from models.json (key2)
and prints any exception with full traceback.
"""
import asyncio
import traceback

API_BASE = "https://api.tokenrouter.com/v1"
MODEL = "qwen/qwen3.8-max-free"
KEY2 = "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE"


def build_llm():
    from llama_index.llms.openai_like import OpenAILike
    # Exact args PyGPT OpenRouterLLM.llama() produces
    return OpenAILike(
        model=MODEL,
        api_key=KEY2,
        api_base=API_BASE,
        is_chat_model=True,
        is_function_calling_model=True,  # models.json tool_calls=true
    )


def test_direct_chat():
    print("=" * 70)
    print("TEST 1: direct OpenAILike chat (baseline)")
    print("=" * 70)
    try:
        llm = build_llm()
        resp = llm.complete("Say OK")
        print("OK ->", repr(resp.text[:200]))
        return True
    except Exception as e:
        print("FAILED:", type(e).__name__, e)
        traceback.print_exc()
        return False


def test_chat_messages():
    print("=" * 70)
    print("TEST 2: OpenAILike chat with messages (what agents use)")
    print("=" * 70)
    try:
        from llama_index.core.llms import ChatMessage
        llm = build_llm()
        resp = llm.chat([ChatMessage(role="user", content="Say OK")])
        print("OK ->", repr(resp.message.content[:200]))
        return True
    except Exception as e:
        print("FAILED:", type(e).__name__, e)
        traceback.print_exc()
        return False


async def test_function_agent():
    print("=" * 70)
    print("TEST 3: FunctionAgent (the actual agent_llama path)")
    print("=" * 70)
    try:
        from llama_index.core.agent.workflow import FunctionAgent
        llm = build_llm()
        agent = FunctionAgent(
            name="test",
            description="test",
            tools=[],
            llm=llm,
            system_prompt="You are a helpful assistant.",
            max_steps=5,
        )
        handler = agent.run(user_msg="HI")
        last = ""
        async for e in handler.stream_events():
            t = type(e).__name__
            resp = getattr(e, "response", None)
            delta = getattr(e, "delta", None)
            if resp:
                last = str(resp)
            print(f"  event={t} delta={delta!r} resp={str(resp)[:80]!r}")
        print("FINAL ->", repr(last[:200]))
        return bool(last)
    except Exception as e:
        print("FAILED:", type(e).__name__, e)
        traceback.print_exc()
        return False


if __name__ == "__main__":
    r1 = test_direct_chat()
    r2 = test_chat_messages()
    r3 = asyncio.run(test_function_agent())
    print("=" * 70)
    print(f"direct_chat={r1}  chat_messages={r2}  function_agent={r3}")
