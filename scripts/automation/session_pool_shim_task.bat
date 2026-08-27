@echo off

rem OmniRoute Session Pool Shim -- invoked by Windows Task Scheduler every 5 min.

rem Starts the shim on :8190 if it is not already answering.

rem The shim is the OpenAI-compatible face over the SessionPool (chat + video).
rem Its supply is session files on disk, so it survives reboot like the chat pool.

cd /d D:\omniroute-monetizer

"D:\omniroute-monetizer\.venv\Scripts\python.exe" -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8190/v1/models',timeout=3)" >nul 2>&1

if not errorlevel 1 exit /b 0

"D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\session_pool_shim.py" 8190 >> "D:\omniroute-monetizer\logs\shim_stdout.log" 2>&1
