@echo off

rem OmniRoute Session Pool Shim -- invoked by Windows Task Scheduler every 5 min.

rem Starts the shim on :8190 if it is not already answering.

rem The shim is the OpenAI-compatible face over the SessionPool (chat + video).
rem Its supply is session files on disk, so it survives reboot like the chat pool.

cd /d D:\omniroute-monetizer

rem Spend gate (worklog #1123): the operator's film-runway instruction is the consent for the
rem pool's video seats to charge. rtst clips cost 6 credits, flow clips ~20 credits; the
rem per-seat clients still enforce their own OMNI_VIDEO_MAX_SPEND caps before any submit.
set OMNI_VIDEO_CONFIRM_SPEND=1

"D:\omniroute-monetizer\.venv\Scripts\python.exe" -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8190/v1/models',timeout=3)" >nul 2>&1

if not errorlevel 1 exit /b 0

"D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\session_pool_shim.py" 8190 >> "D:\omniroute-monetizer\logs\shim_stdout.log" 2>&1
