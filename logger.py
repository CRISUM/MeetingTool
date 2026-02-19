"""
日志模块
- 按天分文件存储
- 同时输出到终端和文件
- 自动清理过期日志
- 不记录敏感会议内容
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import config


def setup_logging(level: str = None) -> logging.Logger:
    """
    初始化日志系统。

    Args:
        level: 日志级别字符串 (DEBUG/INFO/WARNING/ERROR)

    Returns:
        root logger
    """
    level = level or config.LOG_LEVEL
    log_level = getattr(logging, level.upper(), logging.INFO)

    # 日志文件按天命名
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = config.LOGS_DIR / f"{today}.log"

    # 格式
    file_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)-20s %(message)s",
        datefmt="%H:%M:%S",
    )
    console_formatter = logging.Formatter(
        "[%(levelname)-8s] %(message)s"
    )

    # 文件 handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # 文件始终记录 DEBUG 级别
    file_handler.setFormatter(file_formatter)

    # 终端 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)

    # 配置 root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 避免重复添加 handler（重复调用 setup_logging 时）
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 清理过期日志
    cleanup_old_logs()

    logger = logging.getLogger("meeting_tool")
    logger.info(f"日志系统初始化完成 | 级别: {level} | 文件: {log_file}")

    return root_logger


def cleanup_old_logs():
    """清理超过保留天数的日志文件"""
    cutoff = datetime.now() - timedelta(days=config.LOG_RETENTION_DAYS)

    for log_file in config.LOGS_DIR.glob("*.log"):
        try:
            # 从文件名解析日期
            date_str = log_file.stem  # "2026-02-19"
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                log_file.unlink()
                logging.getLogger(__name__).debug(f"已清理过期日志: {log_file.name}")
        except (ValueError, OSError):
            pass


def set_log_level(level: str):
    """动态调整终端日志级别"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    config.LOG_LEVEL = level.upper()

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            handler.setLevel(log_level)

    logging.getLogger(__name__).info(f"终端日志级别已调整为: {level}")
