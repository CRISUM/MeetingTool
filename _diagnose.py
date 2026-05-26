"""环境诊断辅助脚本，由 诊断.bat / 诊断.command 在 venv 内调用。"""

import importlib.metadata as md
import os
import shutil
import sys
from pathlib import Path


def main() -> None:
    print(f"  √ venv Python: {sys.version.split()[0]}  ({sys.executable})")
    print()

    print("  依赖版本:")
    for pkg in ("funasr", "modelscope", "gradio", "openai", "pydub", "torch", "torchaudio"):
        try:
            print(f"    {pkg:12s} {md.version(pkg)}")
        except md.PackageNotFoundError:
            print(f"    {pkg:12s} (未安装)")
    print()

    print("  PyTorch / CUDA:")
    try:
        import torch
        print(f"    torch={torch.__version__}")
        print(f"    CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"    CUDA device:    {torch.cuda.get_device_name(0)}")
    except Exception as e:
        print(f"    ! torch 导入失败: {e}")
    print()

    cache_dir = Path(os.environ.get("MODELSCOPE_CACHE") or Path.home() / ".cache" / "modelscope")
    print(f"  模型缓存目录: {cache_dir}")
    if cache_dir.exists():
        total = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
        print(f"  已下载大小:   {total / (1024 * 1024):.1f} MB")
    else:
        print("  ~ 缓存目录尚未创建（首次启动会下载约 500MB）")
    print()

    usage = shutil.disk_usage(Path.cwd())
    print(f"  当前盘剩余:   {usage.free / (1024 ** 3):.1f} GB / 总 {usage.total / (1024 ** 3):.1f} GB")
    print()

    print("  环境变量:")
    key = os.environ.get("DASHSCOPE_API_KEY")
    if key:
        print(f"    √ DASHSCOPE_API_KEY 已设置 (前缀={key[:4]}***, 长度={len(key)})")
    else:
        print("    ~ DASHSCOPE_API_KEY 未设置 (可在 UI 设置页面临时填入)")
    ms_cache = os.environ.get("MODELSCOPE_CACHE")
    print(f"    MODELSCOPE_CACHE = {ms_cache or '(未设置，使用默认)'}")


if __name__ == "__main__":
    main()
