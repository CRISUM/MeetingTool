@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================
echo   会议录音转写工具 · 环境诊断
echo ================================================
echo.

:: ── 系统 Python ────────────────────────────────
echo [系统 Python]
python --version 2>nul
if errorlevel 1 (
    echo   X 未检测到系统 Python
) else (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo   √ %%i
)
echo.

:: ── ffmpeg ─────────────────────────────────────
echo [ffmpeg]
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo   X 未检测到 ffmpeg
) else (
    for /f "tokens=1-3" %%a in ('ffmpeg -version 2^>^&1 ^| findstr /b "ffmpeg version"') do echo   √ %%a %%b %%c
)
echo.

:: ── venv + 依赖 + PyTorch + 缓存 + 环境变量 ────
echo [虚拟环境 / 依赖 / PyTorch / 缓存 / 环境变量]
if exist "venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" _diagnose.py
) else (
    echo   X venv\ 不存在 ^(请先运行「安装.bat」^)
)
echo.

echo ================================================
echo   诊断完成
echo ================================================
pause
