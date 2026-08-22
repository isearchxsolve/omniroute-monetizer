@echo off
REM ============================================================================
REM  GetFreeKeys.cmd -- one double-click. Sign up free, get a key, wire it.
REM
REM  What happens:
REM    * For each free provider, its website opens in the ROBOT's Chrome -- the
REM      blank profile you already signed into Google with. Your own Chrome is
REM      never opened, read or copied.
REM    * You click "Continue with Google", then create an API key and copy it.
REM    * Press Enter here. The key is wired into OmniRoute and PROVED by asking
REM      a real model a real question. If it cannot answer, the row is removed.
REM
REM  If a site asks for a CARD  -> type p. We walk away. Nothing is ever paid.
REM  If you see a CAPTCHA      -> type c. We walk away. Nothing is ever solved.
REM  Each provider is tried once. Nothing is retried or hammered.
REM
REM  Card-free providers are queued first, so the early ones need nothing but
REM  your Google click.
REM ============================================================================
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

REM Find Python the way SignInWithGoogleOnce.cmd does. A bare "python" is not on PATH in a
REM plain cmd.exe window, which is why an earlier version of this file did nothing at all.
set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
if "%PY%"=="python" (
  where python >nul 2>nul
  if errorlevel 1 (
    echo   [PROBLEM] Could not find Python on this computer.
    echo   Looked in:
    echo     %LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe
    echo     %~dp0.venv\Scripts\python.exe
    echo     and on PATH.
    echo.
    pause
    exit /b 3
  )
)

echo.
echo   Starting with the providers that state NO CREDIT CARD is required.
echo.
"%PY%" -u "scripts\automation\harvest_free_keys.py" %*
echo.
echo   Finished. Nothing was paid for and no CAPTCHA was touched.
pause
