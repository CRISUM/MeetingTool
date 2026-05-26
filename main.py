"""
会议录音转写 + AI总结工具
运行: python3 main.py
预热: python3 main.py --preheat   （仅触发 FunASR 模型下载后退出）
"""

import logging
import sys

from logger import setup_logging
from state import load_tasks
from ui import build_ui, LAUNCH_KWARGS

setup_logging()
logger = logging.getLogger(__name__)


def preheat() -> None:
    """触发 FunASR 模型下载到本地缓存，安装阶段调用，下载完成后立即退出。"""
    from transcriber import get_funasr_model

    logger.info("开始预热 FunASR 模型（首次会下载约 500MB）...")
    get_funasr_model(use_speaker=False)
    logger.info("预热完成")


if __name__ == "__main__":
    if "--preheat" in sys.argv:
        preheat()
        sys.exit(0)

    load_tasks()
    logger.info("启动会议录音转写工具")
    app = build_ui()
    app.launch(**LAUNCH_KWARGS)