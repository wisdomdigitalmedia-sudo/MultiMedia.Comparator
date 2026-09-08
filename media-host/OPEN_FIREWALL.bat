@echo off
title Open Media Host firewall (TCP 8766)
cd /d "%~dp0"
echo.
echo  Windows will ask "Do you want to allow this app to make changes?"
echo  Click Yes. That is how Admin access is granted — there is no password box in the setup page.
echo.
set "SCRIPT=%~dp0host-installer\open-firewall.ps1"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0open-firewall.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
if errorlevel 1 (
  echo.
  echo Firewall rule was not added. If you clicked No on the prompt, run this file again and click Yes.
  pause
  exit /b 1
)
echo.
echo Firewall TCP 8766 is open for the media host agent.
pause
