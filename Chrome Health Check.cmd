@echo off
setlocal
REM ============================================================================
REM  Chrome Health Check -- one click, read-only, changes nothing.
REM
REM  Run this FIRST whenever Chrome looks wrong ("Sign in to Chrome", missing
REM  profile names, automation reporting a login wall).
REM
REM  It answers, in plain terms:
REM    * is Chrome actually closed?
REM    * is automation pointed at the real Chrome folder, or a fake one?
REM    * does each profile still hold its Google sign-in credential?
REM    * have the cookie stores been emptied?
REM    * which backup, if any, can restore each profile?
REM
REM  It never writes to Chrome, and never reads a password, cookie or token.
REM ============================================================================

cd /d "%~dp0"

set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY ( where py >nul 2>&1 && set "PY=py" )
if not defined PY (
    echo.
    echo   Could not find Python on this computer.
    echo   Install Python 3, or ask the agent to run the audit directly.
    echo.
    pause
    exit /b 2
)

if not exist "scripts\automation\chrome_auth_audit.py" (
    echo.
    echo   Cannot find scripts\automation\chrome_auth_audit.py next to this file.
    echo   Keep this launcher in the D:\omniroute-monetizer folder.
    echo.
    pause
    exit /b 2
)

if not exist "state" mkdir "state" >nul 2>&1

echo.
echo  Running a read-only Chrome health check. Nothing will be changed.
echo.
"%PY%" "scripts\automation\chrome_auth_audit.py" --json "state\chrome_auth_report.json"

echo.
echo ============================================================================
echo  WHAT TO DO NEXT
echo ============================================================================
echo.
echo  If a profile shows credential_complete=False, Chrome is NOT signed in for
echo  that profile, no matter what name or email is displayed next to it.
echo.
echo  Look at the "recovery coverage map" above:
echo.
echo    * "USABLE" next to a backup  -  that profile's sign-in may be restorable
echo      from local files. Ask the agent to run chrome_session_restore.py for
echo      that one profile. It is reversible and it asks before changing anything.
echo.
echo    * "NO USABLE LOCAL SOURCE"   -  that profile can only be recovered by
echo      signing in to Google normally. No script can avoid this.
echo.
echo  To make a fresh safety backup first, run "Chrome Profile Rescue.cmd"
echo  and choose option 1.
echo.
pause
endlocal
