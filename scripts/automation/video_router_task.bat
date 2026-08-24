@echo off
rem OmniRoute Video Router -- invoked by Windows Task Scheduler at logon and every 5 min.
rem Starts the two video faces if :8189 is not already answering.
rem Written by `python video_router.py boot --install`; edit that, not this.
cd /d D:\omniroute-monetizer
"D:\omniroute-monetizer\.venv\Scripts\python.exe" -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8189/healthz',timeout=3)" >nul 2>&1
if not errorlevel 1 exit /b 0
"D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\video_router.py" serve >> "D:\omniroute-monetizer\state\video_router_serve.log" 2>&1
