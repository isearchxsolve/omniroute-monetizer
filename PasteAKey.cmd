@echo off
REM ============================================================================
REM  PasteAKey.cmd
REM
REM  For providers that will not let an automated browser sign in -- Google most
REM  of all. Measured 2026-08-22: Google answers "Couldn't sign you in / This
REM  browser or app may not be secure" in a Playwright-launched Chrome, and we
REM  do not disguise that.
REM
REM  So you do it the easy way instead:
REM    1. Open the provider page in YOUR OWN Chrome, normally.
REM    2. Copy the API key.
REM    3. Run this and paste it once.
REM
REM  Nothing automated goes near your Chrome. You do the copying.
REM
REM  The key is hidden as you paste it, and it is checked against the provider's
REM  own server before anything calls it working. It is saved to
REM  state\generated_keys.json, which is gitignored and never committed.
REM ============================================================================

setlocal
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
set "SCRIPT=%~dp0scripts\automation\provider_key_paste.py"

if not exist "%PY%" (
  echo.
  echo  [PROBLEM] Could not find the Python with the needed packages.
  echo            Looked for: %PY%
  echo            Nothing was changed. Show this message to the agent.
  echo.
  pause
  exit /b 3
)

if not exist "%SCRIPT%" (
  echo.
  echo  [PROBLEM] Could not find the paste script.
  echo            Looked for: %SCRIPT%
  echo.
  pause
  exit /b 3
)

cls
"%PY%" "%SCRIPT%" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo  [ok] Finished. You can close this window.
) else (
  echo  [info] Exit code %RC%. If a key came back NOT VERIFIED, the text above says
  echo         what the provider answered. Show it to the agent.
)
echo.
pause
endlocal
exit /b %RC%
