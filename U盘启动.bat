@echo off
setlocal
title Miaoxiang Portable Launcher

set "USB_DRIVE=%~d0"
for %%I in ("%~dp0..") do set "MUSIC_FOLDER=%%~nxI"
set "TARGET_ROOT=F:\%MUSIC_FOLDER%"

if not exist "%TARGET_ROOT%\" (
    subst F: "%USB_DRIVE%\"
    if errorlevel 1 (
        echo Cannot map %USB_DRIVE% to F:.
        echo Close programs using F:, or assign F: to this USB disk.
        pause
        exit /b 1
    )
)

if not exist "%TARGET_ROOT%\aimusic\start_console.bat" (
    echo Cannot find %TARGET_ROOT%\aimusic\start_console.bat
    echo Make sure this launcher stays inside the music\aimusic folder.
    pause
    exit /b 1
)

cd /d "%TARGET_ROOT%\aimusic"
call "%TARGET_ROOT%\aimusic\start_console.bat"
exit /b %ERRORLEVEL%
