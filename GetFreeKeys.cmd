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
echo.
echo   Starting with the providers that state NO CREDIT CARD is required.
echo.
python -u "scripts\automation\harvest_free_keys.py" %*
echo.
echo   Finished. Nothing was paid for and no CAPTCHA was touched.
pause
