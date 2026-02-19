"""
音频转写模块
- 音频切片（用于断点续传）
- Whisper 本地转写
- 断点恢复
- 保存 segments（带时间戳）供说话人对齐使用
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from pydub import AudioSegment

import config

logger = logging.getLogger(__name__)

# 全局缓存，避免重复加载模型
_whisper_model = None


def get_whisper_model(model_name: str = None):
    """加载并缓存 Whisper 模型"""
    global _whisper_model
    import whisper

    model_name = model_name or config.WHISPER_MODEL
    if _whisper_model is None:
        logger.info(f"加载 Whisper {model_name} 模型...")
        _whisper_model = whisper.load_model(model_name)
        logger.info("Whisper 模型加载完成")
    return _whisper_model


def split_audio(audio_path: str, task_name: str) -> list[Path]:
    """
    将音频切成固定时长的小段，保存到 temp/{task_name}/chunks/
    返回切片文件路径列表
    """
    chunks_dir = config.TEMP_DIR / task_name / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = config.TEMP_DIR / task_name / "chunks_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        chunk_paths = [Path(p) for p in manifest["chunk_paths"]]
        if all(p.exists() for p in chunk_paths):
            logger.debug(f"切片已存在，跳过: {len(chunk_paths)} 段")
            return chunk_paths

    logger.info(f"开始切分音频: {audio_path}")
    audio = AudioSegment.from_file(audio_path)
    duration_ms = len(audio)
    chunk_ms = config.CHUNK_DURATION_SECONDS * 1000

    chunk_paths = []
    idx = 0
    for start in range(0, duration_ms, chunk_ms):
        end = min(start + chunk_ms, duration_ms)
        chunk = audio[start:end]
        chunk_path = chunks_dir / f"chunk_{idx:04d}.wav"
        chunk.export(str(chunk_path), format="wav")
        chunk_paths.append(chunk_path)
        idx += 1

    manifest = {
        "source_audio": str(audio_path),
        "total_chunks": len(chunk_paths),
        "chunk_duration_seconds": config.CHUNK_DURATION_SECONDS,
        "chunk_paths": [str(p) for p in chunk_paths],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(f"音频切分完成: {len(chunk_paths)} 段")
    return chunk_paths


def transcribe_audio(
    audio_path: str,
    model_name: str = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> tuple[str, Path]:
    """
    转写音频文件，支持断点续传。
    同时保存 segments json（带时间戳）供说话人对齐。

    Returns:
        (完整转写文本, 输出目录路径)
    """
    file_name = Path(audio_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_name = f"{file_name}_{timestamp}"

    # 检查是否有未完成的同名任务（断点恢复）
    existing_task = _find_existing_task(file_name)
    if existing_task:
        task_name = existing_task
        logger.info(f"发现未完成任务，恢复: {task_name}")

    # 复制原始文件到 input 目录
    input_copy = config.INPUT_DIR / Path(audio_path).name
    if not input_copy.exists():
        import shutil
        shutil.copy2(audio_path, input_copy)

    output_dir = config.OUTPUT_DIR / task_name
    output_dir.mkdir(parents=True, exist_ok=True)

    temp_dir = config.TEMP_DIR / task_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    results_dir = temp_dir / "chunk_results"
    results_dir.mkdir(exist_ok=True)

    final_transcript_path = output_dir / "转写全文.txt"

    # 如果已有完整转写结果，直接返回
    if final_transcript_path.exists():
        text = final_transcript_path.read_text(encoding="utf-8")
        if text.strip():
            if progress_callback:
                progress_callback(1.0, "已有转写结果，跳过")
            logger.info(f"已有转写结果，跳过: {task_name}")
            return text, output_dir

    if progress_callback:
        progress_callback(0.0, "正在切分音频...")

    chunk_paths = split_audio(audio_path, task_name)
    total_chunks = len(chunk_paths)

    if progress_callback:
        progress_callback(0.05, f"音频已切为 {total_chunks} 段，加载模型中...")

    model = get_whisper_model(model_name)

    if progress_callback:
        progress_callback(0.1, "模型加载完成，开始转写...")

    # 逐段转写（带断点恢复）
    all_texts = []
    all_segments = []  # 收集所有段的 segments（带全局时间偏移）

    for idx, chunk_path in enumerate(chunk_paths):
        text_result_path = results_dir / f"chunk_{idx:04d}.txt"
        segments_result_path = results_dir / f"chunk_{idx:04d}_segments.json"

        # 当前段的时间偏移
        time_offset = idx * config.CHUNK_DURATION_SECONDS

        # 断点恢复：如果这段已经转写过，跳过
        if text_result_path.exists() and segments_result_path.exists():
            text = text_result_path.read_text(encoding="utf-8")
            segments = json.loads(
                segments_result_path.read_text(encoding="utf-8")
            )
            all_texts.append(text)
            all_segments.extend(segments)
            if progress_callback:
                ratio = 0.1 + 0.85 * (idx + 1) / total_chunks
                progress_callback(ratio, f"第 {idx+1}/{total_chunks} 段已有结果，跳过")
            logger.debug(f"段 {idx+1}/{total_chunks} 已有结果，跳过")
            continue

        if progress_callback:
            ratio = 0.1 + 0.85 * idx / total_chunks
            progress_callback(ratio, f"正在转写第 {idx+1}/{total_chunks} 段...")

        logger.info(f"转写第 {idx+1}/{total_chunks} 段...")
        start_time = time.time()

        result = model.transcribe(
            str(chunk_path),
            language=config.WHISPER_LANGUAGE,
            initial_prompt="以下是一段中文会议录音。",
        )

        text = result["text"].strip()
        elapsed = time.time() - start_time

        # 处理 segments：加上全局时间偏移
        chunk_segments = []
        for seg in result.get("segments", []):
            chunk_segments.append({
                "start": seg["start"] + time_offset,
                "end": seg["end"] + time_offset,
                "text": seg["text"].strip(),
            })

        # 立即保存（断点恢复用）
        text_result_path.write_text(text, encoding="utf-8")
        segments_result_path.write_text(
            json.dumps(chunk_segments, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        all_texts.append(text)
        all_segments.extend(chunk_segments)

        logger.info(
            f"段 {idx+1}/{total_chunks} 完成 | "
            f"耗时 {elapsed:.0f}s | 字数 {len(text)}"
        )

        if progress_callback:
            ratio = 0.1 + 0.85 * (idx + 1) / total_chunks
            progress_callback(
                ratio, f"第 {idx+1}/{total_chunks} 段完成（耗时 {elapsed:.0f}s）"
            )

    # 合并所有段落
    full_transcript = "\n".join(all_texts)

    # 保存完整转写和全局 segments
    final_transcript_path.write_text(full_transcript, encoding="utf-8")

    all_segments_path = output_dir / "segments.json"
    all_segments_path.write_text(
        json.dumps(all_segments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info(
        f"转写完成: {task_name} | 总字数 {len(full_transcript)} | "
        f"segments 数 {len(all_segments)}"
    )

    if progress_callback:
        progress_callback(1.0, f"转写完成，共 {len(full_transcript)} 字")

    return full_transcript, output_dir


def _find_existing_task(file_name: str) -> Optional[str]:
    """
    查找同名文件的未完成任务（有 temp 目录但 output 中没有完整结果）。
    用于断点恢复。
    """
    for task_dir in sorted(config.TEMP_DIR.iterdir(), reverse=True):
        if not task_dir.is_dir():
            continue
        if task_dir.name.startswith(file_name + "_"):
            # 检查是否已有完整结果
            output_dir = config.OUTPUT_DIR / task_dir.name
            final_transcript = output_dir / "转写全文.txt"
            if not final_transcript.exists() or not final_transcript.read_text(
                encoding="utf-8"
            ).strip():
                return task_dir.name
    return None
