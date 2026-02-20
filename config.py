"""
全局配置
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

# ============================================================
# API 配置
# ============================================================

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
QWEN_MODEL = "qwen3.5-plus"

# ============================================================
# FunASR 配置
# ============================================================

FUNASR_MODEL = "paraformer-zh"
FUNASR_VAD_MODEL = "fsmn-vad"
FUNASR_PUNC_MODEL = "ct-punc"
FUNASR_SPK_MODEL = "cam++"
CHUNK_DURATION_SECONDS = 30 * 60

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

LOG_LEVEL = "INFO"
LOG_RETENTION_DAYS = 30

# ============================================================
# Prompt 文件管理
# ============================================================

PROMPT_FILES = {
    "single_summary": PROMPTS_DIR / "single_summary.txt",
    "chunk_extract": PROMPTS_DIR / "chunk_extract.txt",
    "merge_summary": PROMPTS_DIR / "merge_summary.txt",
}

DEFAULT_PROMPTS = {
    "single_summary": """\
你是一个专业的会议记录助手。请根据以下会议转写文本，生成一份结构化的会议纪要。

**输出格式要求（严格遵守）：**
- 使用 `# 会议纪要` 作为文档唯一的一级标题
- 使用 `## 一、xxx` 格式作为二级标题（用中文数字编号）
- 各章节内的要点使用 `- ` 开头的列表项
- 子要点使用 `  - `（两个空格缩进）
- 重要术语或决议可用 `**加粗**` 标注
- 不使用三级及以下标题，不使用表格
- 章节之间空一行

必须包含以下章节，无相关内容时写"无"：

# 会议纪要

## 一、会议概述

## 二、关键讨论要点

## 三、各方立场与观点

## 四、达成的共识或决议

## 五、待办事项与行动项

## 六、待确认事项

---
请用中文输出，保持客观准确，不要添加转写文本中没有的信息。

会议转写文本：

{transcript}""",

    "chunk_extract": """\
请提取以下会议文本片段的关键要点，保留重要细节、数据和决策内容。
输出为简洁的要点列表，每条以 `- ` 开头，不需要标题和格式。

{chunk}""",

    "merge_summary": """\
你是一个专业的会议记录助手。以下是多段会议录音的要点摘要，属于同一个会议/主题。
请合并生成一份完整的结构化会议纪要。

**输出格式要求（严格遵守）：**
- 使用 `# 会议纪要` 作为文档唯一的一级标题
- 使用 `## 一、xxx` 格式作为二级标题（用中文数字编号）
- 各章节内的要点使用 `- ` 开头的列表项
- 子要点使用 `  - `（两个空格缩进）
- 重要术语或决议可用 `**加粗**` 标注
- 不使用三级及以下标题，不使用表格
- 章节之间空一行

必须包含以下章节，无相关内容时写"无"：

# 会议纪要

## 一、会议概述

## 二、关键讨论要点

## 三、各方立场与观点

## 四、达成的共识或决议

## 五、待办事项与行动项

## 六、待确认事项

---
去除重复内容，按逻辑顺序组织，保持客观准确。

各段要点：

{summaries}""",
}

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
    import logging
    logger = logging.getLogger(__name__)

    path = PROMPT_FILES.get(key)
    if not path or not path.exists():
        logger.warning(f"Prompt 文件不存在: {key}，使用默认值")
        return DEFAULT_PROMPTS.get(key, "")

    content = path.read_text(encoding="utf-8")
    required = PROMPT_REQUIRED_PLACEHOLDERS.get(key, [])
    missing = [p for p in required if p not in content]
    if missing:
        logger.warning(f"Prompt '{key}' 缺少必要占位符 {missing}，回退到默认值")
        return DEFAULT_PROMPTS.get(key, "")

    return content


def save_prompt(key: str, content: str) -> tuple[bool, str]:
    required = PROMPT_REQUIRED_PLACEHOLDERS.get(key, [])
    missing = [p for p in required if p not in content]
    if missing:
        return False, f"缺少必要占位符: {', '.join(missing)}"

    path = PROMPT_FILES.get(key)
    if not path:
        return False, f"未知的 prompt 类型: {key}"

    path.write_text(content, encoding="utf-8")
    return True, "保存成功"


init_prompt_files()
