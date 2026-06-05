@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [AiinLink] 使用 venv 启动...
.\venv\Scripts\python.exe main.py %*
if errorlevel 1 (
    echo.
    echo [AiinLink] 启动失败，按任意键退出...
    pause >nul
)
