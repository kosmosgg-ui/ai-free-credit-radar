@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo PC must remain turned on. Run Ctrl+C to stop.
python radar.py --watch 15
pause
