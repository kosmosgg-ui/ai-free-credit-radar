@echo off
chcp 65001 >nul
cd /d "%~dp0"
python radar.py --once
if errorlevel 1 (
  echo [ERROR] Python installation or network may be unavailable.
  pause
  exit /b 1
)
start "" "%~dp0site\index.html"
pause
