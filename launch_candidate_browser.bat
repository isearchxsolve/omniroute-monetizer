@echo off
echo Launching all 50 providers from free_llm_chat_sites.json...
python scripts\automation\launch_and_harvest_chats.py launch --port 9222
echo Please sign in to any required providers, then close this window.
pause
