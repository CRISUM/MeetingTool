#!/bin/bash
# 会议录音转写工具 · 更新（Mac）
set -e
trap 'echo ""; echo "❌ 更新出错。"; read -p "按回车键关闭..." _' ERR

cd "$(dirname "$0")"

if [ -f /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

echo "================================================"
echo "  会议录音转写工具 · 更新"
echo "================================================"
echo ""

# ── 1. git pull ────────────────────────────────
echo "【1/2】拉取最新代码..."
if command -v git &>/dev/null && [ -d .git ]; then
    git pull --ff-only
    echo "  ✅ 代码已更新"
else
    echo "  ⚠️ 跳过（不是 git 仓库或未安装 git）"
fi
echo ""

# ── 2. 升级依赖 ────────────────────────────────
echo "【2/2】升级 Python 依赖..."
if [ ! -x "venv/bin/python3" ]; then
    echo "  ❌ venv/ 不存在，请先运行「安装.command」"
    read -p "按回车键关闭..." _
    exit 1
fi

./venv/bin/python3 -m pip install --upgrade pip -q

if ./venv/bin/python3 -m pip install --upgrade -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com; then
    echo "  ✅ 依赖已升级"
else
    echo "  ⚠️ 阿里云镜像失败，使用默认源重试..."
    ./venv/bin/python3 -m pip install --upgrade -r requirements.txt
    echo "  ✅ 依赖已升级"
fi
echo ""

echo "================================================"
echo "  ✅ 更新完成"
echo "================================================"
read -p "按回车键关闭..." _
