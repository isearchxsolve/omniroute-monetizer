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

rem Health probe (worklog #1134): use curl.exe (built into Windows) instead of a python one-liner.
rem The old python probe spawned a venv-launcher + base-interpreter python.exe PAIR every 5 minutes
rem -- that transient pair is exactly the "two duplicate processes popping every 5 mins" the operator
rem saw. curl.exe spawns nothing visible and exits non-zero on any failure, same semantics.
curl.exe -s -o nul --max-time 3 "http://127.0.0.1:8190/v1/models"

if not errorlevel 1 exit /b 0

echo [%date% %time%] PRE-START >> "D:\omniroute-monetizer\logs\shim_task_diag.log"

rem Not answering -> start it. The venv launcher spawns the base interpreter as a child process
rem (normal Python 3.11 venv behavior on Windows), so ONE healthy shim always shows as two
rem python.exe rows: the launcher and the interpreter that holds :8190. That is expected, not a
rem duplicate. ExclusiveThreadingHTTPServer (allow_reuse_address=False) makes any true second bind
rem fail loudly, and run() treats "address already in use" as a clean no-op exit.
rem
rem Detached launch (worklog #1134): `start "" /b` runs the shim in the background and lets THIS
rem bat exit immediately. Before, the bat ran the shim synchronously as its last line, so the bat's
rem cmd.exe stayed resident as the shim's parent for the shim's whole life -- that is the stray
rem "cmd.exe" the operator kept seeing. With /b the bat exits, leaving only the python processes.
rem Verified 2026-08-28: a /b child survives the bat's console closing, and its stdout still lands
rem in the log. The 5-min scheduled task remains the supervisor (probe guard above prevents
rem double-launch; the shim's EADDRINUSE no-op guard is the second line of defense).
start "" /b "D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\session_pool_shim.py" 8190 >> "D:\omniroute-monetizer\logs\shim_stdout_current.log" 2>&1

rem Verify the listener actually came up (worklog #1367). cmd does NOT set errorlevel
rem when the >> append open fails -- it silently aborts the start line inside the hidden
rem window. That failure mode has now bitten twice (historic logs/shim_stdout.log, then
rem logs/shim_stdout_current.log): a foreign process holds an exclusive handle on the log
rem and the shim never launches while the task keeps reporting 0. Probe the listener and,
rem if absent, retry once against the alternate log file before yielding to the next cycle.
ping -n 4 127.0.0.1 >nul
curl.exe -s -o nul --max-time 3 "http://127.0.0.1:8190/v1/models"
if not errorlevel 1 exit /b 0
echo [%date% %time%] FALLBACK-START alt-log >> "D:\omniroute-monetizer\logs\shim_task_diag.log"
start "" /b "D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\session_pool_shim.py" 8190 >> "D:\omniroute-monetizer\logs\shim_stdout_alt.log" 2>&1
