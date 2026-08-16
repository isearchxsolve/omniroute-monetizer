@echo off
rem OmniRoute OpenRouter Fallback Wiring (Fix G6) — daily 03:30.
rem Adds weight-0 OpenRouter fallback entries to target combos (idempotent).
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\wire_openrouter_fallback.py"
