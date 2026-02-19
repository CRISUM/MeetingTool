"""
Gradio UI 层（Gradio 6 兼容）
- theme/head 参数移至 launch()
- Toast 通过隐藏 Textbox + js= 参数触发，避免 script 标签不重复执行的问题
- open_dir_btn 直接读 task_selector 值，不依赖异步 State
"""

import json
import time

import gradio as gr

import config
import handlers
import state

# ============================================================
# Toast 系统
# ============================================================

# CSS + JS 容器，通过 gr.HTML 注入一次
TOAST_CONTAINER_HTML = """
<style>
#mt-toast-container {
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 9999;
    display: flex;
    flex-direction: column-reverse;
    gap: 8px;
    pointer-events: none;
}
.mt-toast {
    min-width: 260px;
    max-width: 400px;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    color: #fff;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18);
    opacity: 0;
    transform: translateX(40px);
    transition: opacity 0.22s ease, transform 0.22s ease;
    pointer-events: auto;
    cursor: pointer;
    line-height: 1.45;
    word-break: break-word;
}
.mt-toast.show { opacity: 1; transform: translateX(0); }
.mt-toast.hide { opacity: 0; transform: translateX(40px); }
.mt-toast-success { background: #22c55e; }
.mt-toast-error   { background: #ef4444; }
.mt-toast-warning { background: #f59e0b; }
.mt-toast-info    { background: #3b82f6; }
</style>

<script>
(function() {
    const MAX_TOASTS = 3;
    const DURATION   = 4000;

    function ensureContainer() {
        if (!document.getElementById('mt-toast-container')) {
            const c = document.createElement('div');
            c.id = 'mt-toast-container';
            document.body.appendChild(c);
        }
        return document.getElementById('mt-toast-container');
    }

    window._showToasts = function(list) {
        if (!Array.isArray(list) || !list.length) return;
        list.forEach(function(t) { addToast(t.type || 'info', t.msg || ''); });
    };

    function addToast(type, msg) {
        const c = ensureContainer();
        const items = c.querySelectorAll('.mt-toast');
        if (items.length >= MAX_TOASTS) removeToast(items[items.length - 1]);

        const el = document.createElement('div');
        el.className = 'mt-toast mt-toast-' + type;
        el.textContent = msg;
        el.onclick = function() { removeToast(el); };
        c.appendChild(el);

        requestAnimationFrame(function() {
            requestAnimationFrame(function() { el.classList.add('show'); });
        });
        el._tid = setTimeout(function() { removeToast(el); }, DURATION);
    }

    function removeToast(el) {
        if (!el || el._gone) return;
        el._gone = true;
        clearTimeout(el._tid);
        el.classList.remove('show');
        el.classList.add('hide');
        setTimeout(function() { el.parentNode && el.parentNode.removeChild(el); }, 280);
    }
})();
</script>
"""

# js= 函数：在浏览器端读取隐藏 Textbox 的值并调用 _showToasts
# Gradio 6 的 js= 接收与 inputs 对应的参数，返回值写回 outputs
_TOAST_JS = """
(payload) => {
    try {
        if (payload) {
            const obj = JSON.parse(payload);
            if (window._showToasts && obj.toasts) {
                window._showToasts(obj.toasts);
            }
        }
    } catch(e) { console.warn('toast parse error', e); }
    return payload;
}
"""

def _toast_payload(toasts: list[dict]) -> str:
    """序列化 toast 列表为 JSON，时间戳保证每次值不同从而触发 change 事件"""
    if not toasts:
        return ""
    return json.dumps({"ts": time.time(), "toasts": toasts}, ensure_ascii=False)


# ============================================================
# UI 构建
# ============================================================

