"""
日志模块
- 按天分文件存储
- 同时输出到终端和文件
- 自动清理过期日志
- 压制第三方库噪音（终端仅显示本项目日志）
- 不记录敏感会议内容
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import config

# 本项目自己的 logger 前缀，终端只显示这些
_OWN_LOGGER_PREFIXES = (
    "meeting_tool",
    "transcriber",
    "summarizer",
    "diarizer",
    "handlers",
    "state",
    "ui",
    "config",
    "__main__",
)

# 第三方子 logger 压制到 WARNING（避免它们向 root 传播 DEBUG/INFO）
_NOISY_LOGGERS = [
    "funasr",
    "modelscope",
    "asyncio",
    "httpcore",
    "httpx",
    "urllib3",
    "python_multipart",
    "matplotlib",
    "dashscope",
    "gradio",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "fastapi",
]


class _OwnLoggerFilter(logging.Filter):
    """
    终端 handler 过滤器：只放行本项目的 logger。
    第三方通过 root logger 直接调用 logging.warning() 等也会被过滤掉。
    """
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith(_OWN_LOGGER_PREFIXES)


def setup_logging(level: str = None) -> logging.Logger:
    """
    初始化日志系统。

    Args:
        level: 日志级别字符串 (DEBUG/INFO/WARNING/ERROR)，仅影响本项目的终端输出

    Returns:
        root logger
    """
    level = level or config.LOG_LEVEL
    log_level = getattr(logging, level.upper(), logging.INFO)

    today = datetime.now().strftime("%Y-%m-%d")
    log_file = config.LOGS_DIR / f"{today}.log"

    file_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)-20s %(message)s",
        datefmt="%H:%M:%S",
    )
    console_formatter = logging.Formatter(
        "[%(levelname)-8s] %(message)s"
    )

    # 文件 handler：记录所有（含第三方 WARNING+），方便排查
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # 终端 handler：只显示本项目日志
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(_OwnLoggerFilter())

    # root logger 设为 DEBUG，让两个 handler 按自己的规则过滤
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 把已知的第三方子 logger 也压到 WARNING，减少文件日志噪音
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    cleanup_old_logs()

    logger = logging.getLogger("meeting_tool")
    logger.info(f"日志系统初始化完成 | 级别: {level} | 文件: {log_file}")

    return root_logger


def cleanup_old_logs():
    """清理超过保留天数的日志文件"""
    cutoff = datetime.now() - timedelta(days=config.LOG_RETENTION_DAYS)
    for log_file in config.LOGS_DIR.glob("*.log"):
        try:
            file_date = datetime.strptime(log_file.stem, "%Y-%m-%d")
            if file_date < cutoff:
                log_file.unlink()
                logging.getLogger(__name__).debug(f"已清理过期日志: {log_file.name}")
        except (ValueError, OSError):
            pass


def set_log_level(level: str):
    """动态调整本项目终端日志级别（不影响第三方 logger 的压制）"""
    log_level = getattr(logging, level.upper(), logging.INFO)
    config.LOG_LEVEL = level.upper()

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            handler.setLevel(log_level)

    logging.getLogger(__name__).info(f"终端日志级别已调整为: {level}")