@echo off

rem OmniRoute Rig Supervisor -- invoked by Windows Task Scheduler every 5 min.

rem Starts the supervisor watch loop if it is not already running.

rem The supervisor monitors chat_pool (:20130), omniroute (:20128), video_router (:8189),
rem and session_pool_shim (:8190), restarting owned services that die.

cd /d D:\omniroute-monetizer

wmic process where "CommandLine like '%%omni_supervisor%%'" get ProcessId /format:list 2>nul | findstr "ProcessId" >nul

if not errorlevel 1 exit /b 0

"D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\omni_supervisor.py" --watch >> "D:\omniroute-monetizer\logs\supervisor_stdout.log" 2>&1
