"""
音频转写模块
- 音频切片（用于断点续传）
- Whisper 本地转写
- 断点恢复
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from pydub import AudioSegment

import config


# 全局缓存，避免重复加载模型
_whisper_model = None


def get_whisper_model(model_name: str = None):
    """加载并缓存 Whisper 模型"""
    global _whisper_model
    import whisper

    model_name = model_name or config.WHISPER_MODEL
    if _whisper_model is None:
        _whisper_model = whisper.load_model(model_name)
    return _whisper_model


def split_audio(audio_path: str, task_name: str) -> list[Path]:
    """
    将音频切成固定时长的小段，保存到 temp/{task_name}/chunks/
    返回切片文件路径列表
    """
    chunks_dir = config.TEMP_DIR / task_name / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    # 检查是否已经切过片（断点恢复时跳过）
    manifest_path = config.TEMP_DIR / task_name / "chunks_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        chunk_paths = [Path(p) for p in manifest["chunk_paths"]]
        # 验证文件都还在
        if all(p.exists() for p in chunk_paths):
            return chunk_paths

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

    # 保存切片清单
    manifest = {
        "source_audio": str(audio_path),
        "total_chunks": len(chunk_paths),
        "chunk_duration_seconds": config.CHUNK_DURATION_SECONDS,
        "chunk_paths": [str(p) for p in chunk_paths],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return chunk_paths


def transcribe_audio(
    audio_path: str,
    model_name: str = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> tuple[str, Path]:
    """
    转写音频文件，支持断点续传。

    Args:
        audio_path: 音频文件路径
        model_name: Whisper 模型名称
        progress_callback: 进度回调 (progress_ratio, status_message)

    Returns:
        (完整转写文本, 输出目录路径)
    """
    file_name = Path(audio_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_name = f"{file_name}_{timestamp}"

    # 复制原始文件到 input 目录
    input_copy = config.INPUT_DIR / Path(audio_path).name
    if not input_copy.exists():
        import shutil
        shutil.copy2(audio_path, input_copy)

    # 输出目录
    output_dir = config.OUTPUT_DIR / task_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # 中间文件目录
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
            return text, output_dir

    if progress_callback:
        progress_callback(0.0, "正在切分音频...")

    # 切片
    chunk_paths = split_audio(audio_path, task_name)
    total_chunks = len(chunk_paths)

    if progress_callback:
        progress_callback(0.05, f"音频已切为 {total_chunks} 段，加载模型中...")

    # 加载模型
    model = get_whisper_model(model_name)

    if progress_callback:
        progress_callback(0.1, "模型加载完成，开始转写...")

    # 逐段转写（带断点恢复）
    all_texts = []
    for idx, chunk_path in enumerate(chunk_paths):
        result_path = results_dir / f"chunk_{idx:04d}.txt"

        # 断点恢复：如果这段已经转写过，跳过
        if result_path.exists():
            text = result_path.read_text(encoding="utf-8")
            all_texts.append(text)
            if progress_callback:
                ratio = 0.1 + 0.85 * (idx + 1) / total_chunks
                progress_callback(ratio, f"第 {idx+1}/{total_chunks} 段已有结果，跳过")
            continue

        # 转写当前段
        if progress_callback:
            ratio = 0.1 + 0.85 * idx / total_chunks
            progress_callback(ratio, f"正在转写第 {idx+1}/{total_chunks} 段...")

        start_time = time.time()
        result = model.transcribe(
            str(chunk_path),
            language=config.WHISPER_LANGUAGE,
            initial_prompt="以下是一段中文会议录音。",
        )
        text = result["text"].strip()
        elapsed = time.time() - start_time

        # 立即保存该段结果
        result_path.write_text(text, encoding="utf-8")
        all_texts.append(text)

        if progress_callback:
            ratio = 0.1 + 0.85 * (idx + 1) / total_chunks
            progress_callback(ratio, f"第 {idx+1}/{total_chunks} 段完成（耗时 {elapsed:.0f}s）")

    # 合并所有段落
    full_transcript = "\n".join(all_texts)

    # 保存完整转写
    final_transcript_path.write_text(full_transcript, encoding="utf-8")

    if progress_callback:
        progress_callback(1.0, f"转写完成，共 {len(full_transcript)} 字")

    return full_transcript, output_dir
