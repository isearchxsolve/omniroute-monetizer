@echo off
setlocal
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo Google Chrome was not found.
  pause
  exit /b 1
)
tasklist /fi "imagename eq chrome.exe" 2>nul | find /i "chrome.exe" >nul
if not errorlevel 1 (
  echo Close every Chrome window first, then run this file again.
  pause
  exit /b 2
)
start "" "%CHROME%" --profile-directory="Profile 17" --restore-last-session
endlocal
