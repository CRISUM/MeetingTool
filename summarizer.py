"""
AI 总结模块
- 单文件总结
- 超长文本分段总结
- 多文件合并总结
"""

from typing import Callable, Optional

import config


def _call_qwen(prompt: str) -> str:
    """调用通义千问 API"""
    import dashscope
    from dashscope import Generation

    dashscope.api_key = config.DASHSCOPE_API_KEY

    response = Generation.call(
        model=config.QWEN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        result_format="message",
    )

    if response.status_code == 200:
        return response.output.choices[0].message.content
    else:
        raise Exception(f"通义千问 API 调用失败: {response.code} - {response.message}")


def summarize_single(
    transcript: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """
    对单个转写文本生成总结。
    超长文本自动分段处理。
    """
    if not config.DASHSCOPE_API_KEY:
        return "⚠️ 未配置通义千问 API Key，无法生成总结。\n请设置环境变量 DASHSCOPE_API_KEY 或在 config.py 中填写。"

    max_chars = 28000  # 单次输入限制，留余量给 prompt

    if len(transcript) <= max_chars:
        # 文本不长，直接总结
        if progress_callback:
            progress_callback(0.5, "正在生成总结...")

        prompt = config.SINGLE_SUMMARY_PROMPT.format(transcript=transcript)
        summary = _call_qwen(prompt)

        if progress_callback:
            progress_callback(1.0, "总结完成")
        return summary
    else:
        # 文本太长，分段提取要点再合并
        return _summarize_long_text(transcript, max_chars, progress_callback)


def _summarize_long_text(
    transcript: str,
    max_chars: int,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """对超长文本分段提取要点，再合并生成总结"""
    chunks = []
    for i in range(0, len(transcript), max_chars):
        chunks.append(transcript[i:i + max_chars])

    total = len(chunks)
    if progress_callback:
        progress_callback(0.1, f"文本较长（{len(transcript)}字），分 {total} 段处理...")

    # 每段提取要点
    chunk_summaries = []
    for idx, chunk in enumerate(chunks):
        if progress_callback:
            ratio = 0.1 + 0.7 * idx / total
            progress_callback(ratio, f"提取第 {idx+1}/{total} 段要点...")

        prompt = config.CHUNK_EXTRACT_PROMPT.format(chunk=chunk)
        result = _call_qwen(prompt)
        chunk_summaries.append(result)

    # 合并生成最终总结
    if progress_callback:
        progress_callback(0.85, "合并生成最终总结...")

    merged = "\n\n---\n\n".join(chunk_summaries)
    prompt = config.SINGLE_SUMMARY_PROMPT.format(transcript=merged)
    summary = _call_qwen(prompt)

    if progress_callback:
        progress_callback(1.0, "总结完成")
    return summary


def summarize_merged(
    transcripts: dict[str, str],
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """
    将多个文件的转写文本合并总结。

    Args:
        transcripts: {文件名: 转写文本} 的字典
        progress_callback: 进度回调
    """
    if not config.DASHSCOPE_API_KEY:
        return "⚠️ 未配置通义千问 API Key，无法生成总结。"

    if progress_callback:
        progress_callback(0.1, f"合并 {len(transcripts)} 个文件的内容...")

    # 先对每个文件提取要点（避免合并后太长）
    file_summaries = []
    total = len(transcripts)
    for idx, (filename, transcript) in enumerate(transcripts.items()):
        if progress_callback:
            ratio = 0.1 + 0.6 * idx / total
            progress_callback(ratio, f"提取 {filename} 的要点...")

        # 如果单个文件就很长，先压缩
        if len(transcript) > 28000:
            chunks = [transcript[i:i+28000] for i in range(0, len(transcript), 28000)]
            sub_summaries = []
            for chunk in chunks:
                prompt = config.CHUNK_EXTRACT_PROMPT.format(chunk=chunk)
                sub_summaries.append(_call_qwen(prompt))
            file_summary = "\n".join(sub_summaries)
        else:
            prompt = config.CHUNK_EXTRACT_PROMPT.format(chunk=transcript)
            file_summary = _call_qwen(prompt)

        file_summaries.append(f"【{filename}】\n{file_summary}")

    # 合并总结
    if progress_callback:
        progress_callback(0.8, "生成合并总结...")

    all_summaries = "\n\n---\n\n".join(file_summaries)
    prompt = config.MERGE_SUMMARY_PROMPT.format(summaries=all_summaries)
    summary = _call_qwen(prompt)

    if progress_callback:
        progress_callback(1.0, "合并总结完成")
    return summary
