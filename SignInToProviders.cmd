@echo off
REM ============================================================================
REM  Sign In To Providers.cmd
REM
REM  Double-click this once. It opens a SEPARATE, EMPTY browser that belongs to
REM  the automation -- not your Chrome. You sign in to the provider websites by
REM  hand, one at a time. After that the automation reuses that browser on its
REM  own, forever, without touching your Chrome or your Google logins.
REM
REM  Your own Chrome can stay open. You do not need to close anything.
REM
REM  This file only launches the Python script. The script is the thing that
REM  carries the chrome_live_guard protection, so the guard still applies.
REM  See CHROME_RULES.md.
REM ============================================================================

setlocal
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
set "SCRIPT=%~dp0scripts\automation\provider_login_helper.py"

if not exist "%PY%" (
  echo.
  echo  [PROBLEM] Could not find the Python that has the browser tools installed.
  echo            Looked for: %PY%
  echo.
  echo            Nothing was opened. Tell the agent this message.
  echo.
  pause
  exit /b 3
)

if not exist "%SCRIPT%" (
  echo.
  echo  [PROBLEM] Could not find the sign-in script.
  echo            Looked for: %SCRIPT%
  echo.
  pause
  exit /b 3
)

cls
REM  --google is deliberately NOT passed. Google refuses sign-ins from an
REM  automation-controlled browser ("Couldn't sign you in / This browser or app
REM  may not be secure"), measured 2026-08-22. See MASTER_WORKLOG.md #1033.
REM  Google-only sites are handled by PasteAKey.cmd instead.
"%PY%" "%SCRIPT%" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo  [ok] Finished. You can close this window.
) else (
  echo  [PROBLEM] It stopped early, exit code %RC%. Nothing in your own Chrome was changed.
  echo            Copy the text above and show it to the agent.
)
echo.
pause
endlocal
exit /b %RC%
