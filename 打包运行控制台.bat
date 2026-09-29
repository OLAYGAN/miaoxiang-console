@echo off
setlocal
chcp 65001 >nul
title Miaoxiang Console
cd /d "%~dp0"
if not exist "%~dp0MiaoxiangConsole.exe" (
    echo MiaoxiangConsole.exe is missing.
    echo Antivirus software may have removed this unsigned executable.
    echo Restore it from MiaoxiangConsole-20260924.zip and add this folder to trust list.
    pause
    exit /b 1
)
start "" "http://127.0.0.1:8787"
"%~dp0MiaoxiangConsole.exe"
echo.
echo 控制台已经退出。
pause
