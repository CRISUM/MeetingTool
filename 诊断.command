#!/bin/bash
# 会议录音转写工具 · 环境诊断（Mac）
cd "$(dirname "$0")"

# Apple Silicon 环境变量
if [ -f /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

echo "================================================"
echo "  会议录音转写工具 · 环境诊断"
echo "================================================"
echo ""

echo "[系统 Python]"
if command -v python3 &>/dev/null; then
    echo "  ✅ $(python3 --version)  ($(command -v python3))"
else
    echo "  ❌ 未检测到 python3"
fi
echo ""

echo "[ffmpeg]"
if command -v ffmpeg &>/dev/null; then
    echo "  ✅ $(ffmpeg -version 2>&1 | head -n1)"
else
    echo "  ❌ 未检测到 ffmpeg"
fi
echo ""

echo "[Homebrew]"
if command -v brew &>/dev/null; then
    echo "  ✅ $(brew --version | head -n1)"
else
    echo "  ❌ 未安装 brew"
fi
echo ""

echo "[虚拟环境 / 依赖 / PyTorch / 缓存 / 环境变量]"
if [ -x "venv/bin/python3" ]; then
    ./venv/bin/python3 _diagnose.py
else
    echo "  ❌ venv/ 不存在（请先运行「安装.command」）"
fi
echo ""

echo "================================================"
echo "  诊断完成"
echo "================================================"
read -p "按回车键关闭..." _
