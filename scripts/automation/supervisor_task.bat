@echo off

rem OmniRoute Rig Supervisor -- invoked by Windows Task Scheduler every 5 min.

rem Starts the supervisor watch loop if it is not already running.

rem The supervisor monitors chat_pool (:20130), omniroute (:20128), video_router (:8189),
rem and session_pool_shim (:8190), restarting owned services that die.

cd /d D:\omniroute-monetizer

rem The [_] char class keeps the guard from matching ITS OWN query text: the literal
rem 'omni_supervisor' inside this wmic command line self-matched every time, so the guard
rem always saw "already running" and the bat never started anything (found 2026-08-30).
wmic process where "CommandLine like '%%omni[_]supervisor%%'" get ProcessId /format:list 2>nul | findstr "ProcessId" >nul

if not errorlevel 1 exit /b 0

rem Detached launch (worklog #1134): `start "" /b` runs the watch loop in the background and lets
rem THIS bat exit immediately, so no resident cmd.exe is left behind as the supervisor's parent.
rem The wmic guard above prevents double-launch.
start "" /b "D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\omni_supervisor.py" --watch >> "D:\omniroute-monetizer\logs\supervisor_stdout.log" 2>&1
