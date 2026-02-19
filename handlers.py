"""
事件处理函数（业务逻辑层）
- 所有 Gradio 事件的处理函数
- 依赖 state.py、transcriber、summarizer
- 返回值统一包含 toast 通知对象供 UI 层渲染
- 不直接操作任何 Gradio 组件
"""

import logging
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import gradio as gr

import config
import state
from summarizer import summarize_single, summarize_merged
from transcriber import transcribe_audio

logger = logging.getLogger(__name__)


# ============================================================
# Toast 通知构造
# ============================================================

def toast_success(msg: str) -> dict:
    return {"type": "success", "msg": msg}

def toast_error(msg: str) -> dict:
    return {"type": "error", "msg": msg}

def toast_warning(msg: str) -> dict:
    return {"type": "warning", "msg": msg}

def toast_info(msg: str) -> dict:
    return {"type": "info", "msg": msg}


# ============================================================
# API Key 检测
# ============================================================

def check_dashscope_key() -> bool:
    return bool(config.DASHSCOPE_API_KEY and config.DASHSCOPE_API_KEY.strip())


def get_feature_status() -> dict:
    """
    返回各功能可用状态。
    目前外部依赖只有 DashScope（总结功能）。
    """
    return {
        "summary": check_dashscope_key(),
    }


# ============================================================
# 转写与总结
# ============================================================

def process_files(
    files,
    enable_speaker: bool,
    enable_summary: bool,
    progress=gr.Progress(),
) -> tuple[str, list[str], list[dict]]:
    """
    批量处理上传的音频文件。

    Returns:
        (状态文本, 更新后的任务名列表, toast列表)
    """
    if not files:
        return "请先上传音频文件", state.get_task_names(), [toast_warning("请先上传音频文件")]

    if enable_summary and not check_dashscope_key():
        return (
            "❌ 启用了总结但未配置 API Key，请在设置中填写 DASHSCOPE_API_KEY",
            state.get_task_names(),
            [toast_error("未配置 API Key，无法生成总结")],
        )

    results = []
    toasts = []
    total_files = len(files)

    if enable_speaker:
        results.append("ℹ️ 已启用说话人区分（cam++），声音相似时效果有限。\n")

    for file_idx, file in enumerate(files):
        file_path = file.name if hasattr(file, "name") else str(file)
        file_display_name = Path(file_path).name

        logger.info(f"开始处理 [{file_idx+1}/{total_files}]: {file_display_name}")
        progress(
            file_idx / total_files,
            desc=f"[{file_idx+1}/{total_files}] 处理: {file_display_name}",
        )

        # --- 转写 ---
        def transcribe_progress(ratio, msg):
            base = file_idx / total_files
            span = 0.7 / total_files
            progress(base + ratio * span, desc=f"[{file_idx+1}/{total_files}] {msg}")

        try:
            transcript, output_dir = transcribe_audio(
                audio_path=file_path,
                enable_speaker=enable_speaker,
                progress_callback=transcribe_progress,
            )
        except Exception as e:
            logger.error(f"转写失败: {file_display_name} - {e}", exc_info=True)
            results.append(f"❌ {file_display_name}: 转写失败 - {e}")
            toasts.append(toast_error(f"{file_display_name} 转写失败"))
            continue

        # --- 总结 ---
        summary = ""
        if enable_summary:
            def summary_progress(ratio, msg):
                base = (file_idx + 0.7) / total_files
                span = 0.3 / total_files
                progress(base + ratio * span, desc=f"[{file_idx+1}/{total_files}] {msg}")

            try:
                summary = summarize_single(transcript, progress_callback=summary_progress)
            except Exception as e:
                summary = f"⚠️ 总结生成失败: {e}"
                logger.error(f"总结失败: {e}", exc_info=True)
                toasts.append(toast_warning(f"{file_display_name} 总结生成失败"))

            (output_dir / "会议总结.md").write_text(summary, encoding="utf-8")

        # --- 记录任务（线程安全） ---
        state.upsert_task(file_display_name, {
            "output_dir": str(output_dir),
            "summary": summary,
            "timestamp": datetime.now().isoformat(),
        })

        status_icon = "✅" if summary else "📝"
        results.append(f"{status_icon} {file_display_name} → {output_dir.name}")
        logger.info(f"任务完成: {file_display_name}")

    progress(1.0, desc="全部完成")

    status = "\n".join(results) + f"\n\n📁 输出目录: {config.OUTPUT_DIR}"
    task_names = state.get_task_names()

    if total_files > 0 and not any("❌" in r for r in results):
        toasts.append(toast_success(f"✅ {total_files} 个文件处理完成"))
    elif any("❌" in r for r in results):
        toasts.append(toast_warning("部分文件处理失败，请查看状态"))

    return status, task_names, toasts


