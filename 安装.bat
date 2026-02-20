@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: 切换到脚本所在目录（即项目根目录）
cd /d "%~dp0"

echo ================================================
echo   会议录音转写工具 · 安装程序
echo ================================================
echo.

:: ── 1. 检查 Python ───────────────────────────────
echo 【1/4】检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   × 未检测到 Python，请先安装 Python 3.12 或以上版本。
    echo.
    echo   下载地址：https://www.python.org/downloads/
    echo   安装时务必勾选 "Add Python to PATH"
    echo.
    echo   安装完成后，重新双击本脚本继续安装。
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo   √ %PY_VER% 已安装

:: ── 2. 检查 pip ───────────────────────────────────
echo.
echo 【2/4】检查 pip...
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo   × pip 未找到，尝试修复...
    python -m ensurepip --upgrade
)
python -m pip install --upgrade pip -q
echo   √ pip 已就绪

:: ── 3. 检查 ffmpeg ────────────────────────────────
echo.
echo 【3/4】检查 ffmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo   × 未检测到 ffmpeg。
    echo.
    echo   请按以下步骤安装：
    echo   1. 在浏览器打开：https://www.gyan.dev/ffmpeg/builds/
    echo   2. 下载 "ffmpeg-release-essentials.zip"
    echo   3. 解压后将 bin 文件夹路径添加到系统 PATH
    echo.
    echo   或者如果已安装 scoop，可以直接运行：
    echo     scoop install ffmpeg
    echo.
    echo   安装 ffmpeg 后，重新双击本脚本继续。
    pause
    exit /b 1
) else (
    echo   √ ffmpeg 已安装
)

:: ── 4. 安装 Python 依赖 ───────────────────────────
echo.
echo 【4/4】安装 Python 依赖（首次约需 5-10 分钟）...
echo   （正在下载 FunASR、Gradio 等组件，请保持网络畅通）
echo.

:: 检查是否有 NVIDIA 显卡，有则提示安装 GPU 版 PyTorch
nvidia-smi >nul 2>&1
if not errorlevel 1 (
    echo   检测到 NVIDIA 显卡，正在安装 GPU 版 PyTorch（大幅加速转写）...
    echo   （此步骤约需额外 5 分钟，下载约 2GB）
    echo.
    python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    if errorlevel 1 (
        echo   ！GPU 版 PyTorch 安装失败，将使用 CPU 版继续。
    ) else (
        echo   √ GPU 版 PyTorch 安装完成
    )
    echo.
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo × 依赖安装失败，请截图此窗口发给开发者。
    pause
    exit /b 1
)

echo.
echo   √ Python 依赖安装完成

:: ── 创建启动脚本 ──────────────────────────────────
echo.
echo 正在创建启动快捷方式...

(
echo @echo off
echo chcp 65001 ^>nul
echo cd /d "%%~dp0"
echo echo 正在启动会议录音转写工具...
echo echo 启动后浏览器会自动打开，请稍候。
echo echo （此窗口在使用期间请保持打开，关闭后工具停止运行）
echo echo.
echo python main.py
echo pause
) > 启动.bat

echo   √ 启动快捷方式已创建：启动.bat

:: ── 完成 ──────────────────────────────────────────
echo.
echo ================================================
echo   √ 安装完成！
echo.
echo   以后使用时，双击「启动.bat」即可。
echo.
echo   首次运行时工具会自动下载转写模型（约 500MB），
echo   请保持网络畅通，耐心等待。
echo ================================================
echo.
pause
