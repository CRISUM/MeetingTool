"""
AI 总结模块
- 单文件总结
- 超长文本分段总结
- 多文件合并总结
- Prompt 从文件读取
"""

import logging
import time
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)


def _call_qwen(prompt: str) -> str:
    """调用通义千问 API"""
    import dashscope
    from dashscope import Generation

    dashscope.api_key = config.DASHSCOPE_API_KEY

    start_time = time.time()
    response = Generation.call(
        model=config.QWEN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        result_format="message",
    )
    elapsed = time.time() - start_time

    if response.status_code == 200:
        result = response.output.choices[0].message.content
        logger.debug(f"API 调用成功 | 耗时 {elapsed:.1f}s | 响应长度 {len(result)}")
        return result
    else:
        logger.error(f"API 调用失败 | {response.code} - {response.message}")
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
        return (
            "⚠️ 未配置通义千问 API Key，无法生成总结。\n"
            "请设置环境变量 DASHSCOPE_API_KEY 或在设置中填写。"
        )

    logger.info(f"开始生成总结 | 文本长度 {len(transcript)} 字")
    max_chars = 28000

    if len(transcript) <= max_chars:
        if progress_callback:
            progress_callback(0.5, "正在生成总结...")

        prompt_template = config.load_prompt("single_summary")
        prompt = prompt_template.format(transcript=transcript)
        summary = _call_qwen(prompt)

        if progress_callback:
            progress_callback(1.0, "总结完成")

        logger.info(f"总结生成完成 | 总结长度 {len(summary)} 字")
        return summary
    else:
        return _summarize_long_text(transcript, max_chars, progress_callback)


def _summarize_long_text(
    transcript: str,
    max_chars: int,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """对超长文本分段提取要点，再合并生成总结"""
    chunks = []
    for i in range(0, len(transcript), max_chars):
        chunks.append(transcript[i : i + max_chars])

    total = len(chunks)
    logger.info(f"文本较长（{len(transcript)}字），分 {total} 段处理")

    if progress_callback:
        progress_callback(0.1, f"文本较长（{len(transcript)}字），分 {total} 段处理...")

    chunk_extract_template = config.load_prompt("chunk_extract")
    chunk_summaries = []

    for idx, chunk in enumerate(chunks):
        if progress_callback:
            ratio = 0.1 + 0.7 * idx / total
            progress_callback(ratio, f"提取第 {idx+1}/{total} 段要点...")

        logger.debug(f"提取第 {idx+1}/{total} 段要点")
        prompt = chunk_extract_template.format(chunk=chunk)
        result = _call_qwen(prompt)
        chunk_summaries.append(result)

    if progress_callback:
        progress_callback(0.85, "合并生成最终总结...")

    merged = "\n\n---\n\n".join(chunk_summaries)
    summary_template = config.load_prompt("single_summary")
    prompt = summary_template.format(transcript=merged)
    summary = _call_qwen(prompt)

    if progress_callback:
        progress_callback(1.0, "总结完成")

    logger.info(f"长文本总结完成 | 总结长度 {len(summary)} 字")
    return summary


def summarize_merged(
    transcripts: dict[str, str],
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """将多个文件的转写文本合并总结。"""
    if not config.DASHSCOPE_API_KEY:
        return "⚠️ 未配置通义千问 API Key，无法生成总结。"

    logger.info(f"开始合并总结 | {len(transcripts)} 个文件")

    if progress_callback:
        progress_callback(0.1, f"合并 {len(transcripts)} 个文件的内容...")

    chunk_extract_template = config.load_prompt("chunk_extract")
    file_summaries = []
    total = len(transcripts)

    for idx, (filename, transcript) in enumerate(transcripts.items()):
        if progress_callback:
            ratio = 0.1 + 0.6 * idx / total
            progress_callback(ratio, f"提取 {filename} 的要点...")

        logger.debug(f"提取 {filename} 的要点 | {len(transcript)} 字")

        if len(transcript) > 28000:
            chunks = [
                transcript[i : i + 28000]
                for i in range(0, len(transcript), 28000)
            ]
            sub_summaries = []
            for chunk in chunks:
                prompt = chunk_extract_template.format(chunk=chunk)
                sub_summaries.append(_call_qwen(prompt))
            file_summary = "\n".join(sub_summaries)
        else:
            prompt = chunk_extract_template.format(chunk=transcript)
            file_summary = _call_qwen(prompt)

        file_summaries.append(f"【{filename}】\n{file_summary}")

    if progress_callback:
        progress_callback(0.8, "生成合并总结...")

    all_summaries = "\n\n---\n\n".join(file_summaries)
    merge_template = config.load_prompt("merge_summary")
    prompt = merge_template.format(summaries=all_summaries)
    summary = _call_qwen(prompt)

    if progress_callback:
        progress_callback(1.0, "合并总结完成")

    logger.info(f"合并总结完成 | 总结长度 {len(summary)} 字")
    return summary