def build_ui() -> gr.Blocks:

    feature_status = handlers.get_feature_status()

    with gr.Blocks(title="会议录音转写 + AI总结") as app:

        # Toast 容器（CSS + JS），只注入一次
        gr.HTML(value=TOAST_CONTAINER_HTML)

        # 隐藏 Textbox：Python 写入 JSON → js= 触发弹窗
        toast_payload = gr.Textbox(value="", visible=False)

        # 跨 Tab 共享状态
        current_task_name = gr.State(value="")
        is_annotated_view = gr.State(value=False)

        gr.Markdown("# 🎙️ 会议录音转写 + AI总结工具")

        if feature_status["summary"]:
            gr.Markdown("✅ API Key 已配置 | FunASR 本地转写 + 通义千问 AI 总结")
        else:
            gr.Markdown(
                "⚠️ **未检测到 DASHSCOPE_API_KEY**，总结功能不可用。"
                "可在「设置」中配置（仅当次会话有效）。"
            )

        with gr.Tabs():

            # ------------------------------------------------
            # Tab 1: 转写与总结
            # ------------------------------------------------
            with gr.Tab("📝 转写与总结"):

                with gr.Row():
                    file_input = gr.File(
                        label="上传录音文件（mp3/m4a/wav/flac，可多选）",
                        file_count="multiple",
                        type="filepath",
                    )
                    with gr.Column(scale=1):
                        enable_speaker_cb = gr.Checkbox(
                            label="🗣️ 启用说话人区分（cam++）",
                            value=False,
                            info="识别不同说话人，声音相似时效果有限",
                        )
                        enable_summary_cb = gr.Checkbox(
                            label="📋 启用 AI 总结",
                            value=feature_status["summary"],
                            interactive=feature_status["summary"],
                            info="" if feature_status["summary"] else "需要配置 DASHSCOPE_API_KEY",
                        )
                        run_btn = gr.Button("🚀 开始处理", variant="primary", size="lg")

                process_status = gr.Textbox(
                    label="处理状态",
                    lines=6,
                    interactive=False,
                    placeholder="处理结果将显示在这里...",
                )

            # ------------------------------------------------
            # Tab 2: 合并总结
            # ------------------------------------------------
            with gr.Tab("🔗 合并总结"):

                gr.Markdown("选择已转写的文件，合并生成一份总结（适用于同一会议的多段录音）")

                merge_refresh_btn = gr.Button("🔄 刷新文件列表")
                merge_file_selector = gr.CheckboxGroup(
                    choices=state.get_task_names(),
                    label="选择要合并的文件",
                )
                merge_btn = gr.Button(
                    "📋 生成合并总结",
                    variant="primary",
                    interactive=feature_status["summary"],
                )
                merge_status = gr.Textbox(label="状态", lines=2, interactive=False)
                with gr.Accordion("📖 合并总结结果", open=True):
                    merge_md_output = gr.Markdown("")

            # ------------------------------------------------
            # Tab 3: 任务管理
            # ------------------------------------------------
            with gr.Tab("📋 任务管理"):

                task_refresh_btn = gr.Button("🔄 刷新列表")
                task_table = gr.Markdown(handlers.build_task_table())

                gr.Markdown("---")
                gr.Markdown("### 查看任务详情")

                with gr.Row():
                    task_selector = gr.Dropdown(
                        choices=state.get_task_names(),
                        label="选择任务",
                        interactive=True,
                        scale=4,
                    )
                    open_dir_btn = gr.Button("📂 打开输出目录", scale=1)

                with gr.Row():
                    gr.Markdown("**转写文本**")
                    toggle_view_btn = gr.Button(
                        "切换为说话人版",
                        size="sm",
                        interactive=False,
                    )

                detail_transcript = gr.Textbox(
                    label="",
                    lines=12,
                    interactive=True,
                    placeholder="选择任务后自动加载...",
                )

                gr.Markdown("**会议总结**")
                rerun_summary_btn = gr.Button(
                    "🔄 用上方文本重新总结",
                    variant="secondary",
                    interactive=feature_status["summary"],
                )
                with gr.Accordion("📖 总结预览（Markdown 渲染）", open=True):
                    detail_summary_md = gr.Markdown("")
                detail_summary_text = gr.Textbox(visible=False)

                gr.Markdown("---")
                gr.Markdown("### 删除记录")
                with gr.Row():
                    delete_btn = gr.Button("🗑️ 删除记录（不删除文件）", variant="stop")
                    confirm_delete_btn = gr.Button("⚠️ 确认删除", variant="stop", visible=False)
                    cancel_delete_btn = gr.Button("取消", visible=False)

            # ------------------------------------------------
            # Tab 4: Markdown 查看器
            # ------------------------------------------------
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

            # ------------------------------------------------
            # Tab 5: 设置
            # ------------------------------------------------
            with gr.Tab("⚙️ 设置"):

                gr.Markdown("### API 配置")
                gr.Markdown("- **DASHSCOPE_API_KEY**：通义千问总结功能")

                with gr.Row():
                    api_key_input = gr.Textbox(
                        label="DASHSCOPE_API_KEY",
                        value=config.DASHSCOPE_API_KEY,
                        type="password",
                        placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx",
                        scale=4,
                    )
                    save_key_btn = gr.Button("💾 保存（本次会话）", scale=1)

                gr.Markdown("---")
                gr.Markdown("### Prompt 编辑")
                gr.Markdown("修改后立即生效，无需重启。**注意保留占位符**（花括号部分）。")

                with gr.Tabs():
                    with gr.Tab("单文件总结"):
                        prompt_single = gr.Textbox(
                            label="必须包含 {transcript}",
                            value=config.load_prompt("single_summary"),
                            lines=14,
                            interactive=True,
                        )
                        save_single_btn = gr.Button("💾 保存")

                    with gr.Tab("分段提取"):
                        prompt_chunk = gr.Textbox(
                            label="必须包含 {chunk}（超长文本的中间步骤，用户不可见）",
                            value=config.load_prompt("chunk_extract"),
                            lines=8,
                            interactive=True,
                        )
                        save_chunk_btn = gr.Button("💾 保存")

                    with gr.Tab("合并总结"):
                        prompt_merge = gr.Textbox(
                            label="必须包含 {summaries}",
                            value=config.load_prompt("merge_summary"),
                            lines=14,
                            interactive=True,
                        )
                        save_merge_btn = gr.Button("💾 保存")

                restore_btn = gr.Button("🔄 恢复所有 Prompt 为默认值")

                gr.Markdown("---")
                gr.Markdown("### 日志")
                gr.Markdown(
                    "调整本项目的终端日志级别。"
                    "第三方库（FunASR/Gradio 等）的噪音已固定压制，不受此影响。"
                )
                with gr.Row():
                    log_level_choice = gr.Dropdown(
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        value=config.LOG_LEVEL,
                        label="终端日志级别",
                        scale=3,
                    )
                    save_log_level_btn = gr.Button("💾 应用", scale=1)

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

        # ====================================================
        # toast_payload 变化 → 执行 JS 弹窗
        # ====================================================
        toast_payload.change(
            fn=None,
            inputs=[toast_payload],
            outputs=[toast_payload],
            js=_TOAST_JS,
        )

        # ====================================================
        # 事件绑定
        # ====================================================

        # ---- 转写与总结 ----

        def _process(files, spk, summ, progress=gr.Progress()):
            status, names, toasts = handlers.process_files(files, spk, summ, progress)
            return (
                status,
                gr.Dropdown(choices=names),
                gr.CheckboxGroup(choices=names),
                handlers.build_task_table(),
                _toast_payload(toasts),
            )

        run_btn.click(
            fn=_process,
            inputs=[file_input, enable_speaker_cb, enable_summary_cb],
            outputs=[process_status, task_selector, merge_file_selector,
                     task_table, toast_payload],
        )

        # ---- 任务管理 ----

        def _load_task(task_name):
            if not task_name:
                return ("", False, "", "",
                        gr.Button(interactive=False, value="切换为说话人版"))
            txt, has_ann, summ, summ_md, ann_view = handlers.load_task_detail(task_name)
            label = "切换为普通版" if ann_view else "切换为说话人版"
            return txt, ann_view, summ_md, summ, gr.Button(interactive=has_ann, value=label)

        task_selector.change(
            fn=_load_task,
            inputs=[task_selector],
            outputs=[detail_transcript, is_annotated_view,
                     detail_summary_md, detail_summary_text, toggle_view_btn],
        ).then(
            fn=lambda n: n,
            inputs=[task_selector],
            outputs=[current_task_name],
        )

        def _toggle_view(task_name, cur_ann):
            text, new_ann = handlers.toggle_transcript_view(task_name, cur_ann)
            label = "切换为普通版" if new_ann else "切换为说话人版"
            return text, new_ann, gr.Button(value=label)

        toggle_view_btn.click(
            fn=_toggle_view,
            inputs=[current_task_name, is_annotated_view],
            outputs=[detail_transcript, is_annotated_view, toggle_view_btn],
        )

        def _rerun(task_name, txt, progress=gr.Progress()):
            summ, _, toasts = handlers.rerun_summary(task_name, txt, progress)
            return summ, summ, _toast_payload(toasts)

        rerun_summary_btn.click(
            fn=_rerun,
            inputs=[current_task_name, detail_transcript],
            outputs=[detail_summary_md, detail_summary_text, toast_payload],
        )

        # 打开目录：直接用 task_selector 不用 State，避免竞争
        def _open_dir(task_name, request: gr.Request):
            return _toast_payload(handlers.open_output_dir(task_name, request))

        open_dir_btn.click(
            fn=_open_dir,
            inputs=[task_selector],
            outputs=[toast_payload],
        )

        def _refresh_tasks():
            names = state.get_task_names()
            return gr.Dropdown(choices=names), handlers.build_task_table()

        task_refresh_btn.click(
            fn=_refresh_tasks,
            outputs=[task_selector, task_table],
        )

        # 删除流程
        def _show_confirm(task_name):
            if not task_name:
                return (gr.Button(visible=True), gr.Button(visible=False),
                        gr.Button(visible=False),
                        _toast_payload([handlers.toast_warning("请先选择一个任务")]))
            return (gr.Button(visible=False), gr.Button(visible=True),
                    gr.Button(visible=True), "")

        def _confirm_del(task_name):
            names, toasts = handlers.delete_task(task_name)
            return (
                gr.Dropdown(choices=names, value=None),
                gr.CheckboxGroup(choices=names),
                handlers.build_task_table(),
                gr.Button(visible=True), gr.Button(visible=False), gr.Button(visible=False),
                "", "",
                _toast_payload(toasts),
            )

        def _cancel_del():
            return gr.Button(visible=True), gr.Button(visible=False), gr.Button(visible=False)

        delete_btn.click(
            fn=_show_confirm,
            inputs=[task_selector],
            outputs=[delete_btn, confirm_delete_btn, cancel_delete_btn, toast_payload],
        )
        confirm_delete_btn.click(
            fn=_confirm_del,
            inputs=[task_selector],
            outputs=[task_selector, merge_file_selector, task_table,
                     delete_btn, confirm_delete_btn, cancel_delete_btn,
                     detail_transcript, detail_summary_md, toast_payload],
        )
        cancel_delete_btn.click(
            fn=_cancel_del,
            outputs=[delete_btn, confirm_delete_btn, cancel_delete_btn],
        )

        # ---- 合并总结 ----

        def _merge(selected, progress=gr.Progress()):
            status, md, toasts = handlers.merge_summarize(selected, progress)
            return status, md, _toast_payload(toasts)

        merge_btn.click(fn=_merge, inputs=[merge_file_selector],
                        outputs=[merge_status, merge_md_output, toast_payload])
        merge_refresh_btn.click(
            fn=lambda: gr.CheckboxGroup(choices=state.get_task_names()),
            outputs=[merge_file_selector],
        )

        # ---- Markdown 查看器 ----

        def _load_md(file, path_str):
            from pathlib import Path as P
            if file:
                try:
                    content = P(file if isinstance(file, str) else file.name).read_text(encoding="utf-8")
                except Exception as e:
                    content = f"读取失败: {e}"
            elif path_str and path_str.strip():
                p = P(path_str.strip())
                if not p.is_absolute():
                    p = config.BASE_DIR / p
                try:
                    content = p.read_text(encoding="utf-8")
                except Exception as e:
                    content = f"读取失败: {e}"
            else:
                content = "请上传文件或输入路径"
            return content, content

        md_load_btn.click(fn=_load_md, inputs=[md_file_input, md_load_path],
                          outputs=[md_rendered, md_raw])
        md_rerender_btn.click(fn=lambda t: t, inputs=[md_raw], outputs=[md_rendered])

        # ---- 设置 ----

        def _save_key(key):
            is_valid, toasts = handlers.save_api_key(key)
            return (
                gr.Checkbox(interactive=is_valid,
                            info="" if is_valid else "需要配置 DASHSCOPE_API_KEY"),
                gr.Button(interactive=is_valid),
                gr.Button(interactive=is_valid),
                _toast_payload(toasts),
            )

        save_key_btn.click(
            fn=_save_key,
            inputs=[api_key_input],
            outputs=[enable_summary_cb, merge_btn, rerun_summary_btn, toast_payload],
        )

        def _save_prompt(key, content):
            return _toast_payload(handlers.save_prompt_handler(key, content))

        save_single_btn.click(fn=lambda c: _save_prompt("single_summary", c),
                              inputs=[prompt_single], outputs=[toast_payload])
        save_chunk_btn.click(fn=lambda c: _save_prompt("chunk_extract", c),
                             inputs=[prompt_chunk], outputs=[toast_payload])
        save_merge_btn.click(fn=lambda c: _save_prompt("merge_summary", c),
                             inputs=[prompt_merge], outputs=[toast_payload])

        def _restore():
            p1, p2, p3, toasts = handlers.restore_defaults_handler()
            return p1, p2, p3, _toast_payload(toasts)

        restore_btn.click(fn=_restore,
                          outputs=[prompt_single, prompt_chunk, prompt_merge, toast_payload])

        save_log_level_btn.click(
            fn=lambda lvl: _toast_payload(handlers.update_log_level_handler(lvl)),
            inputs=[log_level_choice],
            outputs=[toast_payload],
        )

    return app


# launch 参数集中在这里，main.py 直接解包使用
LAUNCH_KWARGS = dict(
    server_name="0.0.0.0",
    server_port=None,
    share=False,
    inbrowser=True,
    theme=gr.themes.Soft(),
)