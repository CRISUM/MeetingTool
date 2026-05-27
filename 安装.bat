@echo off
setlocal enabledelayedexpansion

:: 切换到脚本所在目录（即项目根目录）
cd /d "%~dp0"

echo ================================================
echo   会议录音转写工具 · 安装程序
echo ================================================
echo.

:: ── 1. 检查 Python ───────────────────────────────
echo 【1/5】检查 Python...
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

:: ── 2. 检查 ffmpeg ────────────────────────────────
echo.
echo 【2/5】检查 ffmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo   × 未检测到 ffmpeg。
    echo.

    :: 优先尝试 winget 自动安装
    winget --version >nul 2>&1
    if not errorlevel 1 (
        echo   检测到 winget，可自动安装 ffmpeg（Gyan.FFmpeg）。
        set /p FFMPEG_CONFIRM=  是否现在自动安装 ffmpeg？[Y/n]:
        if /i not "!FFMPEG_CONFIRM!"=="n" (
            echo   → 正在通过 winget 安装 ffmpeg...
            winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
            if errorlevel 1 (
                echo   ! winget 安装失败，请按下方说明手动安装。
            ) else (
                echo.
                echo   √ ffmpeg 安装命令已执行。
                echo.
                echo   ? 当前命令行窗口仍读不到新加的 PATH，需要：
                echo     关闭本窗口 → 重新双击「安装.bat」继续。
                echo.
                pause
                exit /b 0
            )
        )
    )

    echo.
    echo   请按以下步骤手动安装：
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

:: ── 3. 创建虚拟环境 ───────────────────────────────
echo.
echo 【3/5】准备 Python 虚拟环境...
if not exist "venv\Scripts\python.exe" (
    echo   → 创建虚拟环境 venv\ ...
    python -m venv venv
    if errorlevel 1 (
        echo   × 虚拟环境创建失败，请确认 Python 安装完整。
        pause
        exit /b 1
    )
    echo   √ 虚拟环境已创建
) else (
    echo   √ 虚拟环境已存在，跳过创建
)

:: 之后所有 pip / python 都走 venv
set "VENV_PY=%~dp0venv\Scripts\python.exe"
"%VENV_PY%" -m pip install --upgrade pip -q

:: ── 4. 安装 Python 依赖 ───────────────────────────
echo.
echo 【4/5】安装 Python 依赖（首次约需 5-10 分钟）...
echo   （正在下载 FunASR、Gradio 等组件，请保持网络畅通）
echo.

:: 检查是否有 NVIDIA 显卡，有则安装 GPU 版 PyTorch，否则装 CPU 版
set "TORCH_OK=0"
nvidia-smi >nul 2>&1
if not errorlevel 1 (
    echo   检测到 NVIDIA 显卡，正在安装 GPU 版 PyTorch（大幅加速转写）...
    echo   （此步骤约需额外 5 分钟，下载约 2GB）
    echo.
    "%VENV_PY%" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
    if errorlevel 1 (
        echo   ! GPU 版 PyTorch 安装失败，回退到 CPU 版。
    ) else (
        echo   √ GPU 版 PyTorch 安装完成
        set "TORCH_OK=1"
    )
    echo.
)
if "%TORCH_OK%"=="0" (
    echo   → 安装 CPU 版 PyTorch...
    "%VENV_PY%" -m pip install torch torchaudio -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
    if errorlevel 1 (
        echo   ! 阿里云镜像失败，使用默认源重试...
        "%VENV_PY%" -m pip install torch torchaudio
        if errorlevel 1 (
            echo × PyTorch 安装失败，请截图此窗口发给开发者。
            pause
            exit /b 1
        )
    )
    echo   √ CPU 版 PyTorch 安装完成
)

:: 其他依赖优先走阿里云镜像
"%VENV_PY%" -m pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
if errorlevel 1 (
    echo   ! 阿里云镜像失败，使用默认源重试...
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo × 依赖安装失败，请截图此窗口发给开发者。
        pause
        exit /b 1
    )
)

echo.
echo   √ Python 依赖安装完成

:: ── 预热模型（可选）─────────────────────────────
echo.
echo 是否现在预下载 FunASR 转写模型？（约 500MB，首次启动可省去等待）
set /p PREHEAT_CONFIRM=  现在预下载？[Y/n]:
if /i not "%PREHEAT_CONFIRM%"=="n" (
    echo   → 正在预下载模型，请保持网络畅通...
    "%VENV_PY%" main.py --preheat
    if errorlevel 1 (
        echo   ! 模型预下载失败，可忽略——首次启动时会自动重试。
    ) else (
        echo   √ 模型预下载完成
    )
)

:: ── 5. 创建启动脚本 ───────────────────────────────
echo.
echo 【5/5】创建启动快捷方式...

if not exist "_launcher_template.bat" (
    echo   X 未找到 _launcher_template.bat，无法生成启动脚本。
    pause
    exit /b 1
)
copy /Y "_launcher_template.bat" "启动.bat" >nul
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
