@echo off
title Media Host setup 1.6
cd /d "%~dp0"
echo.
echo  Media Host setup  —  1.6  (any OS pair)
echo  Double-click installer. Your browser will open.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"
if errorlevel 1 (
  echo.
  echo Setup did not finish. See the message above.
  pause
)
