"""
音频转写模块（FunASR版）
- FunASR Paraformer-zh：ASR + VAD + 标点恢复 + 说话人区分（cam++ clustering）
- 音频切片（断点续传，chunk 30分钟）
- 保存 segments（带时间戳+说话人）

FunASR 实际输出格式（有 spk_model 时）：
    res[0]["text"]          → 完整文本字符串
    res[0]["sentence_info"] → [
        {"text": "...", "start": 1230, "end": 4560, "spk": 0},
        ...
    ]
    - start/end 单位：毫秒
    - spk 是整数 ID（0, 1, 2...）

注意事项：
    - cam++ 做的是 speaker embedding + clustering，精度有限
    - 句子级时间戳（sentence_info）有 spk_model 时自动附带
    - 无 spk_model 时可传 sentence_timestamp=True 获取不含说话人的 sentence_info
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
_funasr_model = None
_funasr_model_has_speaker = False


def get_funasr_model(use_speaker: bool = False):
    """加载并缓存 FunASR 模型"""
    global _funasr_model, _funasr_model_has_speaker
    from funasr import AutoModel

    # 如果已有模型且说话人模式匹配，直接返回
    if _funasr_model is not None and _funasr_model_has_speaker == use_speaker:
        return _funasr_model

    logger.info(f"加载 FunASR 模型（说话人区分: {use_speaker}）...")

    kwargs = dict(
        model=config.FUNASR_MODEL,
        vad_model=config.FUNASR_VAD_MODEL,
        vad_kwargs={"max_single_segment_time": 60000},  # VAD最大切割片段60s
        punc_model=config.FUNASR_PUNC_MODEL,
    )
    if use_speaker:
        kwargs["spk_model"] = config.FUNASR_SPK_MODEL

    _funasr_model = AutoModel(**kwargs)
    _funasr_model_has_speaker = use_speaker

    logger.info("FunASR 模型加载完成")
    return _funasr_model


def split_audio(audio_path: str, task_name: str) -> list[Path]:
    """
    将音频切成固定时长的小段，保存到 temp/{task_name}/chunks/
    返回切片文件路径列表。
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


def _parse_funasr_result(
    result: list,
    time_offset_ms: int,
    use_speaker: bool,
) -> tuple[str, list[dict]]:
    """
    解析 FunASR 输出，返回 (文本, segments列表)。

    FunASR 真实输出结构：
        result[0]["text"]           → 完整文本
        result[0]["sentence_info"]  → 句子列表（有 spk_model 或 sentence_timestamp=True 时存在）
            每个元素：{"text": str, "start": int(ms), "end": int(ms), "spk": int}
            （无 spk_model 时没有 "spk" 字段）

    返回的 segments 格式（与旧版兼容）：
        {"start": float(秒), "end": float(秒), "text": str, "speaker": str}
    """
    if not result:
        return "", []

    item = result[0]
    text = item.get("text", "").strip()
    sentence_info = item.get("sentence_info", [])

    if not sentence_info:
        # 没有 sentence_info，返回纯文本，无 segments
        # 这种情况极少，通常是极短音频
        logger.warning("FunASR 未返回 sentence_info，可能是音频过短")
        return text, []

    segments = []
    for sent in sentence_info:
        # start/end 单位是毫秒，需要加上全局偏移再转秒
        start_ms = sent.get("start", 0) + time_offset_ms
        end_ms = sent.get("end", 0) + time_offset_ms
        sent_text = sent.get("text", "").strip()

        # spk 字段：有 spk_model 时是整数（0, 1, 2...），无时不存在
        spk_raw = sent.get("spk", None)
        if use_speaker and spk_raw is not None:
            speaker = f"SPEAKER_{int(spk_raw):02d}"
        else:
            speaker = "未知"

        segments.append({
            "start": round(start_ms / 1000, 3),
            "end": round(end_ms / 1000, 3),
            "text": sent_text,
            "speaker": speaker,
        })

    return text, segments


def _build_annotated_text(segments: list[dict]) -> str:
    """将 segments 转换为带说话人标注的文本（合并连续同一说话人的句子）"""
    lines = []
    current_speaker = None
    current_texts = []

    for seg in segments:
        spk = seg.get("speaker", "未知")
        if spk != current_speaker:
            if current_speaker is not None and current_texts:
                joined = "".join(current_texts)
                lines.append(f"【{current_speaker}】{joined}")
            current_speaker = spk
            current_texts = [seg["text"]]
        else:
            current_texts.append(seg["text"])

    if current_speaker is not None and current_texts:
        joined = "".join(current_texts)
        lines.append(f"【{current_speaker}】{joined}")

    return "\n\n".join(lines)