def rerun_summary(
    task_name: str,
    transcript_text: str,
    progress=gr.Progress(),
) -> tuple[str, str, list[dict]]:
    """
    用编辑后的转写文本重新生成总结。

    Returns:
        (总结文本, 总结Markdown, toast列表)
    """
    if not transcript_text.strip():
        return "", "", [toast_warning("转写文本为空")]

    if not check_dashscope_key():
        return "", "", [toast_error("未配置 API Key，无法生成总结")]

    def prog(ratio, msg):
        progress(ratio, desc=msg)

    try:
        summary = summarize_single(transcript_text, progress_callback=prog)
    except Exception as e:
        logger.error(f"重新总结失败: {e}", exc_info=True)
        return "", "", [toast_error(f"总结生成失败: {e}")]

    # 回写文件并更新任务记录
    task = state.get_task(task_name)
    if task:
        summary_path = Path(task["output_dir"]) / "会议总结.md"
        summary_path.write_text(summary, encoding="utf-8")
        updated_task = dict(task)
        updated_task["summary"] = summary
        state.upsert_task(task_name, updated_task)

    return summary, summary, [toast_success("总结已更新")]


# ============================================================
# 合并总结
# ============================================================

def merge_summarize(
    selected_files: list[str],
    progress=gr.Progress(),
) -> tuple[str, str, list[dict]]:
    """
    合并多个文件的转写文本生成总结。

    Returns:
        (状态文本, 合并总结Markdown, toast列表)
    """
    if not selected_files:
        return "请先选择要合并的文件", "", [toast_warning("请先选择要合并的文件")]

    if not check_dashscope_key():
        return "❌ 未配置 API Key", "", [toast_error("未配置 API Key，无法生成总结")]

    transcripts = {}
    for fname in selected_files:
        task = state.get_task(fname)
        if task:
            text = state.get_best_transcript(task)
            if text:
                transcripts[fname] = text

    if not transcripts:
        return "所选文件没有转写结果", "", [toast_warning("所选文件没有转写结果")]

    def prog(ratio, msg):
        progress(ratio, desc=msg)

    try:
        merged_summary = summarize_merged(transcripts, progress_callback=prog)
    except Exception as e:
        logger.error(f"合并总结失败: {e}", exc_info=True)
        return f"合并总结失败: {e}", "", [toast_error(f"合并总结失败: {e}")]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    merged_path = config.OUTPUT_DIR / f"合并总结_{timestamp}.md"
    merged_path.write_text(merged_summary, encoding="utf-8")

    return f"📄 已保存: {merged_path.name}", merged_summary, [toast_success("合并总结生成完成")]


# ============================================================
# 任务管理
# ============================================================

def build_task_table() -> str:
    """构建任务列表 Markdown 表格"""
    names = state.get_task_names()
    if not names:
        return "暂无任务记录"

    rows = [
        "| 序号 | 文件名 | 转写 | 说话人 | 总结 | 时间 | 输出目录 |",
        "|------|--------|------|--------|------|------|----------|",
    ]
    for idx, name in enumerate(names, 1):
        task = state.get_task(name)
        if not task:
            continue
        has_transcript = "✅" if state.get_transcript(task) else "❌"
        has_annotated = "✅" if state.has_annotated_transcript(task) else "—"
        summary_text = state.get_summary(task)
        has_summary = "✅" if summary_text and not summary_text.startswith("⚠️") else "❌"
        ts = task.get("timestamp", "")
        try:
            time_str = datetime.fromisoformat(ts).strftime("%m-%d %H:%M") if ts else "未知"
        except Exception:
            time_str = ts[:16] if ts else "未知"
        output_dir = Path(task["output_dir"]).name
        rows.append(
            f"| {idx} | {name} | {has_transcript} | {has_annotated} | {has_summary} | {time_str} | `{output_dir}` |"
        )
    return "\n".join(rows)


