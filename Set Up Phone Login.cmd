@echo off
REM ============================================================================
REM  PHONE LOGIN - set it up once, then your fingerprint is your password.
REM
REM  This opens all four Chrome profiles, one after another, on the Google
REM  page where you add your phone as a passkey.
REM
REM  For each window that opens:
REM     - if it says "Create a passkey"  -> click it, approve on your phone
REM     - if it asks you to sign in      -> sign in, then add the passkey
REM
REM  After this is done once, any future sign-in is: scan QR, touch finger.
REM  No password, no OTP, no hunting through menus.
REM ============================================================================

setlocal
set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
    echo Could not find Chrome. Tell the agent.
    pause
    exit /b 1
)

set "PKPAGE=https://myaccount.google.com/signinoptions/passkeys"

echo.
echo ============================================================================
echo   SET UP PHONE LOGIN FOR ALL FOUR PROFILES
echo ============================================================================
echo.
echo   Turn on Bluetooth on your phone and on this computer first.
echo.
echo   Four Chrome windows will open, one for each account:
echo.
echo      1. Kunal (Your Chrome)  kunal.colab@gmail.com
echo      2. Kunal (Person 1)     xxpertcomments@gmail.com
echo      3. Niloy                niloydassana@gmail.com
echo      4. Kunal                isearch.xsolve@gmail.com
echo.
echo   In each window, look for "Create a passkey" and click it.
echo   Approve on your phone with your fingerprint. Then close that window.
echo.
pause

echo Opening 1 of 4 - kunal.colab@gmail.com ...
start "" "%CHROME%" --profile-directory="Default" "%PKPAGE%"
timeout /t 4 /nobreak >nul

echo Opening 2 of 4 - xxpertcomments@gmail.com ...
start "" "%CHROME%" --profile-directory="Profile 14" "%PKPAGE%"
timeout /t 4 /nobreak >nul

echo Opening 3 of 4 - niloydassana@gmail.com ...
start "" "%CHROME%" --profile-directory="Profile 16" "%PKPAGE%"
timeout /t 4 /nobreak >nul

echo Opening 4 of 4 - isearch.xsolve@gmail.com ...
start "" "%CHROME%" --profile-directory="Profile 17" "%PKPAGE%"

echo.
echo ============================================================================
echo   All four windows are open. Add the passkey in each one.
echo ============================================================================
echo.
echo   Done once, and you never type a password for these accounts again.
echo.
echo   If a login ever breaks in future:
echo      1. Double-click "Chrome Health Check.cmd"  - it tells you which one
echo      2. Double-click this file again            - scan QR, touch finger
echo.
pause
endlocal
