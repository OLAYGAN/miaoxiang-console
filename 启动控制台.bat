@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/health' -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }"
if "%ERRORLEVEL%"=="0" (
    start "" "http://127.0.0.1:8787"
    exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Python 3.11 is required.
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
