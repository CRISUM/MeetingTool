"""
全局状态管理
- completed_tasks 字典（带线程锁保护）
- 任务持久化（load/save）
- 任务数据访问工具函数
"""

import json
import logging
import threading
from pathlib import Path

import config

logger = logging.getLogger(__name__)

# 线程锁：保护 completed_tasks 的并发读写
_tasks_lock = threading.Lock()

# 全局任务字典：{ 文件显示名: { output_dir, summary, timestamp } }
completed_tasks: dict[str, dict] = {}


def load_tasks() -> None:
    """从磁盘加载任务记录到 completed_tasks（仅在启动时调用一次）"""
    global completed_tasks
    if not config.TASKS_DB_PATH.exists():
        return

    try:
        data = json.loads(config.TASKS_DB_PATH.read_text(encoding="utf-8"))
        valid = {}
        for name, task in data.items():
            output_dir = Path(task["output_dir"])
            if (output_dir / "转写全文.txt").exists():
                valid[name] = task
        with _tasks_lock:
            completed_tasks = valid
        logger.info(f"已加载 {len(completed_tasks)} 个历史任务")
    except Exception as e:
        logger.error(f"加载任务记录失败: {e}")


def save_tasks() -> None:
    """将 completed_tasks 持久化到磁盘（调用前须持有锁或在锁内调用）"""
    serializable = {}
    for name, task in completed_tasks.items():
        serializable[name] = {
            "output_dir": str(task["output_dir"]),
            "summary": task.get("summary", ""),
            "timestamp": task.get("timestamp", ""),
        }
    config.TASKS_DB_PATH.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def upsert_task(name: str, task: dict) -> None:
    """线程安全地新增或更新一个任务记录"""
    with _tasks_lock:
        completed_tasks[name] = task
        save_tasks()


def delete_task_by_name(name: str) -> bool:
    """线程安全地删除一个任务记录，返回是否成功"""
    with _tasks_lock:
        if name not in completed_tasks:
            return False
        del completed_tasks[name]
        save_tasks()
    return True


def get_task_names() -> list[str]:
    """返回当前所有任务名列表（线程安全快照）"""
    with _tasks_lock:
        return list(completed_tasks.keys())


def get_task(name: str) -> dict | None:
    """线程安全地获取单个任务"""
    with _tasks_lock:
        return completed_tasks.get(name)


def get_transcript(task: dict) -> str:
    """读取任务的转写全文（普通版）"""
    path = Path(task["output_dir"]) / "转写全文.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def get_annotated_transcript(task: dict) -> str:
    """读取任务的说话人标注版转写文本，不存在则返回空串"""
    path = Path(task["output_dir"]) / "转写全文_说话人标注.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def has_annotated_transcript(task: dict) -> bool:
    """判断任务是否有说话人标注版"""
    path = Path(task["output_dir"]) / "转写全文_说话人标注.txt"
    return path.exists() and path.stat().st_size > 0


def get_summary(task: dict) -> str:
    """读取任务的会议总结，优先从文件读取"""
    path = Path(task["output_dir"]) / "会议总结.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return task.get("summary", "")


def get_best_transcript(task: dict) -> str:
    """
    返回最优转写文本：有说话人标注版则返回标注版，否则返回普通版。
    用于重新总结时的输入文本。
    """
    annotated = get_annotated_transcript(task)
    return annotated if annotated else get_transcript(task)
