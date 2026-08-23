@echo off
REM ============================================================================
REM  ReplayRecordings.cmd -- one double-click. NO CLICKING BY YOU AT ALL.
REM
REM  This plays back the flows I already recorded by hand, the same way a
REM  Selenium test case is replayed:
REM
REM      1. it opens the provider's key page in the ROBOT's Chrome
REM      2. it presses the exact buttons that worked when I recorded them
REM      3. it makes a brand new API key
REM      4. it takes the key (from the page, or from the provider's own
REM         copy button)
REM      5. it plugs the key into OmniRoute
REM      6. it asks a REAL model a REAL question. If nothing answers, the
REM         entry is taken back out again. Nothing is ever reported as
REM         working on a promise.
REM
REM  Nothing is guessed. Every step was watched on the real page first.
REM
REM  You do not touch anything. A Chrome window will move on its own.
REM  That is the ROBOT's blank Chrome -- the one you signed into Google once.
REM  Your own Chrome is never opened, never read, never copied.
REM
REM  If a site wants a CARD    -> it walks away. Nothing is ever paid.
REM  If a site shows a CAPTCHA -> it walks away. Nothing is ever solved.
REM  If a site wants your PHONE-> it walks away.
REM
REM  Recorded flows live in the "recordings" folder, one file per provider.
REM  To do just one of them, drag this file into a terminal and add:
REM      --only reka
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
echo   Replaying the recorded flows. Please do not touch the Chrome window.
echo.
"%PY%" -u "scripts\automation\replay.py" %*
set "RC=%ERRORLEVEL%"
echo.
echo   Finished. Nothing was paid for and no CAPTCHA was touched.
echo   Full details were saved in state\harvest\replay_report.json
echo.
pause
exit /b %RC%
