"""
会议录音转写 + AI总结工具 — Gradio 图形界面
运行: python3 main.py
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import gradio as gr

import config
from logger import setup_logging, set_log_level
from transcriber import transcribe_audio
from summarizer import summarize_single, summarize_merged
from diarizer import (
    check_diarization_available,
    diarize_audio,
    align_transcript_with_speakers,
)

# 初始化日志
setup_logging()
logger = logging.getLogger(__name__)


# ============================================================
# 任务持久化
# ============================================================

def load_tasks() -> dict[str, dict]:
    if config.TASKS_DB_PATH.exists():
        try:
            data = json.loads(config.TASKS_DB_PATH.read_text(encoding="utf-8"))
            valid = {}
            for name, task in data.items():
                output_dir = Path(task["output_dir"])
                transcript_path = output_dir / "转写全文.txt"
                if transcript_path.exists():
                    valid[name] = task
            return valid
        except Exception:
            return {}
    return {}


def save_tasks(tasks: dict[str, dict]):
    serializable = {}
    for name, task in tasks.items():
        serializable[name] = {
            "output_dir": str(task["output_dir"]),
            "summary": task.get("summary", ""),
            "timestamp": task.get("timestamp", ""),
        }
    config.TASKS_DB_PATH.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_transcript(task: dict) -> str:
    transcript_path = Path(task["output_dir"]) / "转写全文.txt"
    if transcript_path.exists():
        return transcript_path.read_text(encoding="utf-8")
    return ""


def get_summary(task: dict) -> str:
    summary_path = Path(task["output_dir"]) / "会议总结.md"
    if summary_path.exists():
        return summary_path.read_text(encoding="utf-8")
    return task.get("summary", "")


def check_api_key() -> bool:
    return bool(config.DASHSCOPE_API_KEY and config.DASHSCOPE_API_KEY.strip())


completed_tasks: dict[str, dict] = load_tasks()
logger.info(f"已加载 {len(completed_tasks)} 个历史任务")


# ============================================================
# 核心处理逻辑
# ============================================================

def process_files(
    files, model_name, enable_diarization, diarization_fallback,
    progress=gr.Progress(),
):
    """处理上传的音频文件（批量）"""
    if not files:
        return "请先上传音频文件", "", ""

    results = []
    total_files = len(files)
    has_api = check_api_key()

    if not has_api:
        results.append("⚠️ 未检测到 API Key，将只进行转写，不生成总结。\n")
        logger.warning("未检测到 API Key，跳过总结")

    # 检查说话人区分可用性
    if enable_diarization:
        diar_ok, diar_msg = check_diarization_available()
        if not diar_ok:
            msg = f"⚠️ 说话人区分不可用: {diar_msg}"
            results.append(msg)
            logger.warning(msg)
            if diarization_fallback == "停止处理":
                return msg + "\n\n已停止处理。", "", ""
            enable_diarization = False

    for file_idx, file in enumerate(files):
        file_path = file.name if hasattr(file, "name") else str(file)
        file_display_name = Path(file_path).name

        logger.info(f"开始处理 [{file_idx+1}/{total_files}]: {file_display_name}")

        progress(
            file_idx / total_files,
            desc=f"[{file_idx+1}/{total_files}] 处理: {file_display_name}",
        )

        # --- 说话人区分（如果启用） ---
        diarization_segments = None
        task_name = None

        if enable_diarization:
            def diar_progress(ratio, msg):
                overall = (file_idx + ratio * 0.3) / total_files
                progress(overall, desc=f"[{file_idx+1}/{total_files}] {msg}")

            try:
                # 生成 task_name 供缓存使用
                file_stem = Path(file_path).stem
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                task_name = f"{file_stem}_{timestamp}"

                diarization_segments = diarize_audio(
                    audio_path=file_path,
                    task_name=task_name,
                    progress_callback=diar_progress,
                )
                logger.info(
                    f"说话人区分成功: {len(diarization_segments)} 个片段"
                )
            except Exception as e:
                error_msg = f"说话人区分失败: {e}"
                logger.error(error_msg, exc_info=True)

                if diarization_fallback == "停止处理":
                    results.append(f"❌ {file_display_name}: {error_msg}")
                    results.append("已停止处理（用户设置：说话人区分失败时停止）")
                    return "\n".join(results), "", ""
                else:
                    results.append(
                        f"⚠️ {file_display_name}: {error_msg}，切换为普通转写"
                    )
                    diarization_segments = None

        # --- 转写 ---
        def transcribe_progress(ratio, msg):
            if enable_diarization and diarization_segments is not None:
                overall = (file_idx + 0.3 + ratio * 0.4) / total_files
            else:
                overall = (file_idx + ratio * 0.7) / total_files
            progress(overall, desc=f"[{file_idx+1}/{total_files}] {msg}")

        try:
            transcript, output_dir = transcribe_audio(
                audio_path=file_path,
                model_name=model_name,
                progress_callback=transcribe_progress,
            )
        except Exception as e:
            logger.error(f"转写失败: {file_display_name} - {e}", exc_info=True)
            results.append(f"❌ {file_display_name}: 转写失败 - {e}")
            continue

        # --- 说话人对齐 ---
        if diarization_segments is not None:
            try:
                segments_path = output_dir / "segments.json"
                if segments_path.exists():
                    whisper_segments = json.loads(
                        segments_path.read_text(encoding="utf-8")
                    )
                    annotated_text = align_transcript_with_speakers(
                        whisper_segments, diarization_segments
                    )
                    # 保存带标注版本
                    (output_dir / "转写全文_说话人标注.txt").write_text(
                        annotated_text, encoding="utf-8"
                    )
                    # 总结用带标注的文本
                    transcript = annotated_text
                    logger.info("说话人对齐完成")
                else:
                    logger.warning("未找到 segments.json，跳过说话人对齐")
            except Exception as e:
                logger.error(f"说话人对齐失败: {e}", exc_info=True)

        # --- 总结（仅在有 API Key 时执行） ---
        summary = ""
        if has_api:
            def summary_progress(ratio, msg):
                if enable_diarization and diarization_segments is not None:
                    overall = (file_idx + 0.7 + ratio * 0.3) / total_files
                else:
                    overall = (file_idx + 0.7 + ratio * 0.3) / total_files
                progress(overall, desc=f"[{file_idx+1}/{total_files}] {msg}")

            try:
                summary = summarize_single(
                    transcript, progress_callback=summary_progress
                )
            except Exception as e:
                summary = f"⚠️ 总结生成失败: {e}"
                logger.error(f"总结失败: {e}", exc_info=True)

            summary_path = output_dir / "会议总结.md"
            summary_path.write_text(summary, encoding="utf-8")

        # 记录任务
        display_name = file_display_name
        completed_tasks[display_name] = {
            "output_dir": str(output_dir),
            "summary": summary,
            "timestamp": datetime.now().isoformat(),
        }
        save_tasks(completed_tasks)

        status_icon = "✅" if summary else "📝"
        results.append(f"{status_icon} {display_name} → {output_dir}")
        logger.info(f"任务完成: {display_name}")

    progress(1.0, desc="全部完成")

    # 返回最后一个文件的结果作为预览
    last_task = list(completed_tasks.values())[-1] if completed_tasks else None
    if last_task:
        transcript_text = get_transcript(last_task)
        transcript_preview = (
            transcript_text[:3000] + "..."
            if len(transcript_text) > 3000
            else transcript_text
        )
        summary_preview = last_task.get("summary", "（未生成总结）")
    else:
        transcript_preview = ""
        summary_preview = ""

    status = "\n".join(results) + f"\n\n📁 输出目录: {config.OUTPUT_DIR}"
    return status, transcript_preview, summary_preview


def merge_summarize(selected_files, progress=gr.Progress()):
    if not selected_files:
        return "请先选择要合并的文件", ""

    if not check_api_key():
        return "❌ 未检测到 API Key，无法生成合并总结。", ""

    transcripts = {}
    for fname in selected_files:
        if fname in completed_tasks:
            transcript = get_transcript(completed_tasks[fname])
            if transcript:
                transcripts[fname] = transcript

    if not transcripts:
        return "所选文件没有转写结果", ""

    def merge_progress(ratio, msg):
        progress(ratio, desc=msg)

    try:
        merged_summary = summarize_merged(
            transcripts, progress_callback=merge_progress
        )
    except Exception as e:
        logger.error(f"合并总结失败: {e}", exc_info=True)
        return f"合并总结失败: {e}", ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    merged_path = config.OUTPUT_DIR / f"合并总结_{timestamp}.md"
    merged_path.write_text(merged_summary, encoding="utf-8")

    return f"📄 合并总结已保存: {merged_path}", merged_summary


def rerun_summary(transcript_text, progress=gr.Progress()):
    if not transcript_text.strip():
        return "转写文本为空"
    if not check_api_key():
        return "❌ 未检测到 API Key，无法生成总结。"

    def summary_progress(ratio, msg):
        progress(ratio, desc=msg)

    try:
        return summarize_single(
            transcript_text, progress_callback=summary_progress
        )
    except Exception as e:
        logger.error(f"重新总结失败: {e}", exc_info=True)
        return f"总结生成失败: {e}"


# ============================================================
# 任务管理
# ============================================================

def build_task_table() -> str:
    if not completed_tasks:
        return "暂无任务记录"

    rows = [
        "| 序号 | 文件名 | 转写 | 总结 | 更新时间 | 输出目录 |",
        "|------|--------|------|------|----------|----------|",
    ]
    for idx, (name, task) in enumerate(completed_tasks.items(), 1):
        has_transcript = "✅" if get_transcript(task) else "❌"
        summary_text = get_summary(task)
        has_summary = (
            "✅"
            if summary_text and not summary_text.startswith("⚠️")
            else "❌"
        )
        ts = task.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                time_str = ts[:16]
        else:
            time_str = "未知"
        output_dir = Path(task["output_dir"]).name
        rows.append(
            f"| {idx} | {name} | {has_transcript} | {has_summary} | {time_str} | `{output_dir}` |"
        )
    return "\n".join(rows)


def view_task_detail(selected_file):
    if not selected_file or selected_file not in completed_tasks:
        return "请选择一个文件", ""
    task = completed_tasks[selected_file]
    transcript = get_transcript(task)
    summary = get_summary(task)
    transcript_preview = (
        transcript[:5000] + "\n\n...(已截断)"
        if len(transcript) > 5000
        else transcript
    )
    return transcript_preview, summary


def delete_task(selected_file):
    if not selected_file or selected_file not in completed_tasks:
        return "请选择一个文件", build_task_table()
    del completed_tasks[selected_file]
    save_tasks(completed_tasks)
    logger.info(f"已删除任务记录: {selected_file}")
    return f"已删除记录: {selected_file}", build_task_table()


# ============================================================
# Gradio 界面
# ============================================================

def build_ui():
    with gr.Blocks(title="会议录音转写 + AI总结") as app:

        gr.Markdown("# 🎙️ 会议录音转写 + AI总结工具")

        if check_api_key():
            gr.Markdown(
                "✅ API Key 已配置 | 上传录音文件 → Whisper本地转写 → 通义千问AI总结"
            )
        else:
            gr.Markdown(
                "⚠️ **未检测到 API Key**，仅可转写，无法生成总结。请在「设置」中配置。"
            )

        with gr.Tabs():

            # ============ Tab 1: 转写 + 总结 ============
            with gr.Tab("📝 转写与总结"):

                with gr.Row():
                    file_input = gr.File(
                        label="上传录音文件（支持 mp3/m4a/wav/flac，可多选）",
                        file_count="multiple",
                        type="filepath",
                    )
                    with gr.Column():
                        model_choice = gr.Dropdown(
                            choices=["tiny", "base", "small", "medium", "large"],
                            value=config.WHISPER_MODEL,
                            label="Whisper 模型",
                            info="medium推荐，large更准但更慢",
                        )
                        diarization_toggle = gr.Checkbox(
                            label="🗣️ 启用说话人区分",
                            value=False,
                            info="识别不同说话人（需要HF_TOKEN）",
                        )
                        diarization_fallback = gr.Radio(
                            choices=["继续转写（不标注说话人）", "停止处理"],
                            value="继续转写（不标注说话人）",
                            label="说话人区分失败时",
                            visible=True,
                        )
                        run_btn = gr.Button(
                            "🚀 开始处理", variant="primary", size="lg"
                        )

                status_output = gr.Textbox(
                    label="处理状态", lines=5, interactive=False
                )

                with gr.Row():
                    transcript_output = gr.Textbox(
                        label="转写文本预览（可编辑后重新总结）",
                        lines=15,
                        interactive=True,
                    )
                    summary_output = gr.Textbox(
                        label="会议总结（纯文本）",
                        lines=15,
                        interactive=False,
                    )

                with gr.Row():
                    resummarize_btn = gr.Button(
                        "🔄 用左侧文本重新总结", variant="secondary"
                    )

                with gr.Accordion("📖 总结 Markdown 预览", open=False):
                    summary_md_preview = gr.Markdown("")

                run_btn.click(
                    fn=process_files,
                    inputs=[
                        file_input,
                        model_choice,
                        diarization_toggle,
                        diarization_fallback,
                    ],
                    outputs=[status_output, transcript_output, summary_output],
                ).then(
                    fn=lambda s: s,
                    inputs=[summary_output],
                    outputs=[summary_md_preview],
                )

                resummarize_btn.click(
                    fn=rerun_summary,
                    inputs=[transcript_output],
                    outputs=[summary_output],
                ).then(
                    fn=lambda s: s,
                    inputs=[summary_output],
                    outputs=[summary_md_preview],
                )

            # ============ Tab 2: 合并总结 ============
            with gr.Tab("🔗 合并总结"):

                gr.Markdown(
                    "选择已转写的文件，合并生成一份总结（适用于同一会议的多段录音）"
                )

                refresh_btn = gr.Button("🔄 刷新文件列表")
                file_selector = gr.CheckboxGroup(
                    choices=list(completed_tasks.keys()),
                    label="选择要合并的文件",
                )
                merge_btn = gr.Button("📋 生成合并总结", variant="primary")

                merge_status = gr.Textbox(
                    label="状态", lines=2, interactive=False
                )

                with gr.Accordion("📖 合并总结结果", open=True):
                    merge_md_output = gr.Markdown("")

                def refresh_file_list():
                    return gr.CheckboxGroup(choices=list(completed_tasks.keys()))

                refresh_btn.click(
                    fn=refresh_file_list, outputs=[file_selector]
                )
                merge_btn.click(
                    fn=merge_summarize,
                    inputs=[file_selector],
                    outputs=[merge_status, merge_md_output],
                )

            # ============ Tab 3: 任务管理 ============
            with gr.Tab("📋 任务管理"):

                gr.Markdown("查看所有已处理的任务，检查转写/总结状态")

                task_refresh_btn = gr.Button("🔄 刷新列表")
                task_table = gr.Markdown(build_task_table())

                gr.Markdown("---")
                gr.Markdown("### 查看任务详情")

                task_selector = gr.Dropdown(
                    choices=list(completed_tasks.keys()),
                    label="选择文件",
                    interactive=True,
                )
                view_btn = gr.Button("🔍 查看详情")

                with gr.Row():
                    delete_btn = gr.Button(
                        "🗑️ 删除记录（不删除文件）", variant="stop"
                    )
                    confirm_delete_btn = gr.Button(
                        "⚠️ 确认删除", variant="stop", visible=False
                    )
                    cancel_delete_btn = gr.Button("取消", visible=False)

                with gr.Row():
                    detail_transcript = gr.Textbox(
                        label="转写文本", lines=10, interactive=False
                    )
                    with gr.Column():
                        detail_summary_md = gr.Markdown(value="")

                delete_status = gr.Textbox(
                    label="操作状态", lines=1, interactive=False
                )

                def refresh_task_selector():
                    return (
                        gr.Dropdown(choices=list(completed_tasks.keys())),
                        build_task_table(),
                    )

                task_refresh_btn.click(
                    fn=refresh_task_selector,
                    outputs=[task_selector, task_table],
                )
                view_btn.click(
                    fn=view_task_detail,
                    inputs=[task_selector],
                    outputs=[detail_transcript, detail_summary_md],
                )

                def show_confirm(selected_file):
                    if not selected_file or selected_file not in completed_tasks:
                        return (
                            "请先选择一个文件",
                            gr.Button(visible=True),
                            gr.Button(visible=False),
                            gr.Button(visible=False),
                        )
                    return (
                        f"确定要删除「{selected_file}」的记录吗？",
                        gr.Button(visible=False),
                        gr.Button(visible=True),
                        gr.Button(visible=True),
                    )

                def confirm_delete(selected_file):
                    result, table = delete_task(selected_file)
                    return (
                        result,
                        table,
                        gr.Button(visible=True),
                        gr.Button(visible=False),
                        gr.Button(visible=False),
                    )

                def cancel_delete_fn():
                    return (
                        "",
                        gr.Button(visible=True),
                        gr.Button(visible=False),
                        gr.Button(visible=False),
                    )

                delete_btn.click(
                    fn=show_confirm,
                    inputs=[task_selector],
                    outputs=[
                        delete_status,
                        delete_btn,
                        confirm_delete_btn,
                        cancel_delete_btn,
                    ],
                )
                confirm_delete_btn.click(
                    fn=confirm_delete,
                    inputs=[task_selector],
                    outputs=[
                        delete_status,
                        task_table,
                        delete_btn,
                        confirm_delete_btn,
                        cancel_delete_btn,
                    ],
                )
                cancel_delete_btn.click(
                    fn=cancel_delete_fn,
                    outputs=[
                        delete_status,
                        delete_btn,
                        confirm_delete_btn,
                        cancel_delete_btn,
                    ],
                )

            # ============ Tab 4: Markdown 查看器 ============
            with gr.Tab("📖 Markdown 查看器"):

                gr.Markdown("查看任意 `.md` 文件，支持 Markdown 渲染效果")

                with gr.Row():
                    md_file_input = gr.File(
                        label="上传 .md 文件",
                        file_types=[".md", ".txt"],
                        type="filepath",
                    )
                    md_load_path = gr.Textbox(
                        label="或输入文件路径",
                        placeholder="例如: data/output/xxx/会议总结.md",
                    )

                md_load_btn = gr.Button("📖 加载并渲染")
                md_rendered = gr.Markdown("")
                md_raw = gr.Textbox(
                    label="原始 Markdown 文本（可编辑）",
                    lines=15,
                    interactive=True,
                )
                md_rerender_btn = gr.Button("🔄 重新渲染上方文本")

                def load_md_file(file, path_str):
                    content = ""
                    if file:
                        file_path = (
                            file.name if hasattr(file, "name") else str(file)
                        )
                        try:
                            content = Path(file_path).read_text(encoding="utf-8")
                        except Exception as e:
                            content = f"读取失败: {e}"
                    elif path_str and path_str.strip():
                        p = Path(path_str.strip())
                        if not p.is_absolute():
                            p = config.BASE_DIR / p
                        try:
                            content = p.read_text(encoding="utf-8")
                        except Exception as e:
                            content = f"读取失败: {e}"
                    else:
                        content = "请上传文件或输入路径"
                    return content, content

                md_load_btn.click(
                    fn=load_md_file,
                    inputs=[md_file_input, md_load_path],
                    outputs=[md_rendered, md_raw],
                )
                md_rerender_btn.click(
                    fn=lambda text: text,
                    inputs=[md_raw],
                    outputs=[md_rendered],
                )

            # ============ Tab 5: 设置 ============
            with gr.Tab("⚙️ 设置"):

                # --- API ---
                gr.Markdown("### API 配置")
                api_key_input = gr.Textbox(
                    label="通义千问 API Key",
                    value=config.DASHSCOPE_API_KEY,
                    type="password",
                    placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx",
                )
                save_key_btn = gr.Button("💾 保存 API Key（仅本次会话有效）")
                key_status = gr.Textbox(label="状态", interactive=False)

                gr.Markdown("### 说话人区分配置")
                hf_token_input = gr.Textbox(
                    label="Hugging Face Token",
                    value=config.HF_TOKEN,
                    type="password",
                    placeholder="hf_xxxxxxxxxxxxxxxxxxxxxxxx",
                )
                save_hf_btn = gr.Button("💾 保存 HF Token（仅本次会话有效）")
                hf_status = gr.Textbox(label="状态", interactive=False)
                gr.Markdown(
                    "说话人区分需要:\n"
                    "1. 注册 [Hugging Face](https://huggingface.co) 获取 Token\n"
                    "2. 同意模型协议: "
                    "[speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)、"
                    "[segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)、"
                    "[speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)"
                )

                def save_api_key(key):
                    config.DASHSCOPE_API_KEY = key
                    return "✅ 已保存" if key else "⚠️ 为空"

                def save_hf_token(token):
                    config.HF_TOKEN = token
                    return "✅ 已保存" if token else "⚠️ 为空"

                save_key_btn.click(
                    fn=save_api_key,
                    inputs=[api_key_input],
                    outputs=[key_status],
                )
                save_hf_btn.click(
                    fn=save_hf_token,
                    inputs=[hf_token_input],
                    outputs=[hf_status],
                )

                # --- Prompt 编辑 ---
                gr.Markdown("---")
                gr.Markdown("### Prompt 编辑")
                gr.Markdown(
                    "自定义总结提示词。修改后立即生效，不需要重启。\n"
                    "**注意保留占位符**（花括号部分），否则无法正常工作。"
                )

                with gr.Tabs():
                    with gr.Tab("单文件总结"):
                        prompt_single = gr.Textbox(
                            label="单文件总结 Prompt（必须包含 {transcript}）",
                            value=config.load_prompt("single_summary"),
                            lines=12,
                            interactive=True,
                        )
                        save_single_btn = gr.Button("💾 保存")
                        single_status = gr.Textbox(interactive=False)

                    with gr.Tab("分段提取"):
                        prompt_chunk = gr.Textbox(
                            label="分段提取 Prompt（必须包含 {chunk}）",
                            value=config.load_prompt("chunk_extract"),
                            lines=8,
                            interactive=True,
                        )
                        save_chunk_btn = gr.Button("💾 保存")
                        chunk_status = gr.Textbox(interactive=False)

                    with gr.Tab("合并总结"):
                        prompt_merge = gr.Textbox(
                            label="合并总结 Prompt（必须包含 {summaries}）",
                            value=config.load_prompt("merge_summary"),
                            lines=12,
                            interactive=True,
                        )
                        save_merge_btn = gr.Button("💾 保存")
                        merge_prompt_status = gr.Textbox(interactive=False)

                restore_btn = gr.Button("🔄 恢复所有 Prompt 为默认值")
                restore_status = gr.Textbox(interactive=False)

                def save_prompt_handler(key, content):
                    ok, msg = config.save_prompt(key, content)
                    icon = "✅" if ok else "❌"
                    return f"{icon} {msg}"

                save_single_btn.click(
                    fn=lambda c: save_prompt_handler("single_summary", c),
                    inputs=[prompt_single],
                    outputs=[single_status],
                )
                save_chunk_btn.click(
                    fn=lambda c: save_prompt_handler("chunk_extract", c),
                    inputs=[prompt_chunk],
                    outputs=[chunk_status],
                )
                save_merge_btn.click(
                    fn=lambda c: save_prompt_handler("merge_summary", c),
                    inputs=[prompt_merge],
                    outputs=[merge_prompt_status],
                )

                def restore_defaults():
                    for key, content in config.DEFAULT_PROMPTS.items():
                        config.save_prompt(key, content)
                    logger.info("已恢复所有 Prompt 为默认值")
                    return (
                        config.load_prompt("single_summary"),
                        config.load_prompt("chunk_extract"),
                        config.load_prompt("merge_summary"),
                        "✅ 已恢复默认值",
                    )

                restore_btn.click(
                    fn=restore_defaults,
                    outputs=[
                        prompt_single,
                        prompt_chunk,
                        prompt_merge,
                        restore_status,
                    ],
                )

                # --- 日志 ---
                gr.Markdown("---")
                gr.Markdown("### 日志")
                log_level_choice = gr.Dropdown(
                    choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                    value=config.LOG_LEVEL,
                    label="终端日志级别",
                )
                save_log_level_btn = gr.Button("💾 应用")
                log_level_status = gr.Textbox(interactive=False)

                def update_log_level(level):
                    set_log_level(level)
                    return f"✅ 日志级别已设为 {level}"

                save_log_level_btn.click(
                    fn=update_log_level,
                    inputs=[log_level_choice],
                    outputs=[log_level_status],
                )

                # --- 目录信息 ---
                gr.Markdown("---")
                gr.Markdown("### 数据目录")
                gr.Markdown(
                    f"- **输入文件**: `{config.INPUT_DIR}`\n"
                    f"- **中间文件**: `{config.TEMP_DIR}`\n"
                    f"- **输出结果**: `{config.OUTPUT_DIR}`\n"
                    f"- **Prompt 文件**: `{config.PROMPTS_DIR}`\n"
                    f"- **日志文件**: `{config.LOGS_DIR}`\n"
                    f"- **任务记录**: `{config.TASKS_DB_PATH}`"
                )

    return app


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    logger.info("启动会议录音转写工具")
    app = build_ui()
    app.launch(
        server_name="0.0.0.0",
        server_port=None,
        share=False,
        inbrowser=True,
        theme=gr.themes.Soft(),
    )
