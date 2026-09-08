@echo off
title Media Catalog Agent v1.5
cd /d "%~dp0"
echo.
echo  Media Catalog Agent  v1.5
echo  Prefer INSTALL.bat the first time — it installs ffprobe and SMART tools.
echo  Leave this window OPEN. Port 8766.
echo.
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 agent.py --host 0.0.0.0 --port 8766 %*
  goto end
)
where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python agent.py --host 0.0.0.0 --port 8766 %*
  goto end
)
if exist "%~dp0host-installer\runtime\python\python.exe" (
  "%~dp0host-installer\runtime\python\python.exe" agent.py --host 0.0.0.0 --port 8766 %*
  goto end
)
echo Python not found. Double-click INSTALL.bat instead.
:end
echo.
pause
