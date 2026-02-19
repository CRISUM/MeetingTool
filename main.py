"""
会议录音转写 + AI总结工具
运行: python3 main.py
"""

import logging

from logger import setup_logging
from state import load_tasks
from ui import build_ui, LAUNCH_KWARGS

setup_logging()
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    load_tasks()
    logger.info("启动会议录音转写工具")
    app = build_ui()
    app.launch(**LAUNCH_KWARGS)