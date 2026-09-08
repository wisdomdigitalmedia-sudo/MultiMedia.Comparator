@echo off
cd /d "%~dp0"
echo Starting agent as Administrator for CrystalDiskInfo SMART...
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0RUN_AGENT.bat' -Verb RunAs"
if errorlevel 1 (
  echo Failed. Right-click RUN_AGENT.bat - Run as administrator.
  pause
)
