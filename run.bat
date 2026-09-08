@echo off
title Media Comparator
cd /d "%~dp0"
echo.
echo  Media Comparator  —  catalog UI on this PC
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo Python 3.9+ is required.
  echo Install from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  call ".venv\Scripts\activate.bat"
  python -m pip install -U pip
  pip install -r requirements.txt
) else (
  call ".venv\Scripts\activate.bat"
)

echo Starting Media Comparator at http://127.0.0.1:8767
echo Open Setup in the app to pick Linux/Windows/Mac and scan the LAN.
python app.py
if errorlevel 1 pause
