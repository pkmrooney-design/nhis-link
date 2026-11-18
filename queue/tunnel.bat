@echo off
rem Double-click to open a temporary public https link (Cloudflare quick tunnel).
rem Keep this window open while the link is in use.
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run start.bat once first to install.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\tunnel.py
pause
