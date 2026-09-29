@echo off
setlocal
chcp 65001 >nul
title Miaoxiang Console
cd /d "%~dp0"

curl.exe -fsS "http://127.0.0.1:8787/api/health" >nul 2>nul
if not errorlevel 1 (
    start "" "http://127.0.0.1:8787"
    exit /b 0
)

set "PY_CMD="
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)
if not defined PY_CMD (
    py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py -3.11"
)
if not defined PY_CMD (
    echo Python 3.11 or newer is required.
    echo Install Python 3.11 and enable "Add python.exe to PATH", then run this file again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo Failed to create Python environment.
        pause
        exit /b 1
    )
    ".venv\Scripts\python" -m pip install -e ".[dev]"
    if errorlevel 1 (
        echo Dependency installation failed.
        pause
        exit /b 1
    )
)

start "" "http://127.0.0.1:8787"
".venv\Scripts\python" -m backend.main --no-open
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo Console failed to start. Exit code: %EXIT_CODE%
echo Console exited. Logs: %CD%\logs\server.log
pause
