@echo off
cd /d "%~dp0"
echo 正在启动会议录音转写工具...
echo 启动后浏览器会自动打开，请稍候。
echo （此窗口在使用期间请保持打开，关闭后工具停止运行）
echo.
if not exist "venv\Scripts\python.exe" (
    echo X 未找到虚拟环境，请先双击「安装.bat」完成安装。
    pause
    exit /b 1
)
call "venv\Scripts\activate.bat"
python main.py
pause
