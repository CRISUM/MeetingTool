"""
说话人区分模块（Speaker Diarization）
- pyannote 分析说话人时间段
- 结果缓存（跑一次后不用重跑）
- 与 Whisper segments 对齐生成带标注文本
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)


def check_diarization_available() -> tuple[bool, str]:
    """检查说话人区分功能是否可用"""
    if not config.HF_TOKEN:
        return False, "未配置 HF_TOKEN（Hugging Face Token）"
    try:
        import pyannote.audio
        return True, "可用"
    except ImportError:
        return False, "未安装 pyannote.audio，请运行: pip install pyannote.audio"


def _get_cache_key(audio_path: str) -> str:
    """生成缓存 key：文件名 + 文件大小 + 修改时间"""
    stat = os.stat(audio_path)
    name = Path(audio_path).name
    return f"{name}_{stat.st_size}_{int(stat.st_mtime)}"


def _get_cache_path(audio_path: str, task_name: str) -> Path:
    """获取说话人区分缓存文件路径"""
    cache_dir = config.TEMP_DIR / task_name
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "diarization_cache.json"


def load_diarization_cache(
    audio_path: str, task_name: str
) -> Optional[list[dict]]:
    """
    加载说话人区分缓存。
    返回 segments 列表或 None（无缓存）。
    """
    cache_path = _get_cache_path(audio_path, task_name)
    if not cache_path.exists():
        return None

    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        # 校验缓存有效性
        if data.get("cache_key") == _get_cache_key(audio_path):
            logger.info("说话人区分缓存命中，跳过分析")
            return data["segments"]
        else:
            logger.info("说话人区分缓存已过期（文件已变更）")
            return None
    except Exception as e:
        logger.warning(f"读取说话人区分缓存失败: {e}")
        return None


def save_diarization_cache(
    audio_path: str, task_name: str, segments: list[dict]
):
    """保存说话人区分结果到缓存"""
    cache_path = _get_cache_path(audio_path, task_name)
    data = {
        "cache_key": _get_cache_key(audio_path),
        "audio_file": str(audio_path),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "num_speakers": len(set(s["speaker"] for s in segments)),
        "num_segments": len(segments),
        "segments": segments,
    }
    cache_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"说话人区分结果已缓存: {cache_path}")


def diarize_audio(
    audio_path: str,
    task_name: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> list[dict]:
    """
    对音频进行说话人区分，带缓存。

    Returns:
        说话人片段列表: [{"start": 0.0, "end": 5.2, "speaker": "SPEAKER_00"}, ...]
    """
    # 检查缓存
    cached = load_diarization_cache(audio_path, task_name)
    if cached is not None:
        if progress_callback:
            speakers = set(s["speaker"] for s in cached)
            progress_callback(
                1.0, f"说话人区分（缓存）：识别到 {len(speakers)} 位说话人"
            )
        return cached

    from pyannote.audio import Pipeline

    if progress_callback:
        progress_callback(0.0, "加载说话人区分模型...")

    logger.info("加载 pyannote 说话人区分模型...")
    start_time = time.time()

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=config.HF_TOKEN,
    )

    # 推到GPU加速（如果可用）
    import torch
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pipeline = pipeline.to(device)
    logger.info(f"pyannote 运行设备: {device}")

    if progress_callback:
        progress_callback(0.2, "模型加载完成，正在分析说话人...")

    logger.info(f"开始说话人区分: {Path(audio_path).name}")
    diarization = pipeline(audio_path)

    # 兼容新版 pyannote：DiarizeOutput 有 speaker_diarization 属性
    annotation = getattr(diarization, "speaker_diarization", diarization)

    segments = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        segments.append({
            "start": round(turn.start, 3),
            "end": round(turn.end, 3),
            "speaker": speaker,
        })

    elapsed = time.time() - start_time
    speakers = set(s["speaker"] for s in segments)

    logger.info(
        f"说话人区分完成 | 耗时 {elapsed:.0f}s | "
        f"{len(speakers)} 位说话人 | {len(segments)} 个片段"
    )

    # 保存缓存
    save_diarization_cache(audio_path, task_name, segments)

    if progress_callback:
        progress_callback(
            1.0, f"说话人区分完成（{elapsed:.0f}s），识别到 {len(speakers)} 位说话人"
        )

    return segments


def align_transcript_with_speakers(
    whisper_segments: list[dict],
    diarization_segments: list[dict],
) -> str:
    """
    将 Whisper segments（带全局时间戳）与说话人区分结果对齐。

    Args:
        whisper_segments: [{"start": float, "end": float, "text": str}, ...]
        diarization_segments: [{"start": float, "end": float, "speaker": str}, ...]

    Returns:
        带说话人标注的文本
    """
    def find_speaker(start: float, end: float) -> str:
        best_speaker = "未知"
        best_overlap = 0.0

        for seg in diarization_segments:
            overlap_start = max(start, seg["start"])
            overlap_end = min(end, seg["end"])
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = seg["speaker"]

        return best_speaker

    lines = []
    current_speaker = None
    current_text = []

    for seg in whisper_segments:
        speaker = find_speaker(seg["start"], seg["end"])

        if speaker != current_speaker:
            if current_speaker is not None and current_text:
                lines.append(f"【{current_speaker}】{"".join(current_text)}")
            current_speaker = speaker
            current_text = [seg["text"]]
        else:
            current_text.append(seg["text"])

    if current_speaker is not None and current_text:
        lines.append(f"【{current_speaker}】{"".join(current_text)}")

    logger.info(f"说话人对齐完成: {len(lines)} 段对话")
    return "\n\n".join(lines)