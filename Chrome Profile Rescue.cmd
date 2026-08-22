@echo off
setlocal
title Chrome Profile Rescue
set "RESCUE_SCRIPT=%~dp0scripts\automation\restore_chrome_profiles.ps1"

if not exist "%RESCUE_SCRIPT%" (
  echo Chrome Profile Rescue could not find its recovery script.
  echo Expected: "%RESCUE_SCRIPT%"
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%RESCUE_SCRIPT%" -Mode Guided
echo.
pause
