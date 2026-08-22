@echo off
REM ============================================================================
REM  FIX CHROME - one click.
REM
REM  Run this ANY TIME Chrome looks wrong. It is safe to run whenever you like.
REM
REM  It will:
REM     * find and remove anything pointing at your real Chrome folder
REM     * check the guard that stops automation touching your Chrome
REM     * tell you which of your four accounts are signed in
REM     * take a fresh backup (only if Chrome is closed)
REM
REM  It NEVER writes to Chrome and NEVER touches your passwords.
REM
REM  Read the lines it prints:
REM     [ok]      nothing wrong
REM     [FIXED]   it repaired that by itself
REM     [YOU]     only you can do this (signing in to Google)
REM     [PROBLEM] show this line to the agent
REM ============================================================================

setlocal
cd /d "%~dp0"

set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY ( where py >nul 2>&1 && set "PY=py" )
if not defined PY (
    echo.
    echo   Could not find Python on this computer.
    echo   Tell the agent: "python is missing".
    echo.
    pause
    exit /b 2
)

if not exist "scripts\automation\chrome_selfheal.py" (
    echo.
    echo   Cannot find scripts\automation\chrome_selfheal.py next to this file.
    echo   Keep this launcher in the D:\omniroute-monetizer folder.
    echo.
    pause
    exit /b 2
)

if not exist "state" mkdir "state" >nul 2>&1

echo.
echo  Checking and repairing. This is safe.
echo.
"%PY%" "scripts\automation\chrome_selfheal.py" --json "state\chrome_selfheal_report.json"
set "RC=%ERRORLEVEL%"

echo.
echo ============================================================================
if "%RC%"=="0" (
    echo   NOTHING IS BROKEN THAT A SCRIPT CAN FIX.
    echo.
    echo   If any line above said [YOU], do that one thing - it is a Google
    echo   sign-in, and only a human can do it. That is not a bug.
) else (
    echo   SOMETHING NEEDS THE AGENT.
    echo.
    echo   Scroll up, find the lines starting with [PROBLEM], and show them
    echo   to the agent. Do not try to fix those by hand.
)
echo ============================================================================
echo.
echo   Full report saved to: state\chrome_selfheal_report.json
echo.
pause
endlocal
