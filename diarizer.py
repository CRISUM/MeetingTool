"""
说话人区分模块（Speaker Diarization）
使用 pyannote.audio 识别"谁在什么时候说话"，
再与 Whisper 的时间戳对齐，生成带说话人标注的转写文本。
"""

from pathlib import Path
from typing import Callable, Optional

import config


def check_diarization_available() -> tuple[bool, str]:
    """检查说话人区分功能是否可用"""
    if not config.HF_TOKEN:
        return False, "未配置 HF_TOKEN（Hugging Face Token）"
    try:
        import pyannote.audio
        return True, "可用"
    except ImportError:
        return False, "未安装 pyannote.audio，请运行: pip install pyannote.audio"


def diarize_audio(
    audio_path: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> list[dict]:
    """
    对音频进行说话人区分。

    Returns:
        说话人片段列表: [{"start": 0.0, "end": 5.2, "speaker": "SPEAKER_00"}, ...]
    """
    from pyannote.audio import Pipeline

    if progress_callback:
        progress_callback(0.0, "加载说话人区分模型...")

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=config.HF_TOKEN,
    )

    if progress_callback:
        progress_callback(0.3, "正在分析说话人...")

    diarization = pipeline(audio_path)

    # 兼容新版pyannote：DiarizeOutput有speaker_diarization属性
    # 旧版直接返回Annotation对象，有itertracks方法
    annotation = getattr(diarization, "speaker_diarization", diarization)

    segments = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        segments.append({
            "start": turn.start,
            "end": turn.end,
            "speaker": speaker,
        })

    if progress_callback:
        # 统计说话人数量
        speakers = set(s["speaker"] for s in segments)
        progress_callback(1.0, f"说话人区分完成，识别到 {len(speakers)} 位说话人")

    return segments


def align_transcript_with_speakers(
    whisper_segments: list[dict],
    diarization_segments: list[dict],
) -> str:
    """
    将 Whisper 的逐句时间戳与说话人区分结果对齐，
    生成带说话人标注的转写文本。

    Args:
        whisper_segments: Whisper 输出的 segments，每个含 start, end, text
        diarization_segments: 说话人区分结果

    Returns:
        带说话人标注的文本
    """
    def find_speaker(start: float, end: float) -> str:
        """找到与给定时间段重叠最多的说话人"""
        best_speaker = "未知"
        best_overlap = 0.0

        for seg in diarization_segments:
            # 计算重叠
            overlap_start = max(start, seg["start"])
            overlap_end = min(end, seg["end"])
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = seg["speaker"]

        return best_speaker

    # 对齐
    lines = []
    current_speaker = None
    current_text = []

    for seg in whisper_segments:
        speaker = find_speaker(seg["start"], seg["end"])

        if speaker != current_speaker:
            # 说话人切换，输出前一段
            if current_speaker is not None and current_text:
                lines.append(f"【{current_speaker}】{"".join(current_text)}")
            current_speaker = speaker
            current_text = [seg["text"].strip()]
        else:
            current_text.append(seg["text"].strip())

    # 最后一段
    if current_speaker is not None and current_text:
        lines.append(f"【{current_speaker}】{"".join(current_text)}")

    return "\n\n".join(lines)


def transcribe_with_diarization(
    audio_path: str,
    model_name: str = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> tuple[str, str]:
    """
    带说话人区分的完整转写流程。

    Returns:
        (纯转写文本, 带说话人标注的文本)
    """
    import whisper
    from transcriber import get_whisper_model

    # Step 1: 说话人区分
    def diar_progress(ratio, msg):
        if progress_callback:
            progress_callback(ratio * 0.4, msg)

    diarization_segments = diarize_audio(audio_path, progress_callback=diar_progress)

    # Step 2: Whisper 转写（需要逐句时间戳）
    if progress_callback:
        progress_callback(0.4, "加载 Whisper 模型...")

    model = get_whisper_model(model_name)

    if progress_callback:
        progress_callback(0.45, "Whisper 转写中（需要完整处理以获取时间戳）...")

    result = model.transcribe(
        audio_path,
        language=config.WHISPER_LANGUAGE,
        initial_prompt="以下是一段中文会议录音。",
        verbose=False,
    )

    if progress_callback:
        progress_callback(0.9, "对齐说话人与文本...")

    # Step 3: 对齐
    plain_text = result["text"]
    whisper_segments = result.get("segments", [])
    annotated_text = align_transcript_with_speakers(whisper_segments, diarization_segments)

    if progress_callback:
        speakers = set(s["speaker"] for s in diarization_segments)
        progress_callback(1.0, f"完成，识别到 {len(speakers)} 位说话人")

    return plain_text, annotated_text