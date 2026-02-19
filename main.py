"""
会议录音转写 + AI总结工具 — Gradio 图形界面
运行: python3 main.py
"""

import json
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
    """将任务记录保存到磁盘（存完整summary用于查看）"""
    serializable = {}
    for name, task in tasks.items():
        serializable[name] = {
            "output_dir": str(task["output_dir"]),
            "summary": task.get("summary", ""),
            "timestamp": task.get("timestamp", ""),
            "has_transcript": bool(get_transcript(task)),
            "has_summary": bool(task.get("summary", "")),
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


def get_summary(task: dict) -> str:
    """读取总结（优先从文件，fallback到task记录）"""
    summary_path = Path(task["output_dir"]) / "会议总结.md"
    if summary_path.exists():
        return summary_path.read_text(encoding="utf-8")
    return task.get("summary", "")


def check_api_key() -> bool:
    """检查API Key是否已配置"""
    return bool(config.DASHSCOPE_API_KEY and config.DASHSCOPE_API_KEY.strip())


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
    has_api = check_api_key()

    if not has_api:
        results.append("⚠️ 未检测到 API Key，将只进行转写，不生成总结。\n")

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

        # --- 总结（仅在有API Key时执行） ---
        summary = ""
        if has_api:
            def summary_progress(ratio, msg):
                overall = (file_idx + 0.7 + ratio * 0.3) / total_files
                progress(overall, desc=f"[{file_idx+1}/{total_files}] {msg}")

            try:
                summary = summarize_single(
                    transcript, progress_callback=summary_progress
                )
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

        status_icon = "✅" if summary else "📝"
        results.append(f"{status_icon} {display_name} → {output_dir}")

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
    """对选中的文件进行合并总结"""
    if not selected_files:
        return "请先选择要合并的文件", ""

    if not check_api_key():
        return "❌ 未检测到 API Key，无法生成合并总结。请在设置中配置。", ""

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
        return f"合并总结失败: {e}", ""

    # 保存合并总结
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    merged_path = config.OUTPUT_DIR / f"合并总结_{timestamp}.md"
    merged_path.write_text(merged_summary, encoding="utf-8")

    status = f"📄 合并总结已保存: {merged_path}"
    return status, merged_summary


def rerun_summary(transcript_text, progress=gr.Progress()):
    """用修改后的转写文本重新生成总结"""
    if not transcript_text.strip():
        return "转写文本为空"

    if not check_api_key():
        return "❌ 未检测到 API Key，无法生成总结。请在设置中配置。"

    def summary_progress(ratio, msg):
        progress(ratio, desc=msg)

    try:
        summary = summarize_single(
            transcript_text, progress_callback=summary_progress
        )
        return summary
    except Exception as e:
        return f"总结生成失败: {e}"


# ============================================================
# 任务管理
# ============================================================

def build_task_table() -> str:
    """生成任务列表的Markdown表格"""
    if not completed_tasks:
        return "暂无任务记录"

    rows = []
    rows.append("| 序号 | 文件名 | 转写 | 总结 | 更新时间 | 输出目录 |")
    rows.append("|------|--------|------|------|----------|----------|")

    for idx, (name, task) in enumerate(completed_tasks.items(), 1):
        has_transcript = "✅" if get_transcript(task) else "❌"

        summary_text = get_summary(task)
        has_summary = "✅" if summary_text and not summary_text.startswith("⚠️") else "❌"

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


def refresh_task_table():
    """刷新任务表格"""
    return build_task_table()


def view_task_detail(selected_file):
    """查看某个任务的详细内容"""
    if not selected_file or selected_file not in completed_tasks:
        return "请选择一个文件", ""

    task = completed_tasks[selected_file]
    transcript = get_transcript(task)
    summary = get_summary(task)

    transcript_preview = (
        transcript[:5000] + "\n\n...(已截断)" if len(transcript) > 5000 else transcript
    )

    return transcript_preview, summary


def delete_task(selected_file):
    """从记录中删除任务（不删除文件）"""
    if not selected_file or selected_file not in completed_tasks:
        return "请选择一个文件", build_task_table()

    del completed_tasks[selected_file]
    save_tasks(completed_tasks)
    return f"已删除记录: {selected_file}", build_task_table()


# ============================================================
# Gradio 界面
# ============================================================

def build_ui():
    with gr.Blocks(title="会议录音转写 + AI总结") as app:

        gr.Markdown("# 🎙️ 会议录音转写 + AI总结工具")

        # API状态提示
        if check_api_key():
            gr.Markdown("✅ API Key 已配置 | 上传录音文件 → Whisper本地转写 → 通义千问AI总结")
        else:
            gr.Markdown("⚠️ **未检测到 API Key**，仅可转写，无法生成总结。请在「设置」中配置。")

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
                        label="会议总结（纯文本）", lines=15, interactive=False
                    )

                with gr.Row():
                    resummarize_btn = gr.Button(
                        "🔄 用左侧文本重新总结", variant="secondary"
                    )

                # Markdown 渲染预览
                with gr.Accordion("📖 总结 Markdown 预览", open=False):
                    summary_md_preview = gr.Markdown("")

                run_btn.click(
                    fn=process_files,
                    inputs=[file_input, model_choice],
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
                    fn=refresh_file_list,
                    outputs=[file_selector],
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

                task_refresh_btn.click(
                    fn=refresh_task_table,
                    outputs=[task_table],
                )

                gr.Markdown("---")
                gr.Markdown("### 查看任务详情")

                task_selector = gr.Dropdown(
                    choices=list(completed_tasks.keys()),
                    label="选择文件",
                    interactive=True,
                )
                view_btn = gr.Button("🔍 查看详情")
                delete_btn = gr.Button("🗑️ 删除记录（不删除文件）", variant="stop")

                with gr.Row():
                    detail_transcript = gr.Textbox(
                        label="转写文本", lines=10, interactive=False
                    )
                    with gr.Column():
                        detail_summary_md = gr.Markdown(
                            label="会议总结",
                            value="",
                        )

                delete_status = gr.Textbox(
                    label="操作状态", lines=1, interactive=False
                )

                def refresh_task_selector():
                    choices = list(completed_tasks.keys())
                    return (
                        gr.Dropdown(choices=choices),
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

                delete_btn.click(
                    fn=delete_task,
                    inputs=[task_selector],
                    outputs=[delete_status, task_table],
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
                    """从上传文件或路径加载md"""
                    content = ""

                    if file:
                        file_path = file.name if hasattr(file, "name") else str(file)
                        try:
                            content = Path(file_path).read_text(encoding="utf-8")
                        except Exception as e:
                            content = f"读取失败: {e}"
                    elif path_str and path_str.strip():
                        p = Path(path_str.strip())
                        # 支持相对路径（相对于脚本目录）
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
                        return "✅ API Key 已保存（本次会话有效）"
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
                    "- **重启保留**: 已完成的任务记录会保存，重启程序后合并总结仍可使用\n"
                    "- **API Key**: 建议通过环境变量设置（永久有效），也可在此页面临时填入"
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
