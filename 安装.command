#!/bin/bash
# 会议录音转写工具 · 一键安装脚本（Mac）
# 双击此文件即可运行

set -e  # 任何命令失败就停止

# 让终端窗口保持打开（双击 .command 文件时默认会关闭）
trap 'echo ""; echo "❌ 安装中途出错，请截图此窗口发给开发者。"; read -p "按回车键关闭..." _' ERR

# 切换到脚本所在目录（即项目根目录）
cd "$(dirname "$0")"

echo "================================================"
echo "  会议录音转写工具 · 安装程序"
echo "================================================"
echo ""

# ── 1. 检查 Homebrew ──────────────────────────────
echo "【1/4】检查 Homebrew..."
if ! command -v brew &>/dev/null; then
    echo "  → 未检测到 Homebrew，正在安装（需要几分钟）..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Apple Silicon Mac 需要把 brew 加入 PATH
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi
    echo "  ✅ Homebrew 安装完成"
else
    echo "  ✅ Homebrew 已安装，跳过"
fi

# ── 2. 检查 Python & ffmpeg ───────────────────────
echo ""
echo "【2/4】检查 Python 和 ffmpeg..."

if ! command -v python3 &>/dev/null || ! python3 -c "import sys; assert sys.version_info >= (3,12)" &>/dev/null 2>&1; then
    echo "  → 正在安装 Python..."
    brew install python
else
    echo "  ✅ Python 已安装（$(python3 --version)）"
fi

if ! command -v ffmpeg &>/dev/null; then
    echo "  → 正在安装 ffmpeg..."
    brew install ffmpeg
else
    echo "  ✅ ffmpeg 已安装"
fi

# ── 3. 安装 Python 依赖 ───────────────────────────
echo ""
echo "【3/4】安装 Python 依赖（首次约需 5–10 分钟）..."
echo "  （正在下载 FunASR、Gradio 等组件，请保持网络畅通）"
echo ""

python3 -m pip install --upgrade pip -q
python3 -m pip install -r requirements.txt

echo ""
echo "  ✅ Python 依赖安装完成"

# ── 4. 创建启动脚本 ───────────────────────────────
echo ""
echo "【4/4】创建启动快捷方式..."

cat > 启动.command << 'LAUNCHER'
#!/bin/bash
cd "$(dirname "$0")"

echo "正在启动会议录音转写工具..."
echo "启动后浏览器会自动打开，请稍候。"
echo "（此窗口在使用期间请保持打开，关闭后工具停止运行）"
echo ""

# Apple Silicon 环境变量
if [ -f /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

python3 main.py
LAUNCHER

chmod +x 启动.command

echo "  ✅ 启动快捷方式已创建：启动.command"

# ── 完成 ──────────────────────────────────────────
echo ""
echo "================================================"
echo "  ✅ 安装完成！"
echo ""
echo "  以后使用时，双击「启动.command」即可。"
echo ""
echo "  首次运行时工具会自动下载转写模型（约 500MB），"
echo "  请保持网络畅通，耐心等待。"
echo "================================================"
echo ""
read -p "按回车键关闭此窗口..." _
