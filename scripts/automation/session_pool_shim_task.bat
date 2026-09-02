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

rem Liveness probe (worklog #1475): use the shim's constant-time local /healthz,
rem NOT /v1/models.  /v1/models is a merged readiness/discovery surface and can
rem reflect a sick upstream catalog even while this local process is alive.
rem curl.exe (built into Windows) avoids a visible Python launcher pair.
rem The old python probe spawned a venv-launcher + base-interpreter python.exe PAIR every 5 minutes
rem -- that transient pair is exactly the "two duplicate processes popping every 5 mins" the operator
rem saw. curl.exe spawns nothing visible and exits non-zero on any failure, same semantics.
curl.exe -s -f -o nul --max-time 3 "http://127.0.0.1:8190/healthz"

if not errorlevel 1 (
  rem Health proves the listener is ours. Preserve that exact interpreter and
  rem its venv launcher, but prune any older exact shim pair that lost its socket.
  "D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\session_pool_shim_owner.py" --port 8190 --reason healthy-orphan --preserve-listener >> "D:\omniroute-monetizer\logs\shim_task_diag.log" 2>&1
  if errorlevel 1 (
    echo [%date% %time%] FAILED healthy orphan prune >> "D:\omniroute-monetizer\logs\shim_task_diag.log"
    exit /b 1
  )
  exit /b 0
)

echo [%date% %time%] PRE-START >> "D:\omniroute-monetizer\logs\shim_task_diag.log"

rem /healthz already failed, so every process whose command line names THIS exact
rem repository shim + port belongs to this task's unhealthy launcher/interpreter
rem pair.  Stop the whole verified pair, including a launcher/orphan that no longer
rem owns the socket.  Never match generic python.exe or a foreign port owner.
"D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\session_pool_shim_owner.py" --port 8190 --reason unhealthy >> "D:\omniroute-monetizer\logs\shim_task_diag.log" 2>&1
if errorlevel 1 (
  echo [%date% %time%] FAILED exact owner cleanup >> "D:\omniroute-monetizer\logs\shim_task_diag.log"
  exit /b 1
)

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
curl.exe -s -f -o nul --max-time 3 "http://127.0.0.1:8190/healthz"
if not errorlevel 1 (
  "D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\session_pool_shim_owner.py" --port 8190 --reason healthy-orphan --preserve-listener >> "D:\omniroute-monetizer\logs\shim_task_diag.log" 2>&1
  if errorlevel 1 exit /b 1
  echo [%date% %time%] RECOVERED primary >> "D:\omniroute-monetizer\logs\shim_task_diag.log"
  exit /b 0
)
echo [%date% %time%] PRIMARY-UNHEALTHY cleanup-before-fallback >> "D:\omniroute-monetizer\logs\shim_task_diag.log"
rem The primary bound but did not answer.  Remove its exact task-owned process
rem pair before the fallback; otherwise the fallback only sees EADDRINUSE and the
rem scheduled task falsely reports success while the wedged primary survives.
"D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\session_pool_shim_owner.py" --port 8190 --reason failed-primary >> "D:\omniroute-monetizer\logs\shim_task_diag.log" 2>&1
if errorlevel 1 (
  echo [%date% %time%] FAILED primary cleanup >> "D:\omniroute-monetizer\logs\shim_task_diag.log"
  exit /b 1
)
echo [%date% %time%] FALLBACK-START alt-log >> "D:\omniroute-monetizer\logs\shim_task_diag.log"
rem A second fixed fallback file can itself be held exclusively.  Make the final
rem task-owned launch log unique per attempt so an unrelated log handle cannot
rem prevent the actual service process from starting.
set "SHIM_FALLBACK_LOG=D:\omniroute-monetizer\logs\shim_stdout_fallback_%RANDOM%_%RANDOM%.log"
start "" /b "D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\session_pool_shim.py" 8190 >> "%SHIM_FALLBACK_LOG%" 2>&1

rem Final verification makes Task Scheduler's Last Result honest.  Before this,
rem the BAT ended with a successful START command even when the fallback never
rem became healthy, so Last Result=0 concealed a dead consumer endpoint.
ping -n 4 127.0.0.1 >nul
curl.exe -s -f -o nul --max-time 3 "http://127.0.0.1:8190/healthz"
if not errorlevel 1 (
  "D:\omniroute-monetizer\.venv\Scripts\python.exe" -u "D:\omniroute-monetizer\scripts\automation\session_pool_shim_owner.py" --port 8190 --reason healthy-orphan --preserve-listener >> "D:\omniroute-monetizer\logs\shim_task_diag.log" 2>&1
  if errorlevel 1 exit /b 1
  echo [%date% %time%] RECOVERED fallback log=%SHIM_FALLBACK_LOG% >> "D:\omniroute-monetizer\logs\shim_task_diag.log"
  exit /b 0
)
echo [%date% %time%] FAILED no-healthy-shim log=%SHIM_FALLBACK_LOG% >> "D:\omniroute-monetizer\logs\shim_task_diag.log"
exit /b 1