def transcribe_audio(
    audio_path: str,
    model_name: str = None,       # 保留兼容参数，FunASR 不使用
    enable_speaker: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> tuple[str, Path]:
    """
    转写音频文件，支持断点续传。
    同时保存 segments.json（带时间戳+说话人标签）和转写全文.txt。

    Args:
        audio_path: 音频文件路径
        model_name: 兼容参数，不使用（FunASR 模型在 config 里指定）
        enable_speaker: 是否启用说话人区分（cam++ clustering）
        progress_callback: 进度回调 (ratio: float, msg: str)

    Returns:
        (转写文本, 输出目录路径)
        - 启用说话人时返回带【SPEAKER_XX】标注的文本
        - 未启用时返回纯文本

    注意：cam++ 说话人区分精度有限，对声音相似的人效果较差。
    """
    file_name = Path(audio_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_name = f"{file_name}_{timestamp}"

    # 断点恢复
    existing_task = _find_existing_task(file_name)
    if existing_task:
        task_name = existing_task
        logger.info(f"发现未完成任务，恢复: {task_name}")

    # 备份原始文件
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

    # 结果文件路径
    final_transcript_path = output_dir / "转写全文.txt"
    final_annotated_path = output_dir / "转写全文_说话人标注.txt"
    all_segments_path = output_dir / "segments.json"

    # 已有完整转写则直接返回
    target_path = final_annotated_path if enable_speaker else final_transcript_path
    if target_path.exists():
        text = target_path.read_text(encoding="utf-8")
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

    model = get_funasr_model(use_speaker=enable_speaker)

    if progress_callback:
        progress_callback(0.1, "模型加载完成，开始转写...")

    all_texts = []
    all_segments = []

    for idx, chunk_path in enumerate(chunk_paths):
        text_result_path = results_dir / f"chunk_{idx:04d}.txt"
        segments_result_path = results_dir / f"chunk_{idx:04d}_segments.json"

        # 当前段的时间偏移（毫秒）
        time_offset_ms = idx * config.CHUNK_DURATION_SECONDS * 1000

        # 断点恢复：已有结果则跳过
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

        logger.info(f"转写第 {idx+1}/{total_chunks} 段: {chunk_path.name}")
        t_start = time.time()

        result = model.generate(
            input=str(chunk_path),
            batch_size_s=300,
            batch_size_threshold_s=60,
            hotword="",
            sentence_timestamp=True,   # 确保有 sentence_info（即使无 spk_model）
        )

        text, segments = _parse_funasr_result(result, time_offset_ms, enable_speaker)
        elapsed = time.time() - t_start

        # 立即保存（断点续传用）
        text_result_path.write_text(text, encoding="utf-8")
        segments_result_path.write_text(
            json.dumps(segments, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        all_texts.append(text)
        all_segments.extend(segments)

        logger.info(
            f"段 {idx+1}/{total_chunks} 完成 | "
            f"耗时 {elapsed:.0f}s | 字数 {len(text)} | "
            f"sentences {len(segments)}"
        )

        if progress_callback:
            ratio = 0.1 + 0.85 * (idx + 1) / total_chunks
            progress_callback(
                ratio, f"第 {idx+1}/{total_chunks} 段完成（耗时 {elapsed:.0f}s）"
            )

    # 合并全文
    full_transcript = "\n".join(all_texts)
    final_transcript_path.write_text(full_transcript, encoding="utf-8")

    # 保存 segments（所有段落，含说话人字段）
    all_segments_path.write_text(
        json.dumps(all_segments, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 说话人区分：生成带标注文本
    annotated_text = ""
    has_speaker_info = (
        enable_speaker
        and any(s.get("speaker", "未知") != "未知" for s in all_segments)
    )
    if has_speaker_info:
        annotated_text = _build_annotated_text(all_segments)
        final_annotated_path.write_text(annotated_text, encoding="utf-8")
        logger.info("已生成说话人标注文本")
    elif enable_speaker:
        logger.warning(
            "启用了说话人区分，但所有句子均未识别出说话人（可能是 cam++ 聚类失败，"
            "声音差异不明显时容易发生）"
        )

    return_text = annotated_text if has_speaker_info else full_transcript

    logger.info(
        f"转写完成: {task_name} | 总字数 {len(full_transcript)} | "
        f"sentences {len(all_segments)}"
    )

    if progress_callback:
        progress_callback(1.0, f"转写完成，共 {len(full_transcript)} 字")

    return return_text, output_dir


def _find_existing_task(file_name: str) -> Optional[str]:
    """查找同名文件的未完成任务，用于断点恢复。"""
    if not config.TEMP_DIR.exists():
        return None
    for task_dir in sorted(config.TEMP_DIR.iterdir(), reverse=True):
        if not task_dir.is_dir():
            continue
        if task_dir.name.startswith(file_name + "_"):
            output_dir = config.OUTPUT_DIR / task_dir.name
            final_transcript = output_dir / "转写全文.txt"
            if not final_transcript.exists() or not final_transcript.read_text(
                encoding="utf-8"
            ).strip():
                return task_dir.name
    return None