def load_task_detail(
    task_name: str,
) -> tuple[str, bool, str, str, bool]:
    """
    加载任务详情。

    Returns:
        (转写文本, 说话人版按钮是否可用, 总结文本, 总结Markdown, 当前显示是否为说话人版)
    """
    if not task_name:
        return "", False, "", "", False

    task = state.get_task(task_name)
    if not task:
        return "", False, "", "", False

    transcript = state.get_transcript(task)
    has_annotated = state.has_annotated_transcript(task)
    summary = state.get_summary(task)

    # 默认显示最优版（有标注则显示标注）
    display_transcript = state.get_annotated_transcript(task) if has_annotated else transcript
    is_annotated_view = has_annotated

    return display_transcript, has_annotated, summary, summary, is_annotated_view


def toggle_transcript_view(
    task_name: str,
    is_annotated_view: bool,
) -> tuple[str, bool]:
    """
    切换普通版/说话人版转写文本。

    Returns:
        (转写文本, 切换后的视图状态)
    """
    if not task_name:
        return "", False

    task = state.get_task(task_name)
    if not task:
        return "", False

    # 切换
    new_is_annotated = not is_annotated_view
    if new_is_annotated and state.has_annotated_transcript(task):
        text = state.get_annotated_transcript(task)
    else:
        text = state.get_transcript(task)
        new_is_annotated = False

    return text, new_is_annotated


def delete_task(task_name: str) -> tuple[str, list[str], list[dict]]:
    """
    删除任务记录（不删除文件）。

    Returns:
        (任务名列表, toast列表)
    """
    if not task_name:
        return state.get_task_names(), [toast_warning("请先选择一个任务")]

    success = state.delete_task_by_name(task_name)
    if success:
        logger.info(f"已删除任务记录: {task_name}")
        return state.get_task_names(), [toast_success(f"已删除记录: {task_name}")]
    else:
        return state.get_task_names(), [toast_error("删除失败：任务不存在")]


def open_output_dir(
    task_name: str,
    request: gr.Request,
) -> list[dict]:
    """
    打开任务输出目录（仅本机访问时生效）。

    Returns:
        toast列表
    """
    # 判断是否本机访问
    client_host = request.client.host if request and request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        return [toast_warning("打开目录功能仅在本机访问时可用")]

    if not task_name:
        return [toast_warning("请先选择一个任务")]

    task = state.get_task(task_name)
    if not task:
        return [toast_error("任务不存在")]

    output_dir = Path(task["output_dir"])
    if not output_dir.exists():
        return [toast_error(f"目录不存在: {output_dir}")]

    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(str(output_dir))
        elif system == "Darwin":
            subprocess.Popen(["open", str(output_dir)])
        else:
            subprocess.Popen(["xdg-open", str(output_dir)])
        return [toast_success("已打开输出目录")]
    except Exception as e:
        logger.error(f"打开目录失败: {e}", exc_info=True)
        return [toast_error(f"打开目录失败: {e}")]


# ============================================================
# 设置
# ============================================================

def save_api_key(key: str) -> tuple[bool, list[dict]]:
    """
    保存 DashScope API Key。

    Returns:
        (key是否有效, toast列表)
    """
    config.DASHSCOPE_API_KEY = key.strip()
    is_valid = bool(config.DASHSCOPE_API_KEY)
    if is_valid:
        return True, [toast_success("API Key 已保存（本次会话有效）")]
    else:
        return False, [toast_warning("API Key 为空，总结功能不可用")]


def save_prompt_handler(key: str, content: str) -> list[dict]:
    ok, msg = config.save_prompt(key, content)
    if ok:
        return [toast_success(f"Prompt 已保存：{msg}")]
    else:
        return [toast_error(f"保存失败：{msg}")]


def restore_defaults_handler() -> tuple[str, str, str, list[dict]]:
    for key, content in config.DEFAULT_PROMPTS.items():
        config.save_prompt(key, content)
    logger.info("已恢复所有 Prompt 为默认值")
    return (
        config.load_prompt("single_summary"),
        config.load_prompt("chunk_extract"),
        config.load_prompt("merge_summary"),
        [toast_success("已恢复所有 Prompt 为默认值")],
    )


def update_log_level_handler(level: str) -> list[dict]:
    from logger import set_log_level
    set_log_level(level)
    return [toast_success(f"日志级别已设为 {level}")]
