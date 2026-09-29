@echo off
setlocal
chcp 65001 >nul
title Miaoxiang Diagnostics
cd /d "%~dp0"

echo === Project ===
echo Location: %CD%
if exist "backend\main.py" (echo backend main: OK) else echo backend main: MISSING
if exist "frontend\index.html" (echo frontend: OK) else echo frontend: MISSING
if exist "data\accounts.json" (echo account data: OK) else echo account data: MISSING
if exist "pyproject.toml" (echo project config: OK) else echo project config: MISSING
echo.
echo === Python ===
where python 2>nul
python --version 2>nul
if errorlevel 1 echo python: not found
where py 2>nul
py -3.11 --version 2>nul
if errorlevel 1 echo py 3.11: not found
echo.
echo === F path ===
for %%I in ("%~dp0..") do set "MUSIC_FOLDER=%%~nxI"
set "TARGET_ROOT=F:\%MUSIC_FOLDER%"
if exist "%TARGET_ROOT%\aimusic\start_console.bat" (
    echo %TARGET_ROOT%: available
) else (
    echo %TARGET_ROOT%: unavailable
)
echo.
echo === Service ===
curl.exe -fsS "http://127.0.0.1:8787/api/health"
if errorlevel 1 echo Console service is not running.
echo.
echo === Chrome ===
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    echo Google Chrome: OK
) else (
    echo Google Chrome was not found in the default location.
)
echo.
echo Diagnostics finished.
pause
