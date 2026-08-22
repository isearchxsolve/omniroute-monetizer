@echo off
REM ============================================================================
REM  SignInWithGoogleOnce.cmd
REM
REM  DOUBLE-CLICK THIS ONE FILE. You only ever need to do it once.
REM
REM  What happens:
REM    1. A brand-new, EMPTY Chrome window opens. It belongs to the robot.
REM       It is NOT your Chrome. Nothing you do in it can log you out of your
REM       own profiles, and your own Chrome can stay open the whole time.
REM    2. You sign in with your Google account, the normal way.
REM    3. You CLOSE that window.
REM
REM  After that the robot visits each provider site in that same browser and
REM  presses "Continue with Google" for you, so you never type a provider
REM  password.
REM
REM  WHY THIS IS A SEPARATE FILE FROM SignInToProviders.cmd
REM  -----------------------------------------------------
REM  Google refuses its own password screen inside an automated browser
REM  ("Couldn't sign you in / This browser or app may not be secure"),
REM  measured 2026-08-22. SignInToProviders.cmd drives Chrome through
REM  Playwright, which Google detects. So THIS file starts plain, ordinary
REM  Chrome with no automation switches at all -- Google sees a completely
REM  normal browser, because it IS one. We do not disguise anything.
REM
REM  The robot's login then stays saved in its own profile folder, and the
REM  automation reuses it afterwards without ever automating a Google password.
REM
REM  This file only launches the Python script. The script is what carries the
REM  chrome_live_guard protection, so the guard still applies and this can
REM  never touch your real Chrome folder. See CHROME_RULES_FOR_AGENTS.md.
REM ============================================================================

setlocal
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
set "SCRIPT=%~dp0scripts\automation\provider_login_helper.py"

if not exist "%PY%" set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo.
  echo  [PROBLEM] Could not find Python.
  echo            Nothing was opened. Show this message to the agent.
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
"%PY%" "%SCRIPT%" --manual-signin
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo  [ok] Thank you. Now tell the agent: "signed in".
) else (
  echo  [PROBLEM] It stopped early, exit code %RC%.
  echo            Nothing in your own Chrome was changed.
  echo            Copy the text above and show it to the agent.
)
echo.
pause
endlocal
exit /b %RC%
