@echo off
REM ============================================================================
REM  WireKeyFromClipboard.cmd
REM
REM  HOW TO USE:
REM    1. In your own Chrome, open a provider site and sign in.
REM    2. Copy the API key (select it, Ctrl+C).
REM    3. Double-click this file.
REM
REM  It reads the key from your clipboard, works out which provider it belongs
REM  to, checks it against that provider's own server, and wires it into
REM  OmniRoute. One key per run. Run it again for the next key.
REM
REM  The key is never shown on screen and never written to any log. It goes only
REM  into state\generated_keys.json, which git ignores.
REM
REM  No automation goes near your Chrome. You do the copying.
REM ============================================================================

setlocal
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
set "SCRIPT=%~dp0scripts\automation\paste_provider_key.py"

if not exist "%PY%" (
  echo.
  echo  [PROBLEM] Could not find the Python that has the tools installed.
  echo            Looked for: %PY%
  echo            Nothing was changed. Show this message to the agent.
  echo.
  pause
  exit /b 3
)

cls
"%PY%" "%SCRIPT%" --clipboard %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo  [ok] Done. Copy the next key and run this again.
) else (
  echo  [PROBLEM] It did not complete. Exit code %RC%.
  echo            Nothing was broken. Copy the text above and show it to the agent.
)
echo.
pause
endlocal
exit /b %RC%
