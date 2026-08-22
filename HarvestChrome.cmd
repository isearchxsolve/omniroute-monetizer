@echo off
REM ============================================================================
REM  HarvestChrome.cmd
REM
REM  HOW TO USE:
REM    1. Double-click this file. A Chrome window opens on the ROBOT's profile
REM       (it is NOT your normal Chrome -- nothing here can log you out).
REM    2. LEAVE THAT WINDOW OPEN.
REM    3. Run the key harvester in attach mode. It drives THAT Chrome:
REM
REM         python scripts\automation\auto_key_harvester.py --attach
REM
REM  WHY THIS EXISTS:
REM    When the harvester launches its own Chrome, that Chrome carries automation
REM    flags, and provider sites (Cloudflare, etc.) treat it as a bot and throw
REM    CAPTCHA walls. A Chrome that YOU started is an ordinary browser -- so the
REM    harvester attaches to this one instead. Far fewer CAPTCHAs, and your own
REM    Chrome profiles are never touched (that is a hard rule in this project).
REM
REM  The debugging port it opens (9333) belongs to the robot profile only, on
REM  this machine only. Close the window when the harvest is done.
REM ============================================================================

setlocal
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
set "SCRIPT=%~dp0scripts\automation\provider_login_helper.py"

if not exist "%PY%" (
  echo.
  echo  [PROBLEM] Could not find the Python that has the tools installed.
  echo            Looked for: %PY%
  echo            Nothing was changed. Show this message to the agent.
  echo.
  pause
  exit /b 3
)

"%PY%" "%SCRIPT%" --harvest-browser
echo.
echo  Leave this Chrome window OPEN, then run the harvester with --attach.
echo.
pause
endlocal
exit /b %ERRORLEVEL%
