"""
全局配置
"""

import os
from pathlib import Path

# 脚本所在目录，所有数据都存在这下面
BASE_DIR = Path(__file__).parent.resolve()

# ============================================================
# API 配置
# ============================================================

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
QWEN_MODEL = "qwen-plus"

# ============================================================
# FunASR 配置
# ============================================================

FUNASR_MODEL = "paraformer-zh"
FUNASR_VAD_MODEL = "fsmn-vad"
FUNASR_PUNC_MODEL = "ct-punc"
FUNASR_SPK_MODEL = "cam++"
CHUNK_DURATION_SECONDS = 30 * 60   # FunASR 内置 VAD，chunk 可以更长

# ============================================================
# 目录配置
# ============================================================

INPUT_DIR = BASE_DIR / "data" / "input"
TEMP_DIR = BASE_DIR / "data" / "temp"
OUTPUT_DIR = BASE_DIR / "data" / "output"
TASKS_DB_PATH = BASE_DIR / "data" / "tasks.json"
PROMPTS_DIR = BASE_DIR / "data" / "prompts"
LOGS_DIR = BASE_DIR / "data" / "logs"

for d in [INPUT_DIR, TEMP_DIR, OUTPUT_DIR, PROMPTS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================================
# 日志配置
# ============================================================

LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_RETENTION_DAYS = 30

# ============================================================
# Prompt 文件管理
# ============================================================

PROMPT_FILES = {
    "single_summary": PROMPTS_DIR / "single_summary.txt",
    "chunk_extract": PROMPTS_DIR / "chunk_extract.txt",
    "merge_summary": PROMPTS_DIR / "merge_summary.txt",
}

# 默认 prompt（首次运行时写入文件）
DEFAULT_PROMPTS = {
    "single_summary": """你是一个专业的会议记录助手。请根据以下会议转写文本，生成一份结构化的会议纪要。

要求：
1. 会议主题/背景概述
2. 关键讨论要点（按议题分类）
3. 各方立场和观点（如能识别不同发言人）
4. 达成的共识或决议
5. 待办事项和行动项（如有）
6. 未解决的分歧或待确认事项（如有）

请用中文输出，保持客观准确，不要添加转写文本中没有的信息。

---
会议转写文本：

{transcript}""",

    "chunk_extract": """请提取以下会议文本片段的关键要点，保留重要细节、数据和决策内容：

{chunk}""",

    "merge_summary": """你是一个专业的会议记录助手。以下是多段会议录音的要点摘要，它们属于同一个会议/主题。
请合并这些内容，生成一份完整的结构化会议纪要。

要求：
1. 会议主题/背景概述
2. 关键讨论要点（按议题分类）
3. 各方立场和观点（如能识别不同发言人）
4. 达成的共识或决议
5. 待办事项和行动项（如有）
6. 未解决的分歧或待确认事项（如有）

去除重复内容，按逻辑顺序组织，保持客观准确。

---
各段要点：

{summaries}""",
}

# prompt 中必须包含的占位符
PROMPT_REQUIRED_PLACEHOLDERS = {
    "single_summary": ["{transcript}"],
    "chunk_extract": ["{chunk}"],
    "merge_summary": ["{summaries}"],
}


def init_prompt_files():
    """首次运行时用默认 prompt 创建文件"""
    for key, path in PROMPT_FILES.items():
        if not path.exists():
            path.write_text(DEFAULT_PROMPTS[key], encoding="utf-8")


def load_prompt(key: str) -> str:
    """
    从文件读取 prompt，带占位符校验。
    缺少必要占位符时回退到默认值并警告。
    """
    import logging
    logger = logging.getLogger(__name__)

    path = PROMPT_FILES.get(key)
    if not path or not path.exists():
        logger.warning(f"Prompt 文件不存在: {key}，使用默认值")
        return DEFAULT_PROMPTS.get(key, "")

    content = path.read_text(encoding="utf-8")

    # 校验占位符
    required = PROMPT_REQUIRED_PLACEHOLDERS.get(key, [])
    missing = [p for p in required if p not in content]
    if missing:
        logger.warning(
            f"Prompt '{key}' 缺少必要占位符 {missing}，回退到默认值"
        )
        return DEFAULT_PROMPTS.get(key, "")

    return content


def save_prompt(key: str, content: str) -> tuple[bool, str]:
    """保存 prompt 到文件，返回 (成功与否, 消息)"""
    required = PROMPT_REQUIRED_PLACEHOLDERS.get(key, [])
    missing = [p for p in required if p not in content]
    if missing:
        return False, f"缺少必要占位符: {', '.join(missing)}"

    path = PROMPT_FILES.get(key)
    if not path:
        return False, f"未知的 prompt 类型: {key}"

    path.write_text(content, encoding="utf-8")
    return True, "保存成功"


# 启动时初始化 prompt 文件
init_prompt_files()
