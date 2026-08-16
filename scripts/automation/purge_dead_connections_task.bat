@echo off
rem OmniRoute Dead-Connection Purge (Fix P5) — daily 03:00. Supported API only.
cd /d d:\omniroute-monetizer
"d:\omniroute-monetizer\.venv\Scripts\python.exe" -u "d:\omniroute-monetizer\scripts\automation\purge_dead_connections.py"
