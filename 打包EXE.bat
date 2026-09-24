@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo 未找到 .venv，请先运行 启动控制台.bat 完成环境安装。
    pause
    exit /b 1
)

".venv\Scripts\python" -m pip show pyinstaller >nul 2>nul
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    ".venv\Scripts\python" -m pip install pyinstaller
    if errorlevel 1 (
        echo PyInstaller 安装失败。
        pause
        exit /b 1
    )
)

echo 正在清理旧构建...
if exist "build\pyinstaller" rmdir /s /q "build\pyinstaller"
if exist "dist\MiaoxiangConsole" rmdir /s /q "dist\MiaoxiangConsole"

echo 正在打包，请稍候...
".venv\Scripts\python" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onedir ^
    --console ^
    --name MiaoxiangConsole ^
    --distpath dist ^
    --workpath build\pyinstaller ^
    --specpath build\pyinstaller ^
    --paths "%CD%" ^
    --add-data "%~dp0frontend;frontend" ^
    --collect-all playwright ^
    --collect-all uvicorn ^
    --collect-all fastapi ^
    --collect-all websockets ^
    --collect-all pydantic ^
    --collect-all httpx ^
    --collect-all certifi ^
    --hidden-import=uvicorn.logging ^
    --hidden-import=uvicorn.loops.auto ^
    --hidden-import=uvicorn.protocols.http.auto ^
    --hidden-import=uvicorn.protocols.websockets.auto ^
    backend\main.py

if errorlevel 1 (
    echo.
    echo 打包失败，请查看上方错误信息。
    pause
    exit /b 1
)

copy /Y "打包运行控制台.bat" "dist\MiaoxiangConsole\启动控制台.bat" >nul

echo.
echo 打包完成：
echo %CD%\dist\MiaoxiangConsole\MiaoxiangConsole.exe
echo.
echo 将整个 MiaoxiangConsole 文件夹复制到第二台电脑即可。
pause
