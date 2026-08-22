@echo off
REM ============================================================================
REM  HarvestKeysAuto.cmd -- one double-click. NO CLICKING BY YOU AT ALL.
REM
REM  This is the robot doing the whole job by itself, for every free provider:
REM      1. opens the provider's site
REM      2. finds the login page
REM      3. presses "Continue with Google"
REM      4. picks your Google profile from the list
REM      5. finds the API keys page
REM      6. presses "Create new API key"
REM      7. copies the key
REM      8. plugs it into OmniRoute and PROVES it by asking a real model a real
REM         question. If nothing answers, the entry is removed again.
REM
REM  You do not touch anything. A Chrome window will open and move on its own.
REM  That is the ROBOT's blank Chrome -- the one you signed into Google once.
REM  Your own Chrome is never opened, never read, never copied.
REM
REM  If a site wants a CARD    -> the robot walks away. Nothing is ever paid.
REM  If a site shows a CAPTCHA -> the robot walks away. Nothing is ever solved.
REM  If a site wants your PHONE-> the robot walks away.
REM  Each provider gets ONE try and 150 seconds. Nothing is retried or hammered.
REM
REM  At the end you get a list: what worked, and what it walked away from.
REM ============================================================================
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo   [PROBLEM] Could not find Python on this computer.
  echo   Looked in:
  echo     %LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe
  echo     %~dp0.venv\Scripts\python.exe
  echo.
  pause
  exit /b 3
)

echo.
echo   The robot is starting. Please do not touch the Chrome window it opens.
echo   Providers that promise NO CREDIT CARD are done first.
echo.
"%PY%" -u "scripts\automation\auto_key_harvester.py" --budget 150 %*
set "RC=%ERRORLEVEL%"
echo.
echo   Finished. Nothing was paid for and no CAPTCHA was touched.
echo   Full details were saved in state\harvest\auto_harvest.json
echo.
pause
exit /b %RC%
