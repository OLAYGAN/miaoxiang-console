@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
start "" "http://127.0.0.1:8787"
"%~dp0MiaoxiangConsole.exe"
echo.
echo 控制台已经退出。
pause
