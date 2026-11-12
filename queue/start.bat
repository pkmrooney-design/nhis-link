@echo off
rem Double-click to start the queue server (Windows).
rem First run creates .venv, installs packages and asks for the admin password.
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\.installed" goto run

set PY=python
where python >nul 2>nul || set PY=py
%PY% --version >nul 2>nul || goto nopython

echo [setup] Creating virtual environment and installing packages...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv || goto fail
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto fail
type nul > ".venv\.installed"

:run
".venv\Scripts\python.exe" run.py
pause
exit /b

:nopython
echo Python 3.10+ is required: https://www.python.org/downloads/
echo (check "Add python.exe to PATH" during install)
pause
exit /b 1

:fail
echo Setup failed. See the messages above.
pause
exit /b 1
