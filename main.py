"""
会议录音转写 + AI总结工具 — Gradio 图形界面
运行: python3 main.py
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

import gradio as gr

import config
from transcriber import transcribe_audio
from summarizer import summarize_single, summarize_merged


# ============================================================
# 任务持久化
# ============================================================

def load_tasks() -> dict[str, dict]:
    """从磁盘加载已完成的任务记录"""
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
    """将任务记录保存到磁盘"""
    serializable = {}
    for name, task in tasks.items():
        serializable[name] = {
            "output_dir": str(task["output_dir"]),
            "summary_preview": task.get("summary", "")[:500],
            "timestamp": task.get("timestamp", ""),
        }
    config.TASKS_DB_PATH.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_transcript(task: dict) -> str:
    """从文件读取转写全文"""
    transcript_path = Path(task["output_dir"]) / "转写全文.txt"
    if transcript_path.exists():
        return transcript_path.read_text(encoding="utf-8")
    return ""


# 启动时加载历史任务
completed_tasks: dict[str, dict] = load_tasks()


# ============================================================
# 核心处理逻辑
# ============================================================

def process_files(files, model_name, progress=gr.Progress()):
    """处理上传的音频文件（批量）"""
    if not files:
        return "请先上传音频文件", "", ""

    results = []
    total_files = len(files)

    for file_idx, file in enumerate(files):
        file_path = file.name if hasattr(file, "name") else str(file)

        progress(
            file_idx / total_files,
            desc=f"[{file_idx+1}/{total_files}] 处理: {Path(file_path).name}",
        )

        # --- 转写 ---
        def transcribe_progress(ratio, msg):
            overall = (file_idx + ratio * 0.7) / total_files
            progress(overall, desc=f"[{file_idx+1}/{total_files}] {msg}")

        try:
            transcript, output_dir = transcribe_audio(
                audio_path=file_path,
                model_name=model_name,
                progress_callback=transcribe_progress,
            )
        except Exception as e:
            results.append(f"❌ {Path(file_path).name}: 转写失败 - {e}")
            continue

        # --- 总结 ---
        def summary_progress(ratio, msg):
            overall = (file_idx + 0.7 + ratio * 0.3) / total_files
            progress(overall, desc=f"[{file_idx+1}/{total_files}] {msg}")

        try:
            summary = summarize_single(transcript, progress_callback=summary_progress)
        except Exception as e:
            summary = f"⚠️ 总结生成失败: {e}"

        # 保存总结到输出目录
        summary_path = output_dir / "会议总结.md"
        summary_path.write_text(summary, encoding="utf-8")

        # 记录任务并持久化
        display_name = Path(file_path).name
        completed_tasks[display_name] = {
            "output_dir": str(output_dir),
            "summary": summary,
            "timestamp": datetime.now().isoformat(),
        }
        save_tasks(completed_tasks)

        results.append(f"✅ {display_name} → {output_dir}")

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
        summary_preview = last_task.get("summary", "")
    else:
        transcript_preview = ""
        summary_preview = ""

    status = "\n".join(results) + f"\n\n📁 输出目录: {config.OUTPUT_DIR}"
    return status, transcript_preview, summary_preview


def merge_summarize(selected_files, progress=gr.Progress()):
    """对选中的文件进行合并总结"""
    if not selected_files:
        return "请先选择要合并的文件"

    transcripts = {}
    for fname in selected_files:
        if fname in completed_tasks:
            transcript = get_transcript(completed_tasks[fname])
            if transcript:
                transcripts[fname] = transcript

    if not transcripts:
        return "所选文件没有转写结果"

    def merge_progress(ratio, msg):
        progress(ratio, desc=msg)

    try:
        merged_summary = summarize_merged(transcripts, progress_callback=merge_progress)
    except Exception as e:
        return f"合并总结失败: {e}"

    # 保存合并总结
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    merged_path = config.OUTPUT_DIR / f"合并总结_{timestamp}.md"
    merged_path.write_text(merged_summary, encoding="utf-8")

    return f"📄 合并总结已保存: {merged_path}\n\n{merged_summary}"


def rerun_summary(transcript_text, progress=gr.Progress()):
    """用修改后的转写文本重新生成总结"""
    if not transcript_text.strip():
        return "转写文本为空"

    def summary_progress(ratio, msg):
        progress(ratio, desc=msg)

    try:
        summary = summarize_single(transcript_text, progress_callback=summary_progress)
        return summary
    except Exception as e:
        return f"总结生成失败: {e}"


# ============================================================
# Gradio 界面
# ============================================================

def build_ui():
    with gr.Blocks(title="会议录音转写 + AI总结") as app:

        gr.Markdown("# 🎙️ 会议录音转写 + AI总结工具")
        gr.Markdown("上传录音文件 → Whisper本地转写 → 通义千问AI总结")

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
                        label="会议总结", lines=15, interactive=False
                    )

                with gr.Row():
                    resummarize_btn = gr.Button(
                        "🔄 用左侧文本重新总结", variant="secondary"
                    )

                run_btn.click(
                    fn=process_files,
                    inputs=[file_input, model_choice],
                    outputs=[status_output, transcript_output, summary_output],
                )

                resummarize_btn.click(
                    fn=rerun_summary,
                    inputs=[transcript_output],
                    outputs=[summary_output],
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
                merge_output = gr.Textbox(
                    label="合并总结结果", lines=20, interactive=False
                )

                def refresh_file_list():
                    return gr.CheckboxGroup(choices=list(completed_tasks.keys()))

                refresh_btn.click(
                    fn=refresh_file_list,
                    outputs=[file_selector],
                )

                merge_btn.click(
                    fn=merge_summarize,
                    inputs=[file_selector],
                    outputs=[merge_output],
                )

            # ============ Tab 3: 设置 ============
            with gr.Tab("⚙️ 设置"):

                gr.Markdown("### API 配置")
                api_key_input = gr.Textbox(
                    label="通义千问 API Key",
                    value=config.DASHSCOPE_API_KEY,
                    type="password",
                    placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx",
                )
                save_key_btn = gr.Button("💾 保存 API Key（仅本次会话有效）")
                key_status = gr.Textbox(label="状态", interactive=False)

                def save_api_key(key):
                    config.DASHSCOPE_API_KEY = key
                    if key:
                        return "✅ API Key 已保存"
                    else:
                        return "⚠️ API Key 为空，总结功能将不可用"

                save_key_btn.click(
                    fn=save_api_key,
                    inputs=[api_key_input],
                    outputs=[key_status],
                )

                gr.Markdown("### 数据目录")
                gr.Markdown(
                    f"- **输入文件**: `{config.INPUT_DIR}`\n"
                    f"- **中间文件**: `{config.TEMP_DIR}`\n"
                    f"- **输出结果**: `{config.OUTPUT_DIR}`\n"
                    f"- **任务记录**: `{config.TASKS_DB_PATH}`"
                )

                gr.Markdown("### 说明")
                gr.Markdown(
                    "- **Whisper 模型选择**: tiny/base 速度快但准确率低，medium 推荐，large 最准但最慢\n"
                    "- **首次运行**: 需要下载 Whisper 模型文件（medium 约 1.5GB），请耐心等待\n"
                    "- **断点续传**: 如果中途中断，再次处理同一文件会自动跳过已完成的部分\n"
                    "- **重启保留**: 已完成的任务记录会保存，重启程序后合并总结仍可使用"
                )

    return app


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name="0.0.0.0",
        server_port=None,
        share=False,
        inbrowser=True,
        theme=gr.themes.Soft(),
    )
