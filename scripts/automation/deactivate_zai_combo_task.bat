@echo off
rem OmniRoute Dead auto/zai Combo Deactivation (Fix G2) — daily 03:45.
rem Idempotent; safe to run repeatedly.
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\deactivate_zai_combo.py"
