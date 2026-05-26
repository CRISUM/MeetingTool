@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================
echo   会议录音转写工具 · 更新
echo ================================================
echo.

:: ── 1. git pull ────────────────────────────────
echo 【1/2】拉取最新代码...
git --version >nul 2>&1
if errorlevel 1 (
    echo   ! 未检测到 git，跳过代码更新（请手动覆盖项目文件）。
) else (
    if exist ".git" (
        git pull --ff-only
        if errorlevel 1 (
            echo   ! git pull 失败，可能本地有冲突或修改。请手动处理后重试。
            pause
            exit /b 1
        )
        echo   √ 代码已更新
    ) else (
        echo   ! 当前目录不是 git 仓库，跳过代码更新。
    )
)
echo.

:: ── 2. 升级依赖 ────────────────────────────────
echo 【2/2】升级 Python 依赖...
if not exist "venv\Scripts\python.exe" (
    echo   X venv\ 不存在，请先运行「安装.bat」。
    pause
    exit /b 1
)
set "VENV_PY=%~dp0venv\Scripts\python.exe"
"%VENV_PY%" -m pip install --upgrade pip -q
"%VENV_PY%" -m pip install --upgrade -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
if errorlevel 1 (
    echo   ! 阿里云镜像失败，使用默认源重试...
    "%VENV_PY%" -m pip install --upgrade -r requirements.txt
    if errorlevel 1 (
        echo   X 依赖升级失败。
        pause
        exit /b 1
    )
)
echo   √ 依赖已升级
echo.

echo ================================================
echo   √ 更新完成
echo ================================================
pause
